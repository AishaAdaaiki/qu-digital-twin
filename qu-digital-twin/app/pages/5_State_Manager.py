import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from app.state_session import get_current_state, set_current_state, reset_to_baseline

st.set_page_config(page_title="State Manager", page_icon="🗄️", layout="wide")
st.title("🗄️ State Manager")
st.caption(
    "L1/L4 — this is 'the department right now'. Every engine reads from this state. "
    "Upload a real file to replace any single domain; anything you don't upload keeps "
    "using the bundled mock data. Nothing here calls an LLM."
)

state = get_current_state()

st.subheader(f"Active state: **{state.label}**")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Courses", len(state.courses))
col2.metric("Electives (catalog)", len(state.elective_catalog))
col3.metric("Faculty", len(state.faculty))
col4.metric("Rooms", len(state.rooms))
col5.metric("Courses w/ demand history", len(state.demand_history))

if st.button("Reset to bundled baseline"):
    reset_to_baseline()
    st.rerun()

st.divider()
st.subheader("Replace a data domain")
st.caption(
    "Each domain is an independent JSON file with the schema documented in "
    "docs/department_simulation_architecture.md §3. Upload a replacement for just "
    "the domain(s) you have real data for."
)

DOMAIN_FIELDS = {
    "courses": "Courses (program requirement graph)",
    "elective_catalog": "Elective catalog (concrete elective offerings)",
    "faculty": "Faculty roster",
    "rooms": "Room inventory",
    "demand_history": "Demand history (enrollment by term)",
    "accreditation_rules": "Accreditation rules",
    "substitution_rules": "Substitution rules",
    "mock_schedule": "Mock section schedule",
    "simulation_config": "Cohort simulation config",
}

uploaded_any = False
cols = st.columns(3)
for i, (field, description) in enumerate(DOMAIN_FIELDS.items()):
    with cols[i % 3]:
        file = st.file_uploader(description, type="json", key=f"upload_{field}")
        if file is not None:
            uploaded_any = True
            try:
                content = json.load(file)
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
                json.dump(content, tmp)
                tmp.close()
                setattr(state, field, {k: v for k, v in content.items() if not str(k).startswith("_")}
                        if isinstance(content, dict) else content)
                st.success(f"{description} replaced ({len(content) if hasattr(content, '__len__') else '?'} entries).")
            except Exception as e:
                st.error(f"Couldn't parse {file.name}: {e}")

if uploaded_any:
    set_current_state(state)
    st.info("State updated for this session. Visit any engine page to see it reflected.")

st.divider()
st.subheader("Inspect current data")
domain_choice = st.selectbox("Domain", options=list(DOMAIN_FIELDS.keys()), format_func=lambda k: DOMAIN_FIELDS[k])
data = getattr(state, domain_choice)
if isinstance(data, dict):
    st.json(data, expanded=False)
else:
    st.json(data)
