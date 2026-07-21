import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import demand as demand_engine
from app.state_session import get_current_state

st.set_page_config(page_title="Demand Forecasting", page_icon="📈", layout="wide")
st.title("📈 Enrollment & Demand Forecasting")
st.caption("M9 — thin wrapper over backend.engines.demand. No logic lives here.")

state = get_current_state()
all_codes = sorted(list(state.courses.keys()) + list(state.elective_catalog.keys()))

tab_forecast, tab_over, tab_new, tab_shocks = st.tabs(
    ["Course Forecast", "Oversubscription", "Propose New Elective", "Shock Scenarios"]
)

with tab_forecast:
    code = st.selectbox("Course", options=all_codes, index=all_codes.index("CMPS303") if "CMPS303" in all_codes else 0)
    result = demand_engine.forecast_course_demand(state, code)
    if "error" in result:
        st.warning(result["error"])
    else:
        hist_df = pd.DataFrame(result["history"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist_df["period"], y=hist_df["enrolled"], mode="lines+markers", name="Enrolled"))
        fig.add_trace(go.Scatter(x=hist_df["period"], y=hist_df["capacity"], mode="lines", name="Capacity", line=dict(dash="dash")))
        forecast_periods = [f["period"] for f in result["forecast"]]
        forecast_vals = [f["projected_enrolled"] for f in result["forecast"]]
        fig.add_trace(go.Scatter(
            x=[hist_df["period"].iloc[-1]] + forecast_periods,
            y=[hist_df["enrolled"].iloc[-1]] + forecast_vals,
            mode="lines+markers", name="Forecast", line=dict(dash="dot", color="orange"),
        ))
        fig.update_layout(title=f"{code} — enrollment trend ({result['trend_direction']})", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Trend slope: {result['trend_slope_per_term']:+.2f} students/term")

with tab_over:
    threshold = st.slider("Waitlist threshold to flag as oversubscribed", 1, 15, 3)
    report = demand_engine.oversubscription_report(state, waitlist_threshold=threshold)
    if report:
        df = pd.DataFrame(report)
        fig = go.Figure(go.Bar(
            x=df["course"], y=df["utilization"],
            marker_color=["firebrick" if s == "oversubscribed" else "steelblue" for s in df["status"]],
            text=df["status"],
        ))
        fig.update_layout(title="Utilization by course (red = oversubscribed, blue = underenrolled)", yaxis_title="Utilization")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No courses flagged at this threshold.")

with tab_new:
    st.write("Give it a name and description — it TF-IDF-matches against every existing course/elective description.")
    name = st.text_input("Proposed course name", value="Deep Learning for Computer Vision")
    description = st.text_area(
        "Description",
        value="Convolutional neural networks, image classification, object detection, and deep learning architectures applied to visual data.",
        height=100,
    )
    credits = st.number_input("Credits", min_value=1, max_value=6, value=3)
    if st.button("Check feasibility", type="primary"):
        result = demand_engine.propose_new_elective(state, name=name, description=description, credits=credits)
        verdict_color = {"feasible": "green", "feasible_flagged": "orange", "infeasible_no_room": "red", "insufficient_evidence": "gray"}
        st.markdown(f"### Verdict: :{verdict_color.get(result['verdict'], 'gray')}[{result['verdict']}]")
        if result.get("rationale"):
            st.write(result["rationale"])
        if result.get("warnings"):
            for w in result["warnings"]:
                st.warning(w)
        if result.get("similar_courses"):
            st.subheader("Most similar existing courses")
            st.dataframe(pd.DataFrame(result["similar_courses"]), use_container_width=True)
        if result.get("faculty_matches"):
            st.subheader("Faculty with a specialization match")
            st.dataframe(pd.DataFrame(result["faculty_matches"]), use_container_width=True)
        if result.get("projected_first_year_demand") is not None:
            st.metric("Projected first-year demand", result["projected_first_year_demand"])

with tab_shocks:
    st.subheader("Make an elective mandatory")
    mandatory_code = st.selectbox("Elective", options=all_codes, key="mandatory_code")
    cohort = st.number_input("Estimated cohort size", value=100, step=10)
    if st.button("Simulate mandatory shock"):
        result = demand_engine.simulate_mandatory_shock(state, mandatory_code, cohort_size_estimate=cohort)
        c1, c2, c3 = st.columns(3)
        c1.metric("Current capacity", result["current_capacity"])
        c2.metric("Projected demand", result["projected_demand_if_mandatory"])
        c3.metric("Capacity gap", result["capacity_gap"])
        st.write("✅ Feasible without changes" if result["feasible_without_changes"] else "⚠️ Would need more capacity")

    st.subheader("Retire a course")
    retire_code = st.selectbox("Course to retire", options=all_codes, key="retire_code")
    if st.button("Simulate retirement"):
        result = demand_engine.simulate_retirement(state, retire_code)
        st.write(f"**{result['displaced_students']} students** displaced, redistributed by similarity:")
        st.dataframe(pd.DataFrame(result["redistribution"]), use_container_width=True)

    st.subheader("Intake shock")
    pct = st.slider("Intake change (%)", -50, 100, 20)
    if st.button("Simulate intake shock"):
        flagged = demand_engine.simulate_intake_shock(state, pct_change=pct / 100)
        if flagged:
            st.dataframe(pd.DataFrame(flagged), use_container_width=True)
        else:
            st.success("No courses would go over capacity at this intake level.")
