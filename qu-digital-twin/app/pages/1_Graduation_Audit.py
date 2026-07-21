import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses
from backend.rule_engine import graduation_audit

st.set_page_config(page_title="Graduation Audit", page_icon="📋", layout="wide")
st.title("📋 Graduation Audit")
st.caption("M2 — thin wrapper over backend.rule_engine.graduation_audit(). No logic lives here.")

courses = load_courses()
all_codes = sorted(courses.keys())

completed = st.multiselect(
    "Completed courses",
    options=all_codes,
    format_func=lambda c: f"{c} — {courses[c]['name']}",
)

if st.button("Run audit", type="primary"):
    result = graduation_audit(completed, courses)

    col1, col2, col3 = st.columns(3)
    col1.metric("Completed credits", result["completed_credits"])
    col2.metric("Remaining credits", result["remaining_credits"])
    col3.metric("Total program credits", result["total_program_credits"])

    if result["unknown_completed"]:
        st.warning(f"Unrecognized course codes ignored: {', '.join(result['unknown_completed'])}")

    st.subheader("Remaining requirements by category")
    for category, codes in sorted(result["remaining_by_category"].items()):
        with st.expander(f"{category} ({len(codes)} courses)"):
            for code in codes:
                st.write(f"**{code}** — {courses[code]['name']} ({courses[code]['credits']} cr)")

    st.subheader("Structural status")
    if result["on_track"]:
        st.success("No structural dead ends detected among remaining courses.")
    else:
        st.error("Structural issue detected in the remaining course graph — check courses.json.")
else:
    st.info("Select completed courses and click **Run audit**.")
