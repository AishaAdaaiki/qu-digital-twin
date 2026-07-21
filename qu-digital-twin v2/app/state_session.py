"""
Frontend-side session-state helpers shared by the department-simulation pages
(State Manager, Demand/Accreditation/Faculty/Space/Org, Scenario Comparison).

Keeps two things in st.session_state:
  - "dept_state": the current working DepartmentState (starts as the bundled
    mock baseline, replaced by uploads in State Manager, or by applying an
    intervention in Propose a Change)
  - "dept_scenarios": a dict of {label: DepartmentState} the user has explicitly
    saved for side-by-side comparison later

Nothing here talks to an LLM or does any analysis - it's purely session plumbing
so the multi-page Streamlit app shares one state object instead of every page
reloading the mock defaults independently.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.state import load_state, DepartmentState


def get_current_state() -> DepartmentState:
    if "dept_state" not in st.session_state:
        st.session_state.dept_state = load_state()
    return st.session_state.dept_state


def set_current_state(state: DepartmentState) -> None:
    st.session_state.dept_state = state


def get_saved_scenarios() -> dict:
    if "dept_scenarios" not in st.session_state:
        st.session_state.dept_scenarios = {}
    return st.session_state.dept_scenarios


def save_scenario(state: DepartmentState, label: str) -> None:
    scenarios = get_saved_scenarios()
    state.label = label
    scenarios[label] = state


def reset_to_baseline() -> None:
    st.session_state.dept_state = load_state(label="Baseline")
