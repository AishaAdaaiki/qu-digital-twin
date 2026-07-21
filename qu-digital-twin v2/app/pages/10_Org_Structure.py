import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import org as org_engine
from app.state_session import get_current_state, set_current_state, save_scenario

st.set_page_config(page_title="Org Structure", page_icon="🏛️", layout="wide")
st.title("🏛️ Org Structure & Curriculum Design")
st.caption("M13 — reuses M9-M12 under the hood. Program splits are impact analyses, not executable moves (see docstring in backend/engines/org.py).")

state = get_current_state()

tab_minor, tab_split, tab_retire = st.tabs(["New Minor Feasibility", "Program Split Impact", "Retire/Promote a Course"])

with tab_minor:
    minor_name = st.text_input("Minor/concentration name", value="AI & Data Science Minor")
    elective_codes = st.multiselect(
        "Courses (from elective catalog)",
        options=sorted(state.elective_catalog.keys()),
        default=["CMPS403", "CMPS460", "CMPS453", "CMPS360"],
        format_func=lambda c: f"{c} — {state.elective_catalog[c]['name']}",
    )
    if st.button("Check feasibility", type="primary"):
        result = org_engine.new_minor_feasibility(state, minor_name, elective_codes)
        if "error" in result:
            st.error(result["error"])
        else:
            verdict_color = {"feasible": "green", "feasible_flagged": "orange", "infeasible_no_room": "red"}
            st.markdown(f"### Verdict: :{verdict_color.get(result['verdict'], 'gray')}[{result['verdict']}]")
            st.metric("Total credit hours", result["total_credits"])
            st.dataframe(pd.DataFrame(result["per_course"]), use_container_width=True)

with tab_split:
    new_program = st.text_input("New program name", value="AI & Data Science")
    move_codes = st.multiselect(
        "Courses to move (from courses.json)", options=sorted(state.courses.keys()),
        default=["CMPS380", "CMPS405"],
        format_func=lambda c: f"{c} — {state.courses[c]['name']}",
    )
    if st.button("Run split impact analysis", type="primary"):
        result = org_engine.split_program_impact(state, new_program, move_codes)
        if "error" in result:
            st.error(result["error"])
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Moved credits", result["moved_total_credits"])
            c2.metric("Remaining credits", result["remaining_total_credits"])
            c3.metric("Est. affected students", result["estimated_affected_students"])

            fig = go.Figure()
            categories = sorted(set(result["moved_credit_hours_by_category"]) | set(result["remaining_credit_hours_by_category"]))
            fig.add_trace(go.Bar(name="Moves to new program", x=categories,
                                  y=[result["moved_credit_hours_by_category"].get(c, 0) for c in categories]))
            fig.add_trace(go.Bar(name="Stays in current program", x=categories,
                                  y=[result["remaining_credit_hours_by_category"].get(c, 0) for c in categories]))
            fig.update_layout(barmode="stack", title="Credit-hour distribution after split")
            st.plotly_chart(fig, use_container_width=True)

            if result["faculty_needed_by_both_programs"]:
                st.warning(f"{len(result['faculty_needed_by_both_programs'])} faculty member(s) would be needed by both programs:")
                st.json(result["faculty_needed_by_both_programs"])
            st.caption(result["note"])

with tab_retire:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Retire a course")
        retire_code = st.selectbox("Course", options=sorted(state.courses.keys()), key="org_retire")
        if st.button("Analyze retirement impact"):
            result = org_engine.retirement_impact(state, retire_code)
            st.write(result["note"])
            st.dataframe(pd.DataFrame(result["demand_redistribution"]["redistribution"]), use_container_width=True)
        if st.button("Apply: remove from program", type="primary"):
            new_state = org_engine.apply_retire_course(state, retire_code)
            set_current_state(new_state)
            st.success(f"{retire_code} retired from the active state.")
            st.rerun()

    with col2:
        st.subheader("Promote an elective into the program")
        promote_code = st.selectbox("Elective", options=sorted(state.elective_catalog.keys()), key="org_promote")
        if st.button("Apply: add to program", type="primary"):
            new_state = org_engine.apply_promote_elective_to_program(state, promote_code)
            set_current_state(new_state)
            st.success(f"{promote_code} added to the active program.")
            st.rerun()

st.divider()
st.subheader("Save current state as a named scenario")
label = st.text_input("Scenario label", value="My scenario")
if st.button("Save for comparison"):
    save_scenario(state, label)
    st.success(f"Saved as '{label}'. See Scenario Comparison to compare against baseline.")
