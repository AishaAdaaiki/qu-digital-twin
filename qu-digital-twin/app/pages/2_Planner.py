import sys
from json import load as json_load
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses
from backend.planner import plan_term, detect_conflicts

st.set_page_config(page_title="Planner", page_icon="🗓️", layout="wide")
st.title("🗓️ Term Planner")
st.caption("M3 — thin wrapper over backend.planner.plan_term() and detect_conflicts(). No logic lives here.")

courses = load_courses()
all_codes = sorted(courses.keys())

with open(Path(__file__).parent.parent.parent / "backend" / "data" / "mock_schedule.json") as f:
    schedule = {k: v for k, v in json_load(f).items() if not k.startswith("_")}

completed = st.multiselect(
    "Completed courses",
    options=all_codes,
    format_func=lambda c: f"{c} — {courses[c]['name']}",
    key="planner_completed",
)

col1, col2, col3 = st.columns(3)
with col1:
    term = st.selectbox("Term to plan for", options=["fall", "spring", "summer"])
with col2:
    max_credits = st.slider("Max credits", min_value=9, max_value=18, value=15)
with col3:
    min_credits = st.slider("Min credits (informational)", min_value=0, max_value=18, value=12)

avoid = st.multiselect("Courses to avoid this term", options=all_codes)

if st.button("Generate plan", type="primary"):
    preferences = {
        "term": term,
        "max_credits": max_credits,
        "min_credits": min_credits,
        "avoid_courses": avoid,
    }
    plan = plan_term(completed, preferences, courses, max_credits=max_credits)
    conflicts = detect_conflicts(plan, completed, courses, schedule)

    total_credits = sum(courses[c]["credits"] for c in plan)

    st.subheader(f"Proposed {term} schedule — {total_credits} credits")
    if plan:
        st.table(
            [{"Course": c, "Name": courses[c]["name"], "Credits": courses[c]["credits"],
              "Category": courses[c].get("category", "-")} for c in plan]
        )
    else:
        st.warning("No eligible courses found for this term given the completed list and constraints.")

    if total_credits < min_credits:
        st.info(f"This plan is under your stated minimum of {min_credits} credits — "
                f"there may not be enough eligible courses offered this term.")

    st.subheader("Conflict check")
    if conflicts:
        st.error(f"{len(conflicts)} conflict(s) found:")
        for c in conflicts:
            st.write(f"- **{c['type']}** — {c['detail']}")
    else:
        st.success("No conflicts detected.")
else:
    st.info("Set your completed courses and preferences, then click **Generate plan**.")
