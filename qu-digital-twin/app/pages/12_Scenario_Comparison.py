import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import accreditation
from backend.engines.faculty import auto_assign_faculty
from backend.engines.space import auto_schedule_rooms
from app.state_session import get_current_state, get_saved_scenarios, save_scenario

st.set_page_config(page_title="Scenario Comparison", page_icon="⚖️", layout="wide")
st.title("⚖️ Scenario Comparison")
st.caption("Baseline vs. one or more saved scenarios, side by side, across all four analysis engines plus compliance.")

state = get_current_state()
scenarios = get_saved_scenarios()

if "Baseline" not in scenarios:
    from backend.state import load_state
    save_scenario(load_state(), "Baseline")
    scenarios = get_saved_scenarios()

if not scenarios:
    st.info("No scenarios saved yet. Build one in Propose a Change or Org Structure, then come back here.")
    st.stop()

selected = st.multiselect("Scenarios to compare", options=list(scenarios.keys()), default=list(scenarios.keys())[:2])
term = st.selectbox("Term", options=["fall", "spring"])

if not selected:
    st.info("Pick at least one scenario.")
    st.stop()

rows = []
for label in selected:
    s = scenarios[label]
    sc = accreditation.compliance_scorecard(s)
    fac = auto_assign_faculty(s, term)
    room = auto_schedule_rooms(s, term)
    rows.append({
        "Scenario": label,
        "Total courses": len(s.courses),
        "Total credit hours": sum(c["credits"] for c in s.courses.values()),
        "Faculty count": len(s.faculty),
        "Room count": len(s.rooms),
        "Compliance checks passed": f"{sc['summary']['passed']}/{sc['summary']['total_checks']}",
        "Fully compliant": sc["summary"]["fully_compliant"],
        "Unteachable courses": len(fac["unteachable_courses"]),
        "Rooms unavailable for": len(room["infeasible_courses"]),
    })

df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True)

fig = go.Figure()
for label in selected:
    s = scenarios[label]
    sc = accreditation.compliance_scorecard(s)
    categories = [c["rule"].replace("min_credit_hours[", "").rstrip("]") for c in sc["credit_hour_checks"]]
    values = [c["actual"] for c in sc["credit_hour_checks"]]
    fig.add_trace(go.Bar(name=label, x=categories, y=values))
fig.update_layout(barmode="group", title="Credit hours by category, across scenarios")
st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Delete a saved scenario")
to_delete = st.selectbox("Scenario", options=[s for s in scenarios if s != "Baseline"] or ["(none deletable)"])
if scenarios and to_delete in scenarios and st.button("Delete"):
    del scenarios[to_delete]
    st.rerun()
