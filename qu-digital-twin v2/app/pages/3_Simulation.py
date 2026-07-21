import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses, load_demand_history
from backend.simulation import load_config, run_cohort_simulation, run_monte_carlo
from backend.scenarios import (
    capacity_bottleneck_ranking,
    remove_summer_scenario,
    restrict_course_to_term_scenario,
    run_scenario,
)
from backend.plots import graduation_histogram, bottleneck_bar_chart, scenario_comparison_bar
from backend import success_rates as sr

st.set_page_config(page_title="Simulation", page_icon="📊", layout="wide")
st.title("📊 Cohort Simulation & What-If Analysis")
st.caption("M4/M5 — thin wrapper over backend.simulation and backend.scenarios. No logic lives here.")

courses = load_courses()
config = load_config()
demand_history = load_demand_history()

tab_cohort, tab_whatif, tab_rates = st.tabs(["Cohort Simulation", "What-If Analysis", "Course Success Rates"])

with tab_cohort:
    st.subheader("Single-cohort flow simulator (T3.1) + Monte Carlo (T3.4)")
    col1, col2, col3 = st.columns(3)
    with col1:
        n_students = st.slider("Students per run", 20, 500, 100, step=20)
    with col2:
        n_runs = st.slider("Monte Carlo runs", 1, 50, 10)
    with col3:
        seed = st.number_input("Seed", value=42, step=1)

    if st.button("Run cohort simulation", type="primary"):
        with st.spinner("Simulating..."):
            single = run_cohort_simulation(n_students=n_students, seed=int(seed), courses=courses, config=config)
            mc = run_monte_carlo(n_students, n_runs, config=config, courses=courses, seed_start=int(seed))

        c1, c2, c3 = st.columns(3)
        c1.metric("Mean graduation term", f"{mc['mean_graduation_term']:.1f}" if mc["mean_graduation_term"] else "n/a")
        c2.metric("Std dev (terms)", f"{mc['std']:.2f}" if mc["std"] else "n/a")
        c3.metric("Stuck students (total, all runs)", mc["n_stuck_total"])

        if mc["distribution"]:
            st.pyplot(graduation_histogram(mc["distribution"], title=f"Graduation-time distribution ({n_runs} runs x {n_students} students)"))

        st.subheader("Bottleneck courses (single seeded run)")
        scores = {
            code: single["fail_counts"].get(code, 0) + single["capacity_block_counts"].get(code, 0)
            for code in courses
        }
        scores = {k: v for k, v in scores.items() if v > 0}
        if scores:
            st.pyplot(bottleneck_bar_chart(scores))
        else:
            st.info("No bottlenecks surfaced at this scale — try more students or more runs.")
    else:
        st.info("Set parameters and click **Run cohort simulation**.")

with tab_whatif:
    st.subheader("What-if scenarios (T3.2 capacity bottlenecks, T3.3 term-capacity stress test)")
    scenario_type = st.selectbox(
        "Scenario type",
        ["Top-5 seat-capacity bottlenecks", "Restrict one course to a single term", "Remove summer semester"],
    )
    n_students_wi = st.slider("Students per run (what-if)", 20, 500, 150, step=20, key="wi_n")
    n_runs_wi = st.slider("Runs per scenario", 1, 20, 5, key="wi_runs")

    if scenario_type == "Top-5 seat-capacity bottlenecks":
        if st.button("Run ranking", type="primary"):
            with st.spinner("Testing seat-capacity cuts across all limited courses..."):
                ranking = capacity_bottleneck_ranking(courses=courses, config=config, n_students=n_students_wi, n_runs=n_runs_wi)
            st.table(
                [{"Course": r["course"], "Cap (orig -> halved)": f"{r['original_capacity']} -> {r['halved_capacity']}",
                  "Δ mean grad term": round(r["delta_terms"], 2) if r["delta_terms"] is not None else "n/a",
                  "% students affected": round(r["affected_students_pct"], 1)} for r in ranking]
            )
            if ranking:
                st.pyplot(scenario_comparison_bar(ranking, title="Seat-capacity cut impact by course"))

    elif scenario_type == "Restrict one course to a single term":
        course_choice = st.selectbox("Course to restrict", options=sorted(courses.keys()))
        term_choice = st.selectbox("Restrict to term", options=["fall", "spring", "summer"])
        if st.button("Run scenario", type="primary"):
            with st.spinner("Running baseline vs. scenario..."):
                result = restrict_course_to_term_scenario(
                    course_choice, term_choice, courses=courses, config=config, n_students=n_students_wi, n_runs=n_runs_wi
                )
            c1, c2, c3 = st.columns(3)
            c1.metric("Baseline mean term", f"{result['baseline_mean']:.2f}" if result["baseline_mean"] else "n/a")
            c2.metric("Scenario mean term", f"{result['scenario_mean']:.2f}" if result["scenario_mean"] else "n/a")
            c3.metric("Δ terms", f"{result['delta_terms']:+.2f}" if result["delta_terms"] is not None else "n/a")
            st.write(f"**{result['affected_students_pct']:.1f}%** of students had a different graduation term under this scenario.")

    else:  # Remove summer semester
        if st.button("Run scenario", type="primary"):
            with st.spinner("Running baseline vs. no-summer scenario..."):
                result = remove_summer_scenario(courses=courses, config=config, n_students=n_students_wi, n_runs=n_runs_wi)
            c1, c2, c3 = st.columns(3)
            c1.metric("Baseline mean term", f"{result['baseline_mean']:.2f}" if result["baseline_mean"] else "n/a")
            c2.metric("Scenario mean term", f"{result['scenario_mean']:.2f}" if result["scenario_mean"] else "n/a")
            c3.metric("Δ terms", f"{result['delta_terms']:+.2f}" if result["delta_terms"] is not None else "n/a")
            st.write(f"**{result['affected_students_pct']:.1f}%** of students had a different graduation term without summer offerings.")

with tab_rates:
    st.subheader("Per-course, per-semester success rates")
    st.caption(
        "Every course's effective pass rate blends its own historical pass rate (from "
        "demand_history.json) with its direct prerequisites' rates, weighted 80/20 by "
        "default — a course whose prerequisites perform poorly gets nudged down too, on "
        "the theory that students arrive less prepared. This is what actually drives "
        "pass/fail/withdraw outcomes in the Cohort Simulation and What-If tabs above "
        "(instead of one flat rate per course category)."
    )

    weight = st.slider(
        "Weight on a course's own history (vs. its prerequisite chain)",
        0.0, 1.0, sr.DEFAULT_WEIGHT, step=0.05,
        help="1.0 = ignore prerequisites entirely, use only the course's own historical rate. "
             "Lower values let weak prerequisite performance pull a course's effective rate down further.",
    )

    rows = []
    for code, record in sorted(courses.items()):
        for term in record.get("offered", []):
            own = sr.historical_rate(demand_history, code, term)
            eff = sr.effective_rate(courses, demand_history, config, code, term=term, weight=weight)
            rows.append({
                "Course": code,
                "Name": record["name"],
                "Category": record.get("category", ""),
                "Term": term,
                "Own historical rate": round(own, 3) if own is not None else "no data (category fallback)",
                "Effective rate": round(eff, 3),
                "Direct prerequisites": ", ".join(record.get("prerequisites", [])) or "—",
            })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=400)

    st.divider()
    st.subheader("Propagate a rate change")
    st.caption(
        "Pick a course and a hypothetical new effective rate for it (e.g. \"what if a "
        "teaching change pushed CMPS151's pass rate up 15 points?\") and see how that "
        "ripples forward through every course that has it as a prerequisite, directly or "
        "through a chain."
    )

    col1, col2 = st.columns(2)
    with col1:
        target_course = st.selectbox(
            "Course", options=sorted(courses.keys()),
            format_func=lambda c: f"{c} — {courses[c]['name']}",
        )
    current_rate = sr.effective_rate(courses, demand_history, config, target_course, term=None, weight=weight)
    with col2:
        new_rate = st.slider(
            f"New effective rate for {target_course} (current: {current_rate:.2f})",
            0.01, 0.99, float(round(current_rate, 2)), step=0.01,
        )

    if st.button("Propagate", type="primary"):
        result = sr.propagate_rate_change(courses, demand_history, config, target_course, new_rate, weight=weight)
        if not result["affected_courses"]:
            st.info(f"No course in the curriculum lists {target_course} as a prerequisite (directly or indirectly) — nothing downstream to affect.")
        else:
            fig = go.Figure()
            top = result["affected_courses"][:15]
            fig.add_trace(go.Bar(name="Before", x=[r["course"] for r in top], y=[r["before"] for r in top]))
            fig.add_trace(go.Bar(name="After", x=[r["course"] for r in top], y=[r["after"] for r in top]))
            fig.update_layout(
                barmode="group",
                title=f"Downstream effective-rate shift from changing {target_course} ({current_rate:.2f} → {new_rate:.2f})",
                yaxis_title="Effective pass rate",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(pd.DataFrame(result["affected_courses"]), use_container_width=True)
            st.write(f"**{result['affected_students_pct']:.1f}%** of students had a different graduation term without summer offerings.")
