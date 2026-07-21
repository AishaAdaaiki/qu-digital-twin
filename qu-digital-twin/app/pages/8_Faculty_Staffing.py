import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import faculty as faculty_engine
from app.state_session import get_current_state, set_current_state

st.set_page_config(page_title="Faculty & Staffing", page_icon="🧑‍🏫", layout="wide")
st.title("🧑‍🏫 Faculty & Staffing")
st.caption("M11 — thin wrapper over backend.engines.faculty. Models one section per offered course per term.")

state = get_current_state()

tab_workload, tab_hiring, tab_roster = st.tabs(["Workload", "Hiring Simulator", "Roster Moves"])

with tab_workload:
    term = st.selectbox("Term", options=["fall", "spring"], key="workload_term")
    result = faculty_engine.auto_assign_faculty(state, term)
    report = faculty_engine.workload_report(state, term)

    if result["unteachable_courses"]:
        st.error(f"Unteachable this term: {', '.join(result['unteachable_courses'])}")
    else:
        st.success("Every course has a qualified, available instructor this term.")

    df = pd.DataFrame(report)
    if not df.empty:
        fig = px.bar(
            df, x="name", y="assigned_courses", color="status",
            color_discrete_map={"overloaded": "firebrick", "at_capacity": "steelblue", "underused": "lightgray"},
            title=f"Faculty workload — {term}",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)

    ratio = faculty_engine.student_faculty_ratio_trend(state)
    st.metric("Student-faculty ratio", ratio["actual"], help=ratio["detail"])

with tab_hiring:
    st.write("Simulate hiring one faculty member — what becomes teachable that isn't now?")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Dr. New Hire")
        rank = st.selectbox("Rank", ["lecturer", "assistant_professor", "associate_professor", "full_professor", "adjunct"])
        max_courses = st.slider("Max courses per term", 1, 5, 3)
    with col2:
        all_course_codes = sorted(state.courses.keys())
        qualified = st.multiselect("Qualified courses", options=all_course_codes)
        specializations = st.text_input("Specializations (comma-separated)", value="machine_learning, artificial_intelligence")
        term_hiring = st.selectbox("Term to test", options=["fall", "spring"], key="hiring_term")

    if st.button("Simulate hire", type="primary"):
        new_faculty = {
            "name": name, "rank": rank, "fte": 1.0, "max_courses_per_term": max_courses,
            "qualified_courses": qualified, "specializations": [s.strip() for s in specializations.split(",") if s.strip()],
            "status": "active", "annual_salary_qar": 300000,
        }
        impact = faculty_engine.hiring_impact(state, new_faculty, term_hiring)
        if impact["newly_teachable_courses"]:
            st.success(f"Newly teachable: {', '.join(impact['newly_teachable_courses'])}")
        else:
            st.info("This hire wouldn't resolve any current unteachable-course gap this term.")
        st.write("Courses this hire would be assigned to teach:", impact["hire_taught_courses"])

with tab_roster:
    st.write("Add, remove, or change status for a faculty member. These changes apply to your working state (see State Manager to reset).")
    action = st.selectbox("Action", ["Change status", "Remove faculty"])
    fid = st.selectbox("Faculty", options=sorted(state.faculty.keys()), format_func=lambda f: f"{f} — {state.faculty[f]['name']}")

    if action == "Change status":
        new_status = st.selectbox("New status", ["active", "on_leave", "sabbatical"])
        if st.button("Apply"):
            new_state = faculty_engine.apply_set_faculty_status(state, fid, new_status)
            set_current_state(new_state)
            st.success(f"{fid} status set to {new_status}.")
            st.rerun()
    else:
        if st.button("Apply", type="primary"):
            new_state = faculty_engine.apply_remove_faculty(state, fid)
            set_current_state(new_state)
            st.success(f"{fid} removed from roster.")
            st.rerun()
