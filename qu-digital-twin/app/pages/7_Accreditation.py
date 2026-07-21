import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import accreditation
from app.state_session import get_current_state

st.set_page_config(page_title="Accreditation & Compliance", page_icon="✅", layout="wide")
st.title("✅ Accreditation & Compliance")
st.caption(
    "M10 — a validator, not a move. Runs against whatever state is currently active "
    "(see State Manager / Propose a Change), so any proposed intervention's compliance "
    "impact is visible here immediately."
)

state = get_current_state()
total_students_override = st.number_input(
    "Total students (leave at 0 to use the CMPS151-based estimate)", min_value=0, value=0, step=10
)
scorecard = accreditation.compliance_scorecard(
    state, total_students=total_students_override or None
)

summary = scorecard["summary"]
c1, c2, c3 = st.columns(3)
c1.metric("Checks passed", f"{summary['passed']} / {summary['total_checks']}")
c2.metric("Fully compliant", "Yes" if summary["fully_compliant"] else "No")
c3.metric("State", scorecard["state_label"])

st.subheader("Credit-hour category minimums")
df = pd.DataFrame(scorecard["credit_hour_checks"])
fig = go.Figure()
fig.add_trace(go.Bar(x=df["rule"], y=df["actual"], name="Actual"))
fig.add_trace(go.Bar(x=df["rule"], y=df["required"], name="Required minimum", opacity=0.5))
fig.update_layout(barmode="overlay", title="Actual vs. required credit hours by category")
st.plotly_chart(fig, use_container_width=True)
st.dataframe(df[["rule", "actual", "required", "pass"]], use_container_width=True)

st.subheader("Class size vs. room-type policy")
if scorecard["class_size_checks"]:
    st.dataframe(pd.DataFrame(scorecard["class_size_checks"])[["course", "actual", "required", "pass", "detail"]], use_container_width=True)
else:
    st.info("No courses have both seat_capacity and requires_room_type set to check.")

st.subheader("Student-faculty ratio")
ratio = scorecard["student_faculty_ratio_check"]
st.write(ratio["detail"])
st.write("✅ Within policy" if ratio["pass"] else "⚠️ Exceeds policy")
