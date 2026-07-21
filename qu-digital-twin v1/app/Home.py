import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(page_title="QU Digital Twin", page_icon="🎓", layout="wide")

st.title("🎓 QU Digital Twin")
st.caption("Full-Lifecycle Student Flow Simulator with AI Advising Layer — CS BSc, Qatar University")

st.markdown(
    """
This system models the full journey of a QU CS student — from enrollment to
graduation — and wraps it in an LLM-based advising agent. One JSON backbone
(`backend/data/courses.json`) feeds every module below; nothing is hardcoded twice.
"""
)

st.subheader("Architecture")
st.code(
    """
Layer 1 — Data (M1)         courses.json: single source of truth, read-only at runtime
Layer 2 — Rule Engine (M2/M3) graduation_audit, substitution_check, plan_term, detect_conflicts
                               Pure functions. No LLM calls.
Layer 3 — Simulation (M4/M5)  Runs Layer 2 thousands of times over synthetic cohorts.
                               Produces bottleneck heatmaps, graduation-time distributions,
                               stress-test deltas. No LLM calls.
Layer 4 — Agent (M6/M7)       The only layer that uses an LLM. Takes natural language,
                               calls Layer 2 functions as tools, never invents an answer.
""",
    language="text",
)

st.subheader("Quick start — student advising")
st.markdown(
    """
1. **Graduation Audit** — see what you have left, given your completed courses.
2. **Planner** — build a valid next-term schedule and check it for conflicts.
3. **Simulation** — see where a whole cohort gets stuck, and what-if scenarios.
4. **Advisor Chat** — ask the LLM advisor questions; it always calls the rule engine.
"""
)

st.subheader("Quick start — department planning")
st.markdown(
    """
5. **State Manager** — load or replace the department's data (courses, faculty, rooms,
   demand history, accreditation rules). Everything below reads from here.
6. **Demand Forecasting** — enrollment trends, oversubscription, and the new-elective
   feasibility check (name + description in, similarity-matched demand/faculty/room
   feasibility out).
7. **Accreditation** — a compliance scorecard against credit-hour, class-size, and
   staffing-ratio policy, for whatever state is currently active.
8. **Faculty & Staffing** — workload, hiring simulation, roster changes.
9. **Physical Space** — room utilization, capacity shortfalls, add/resize rooms.
10. **Org Structure** — new minor/concentration feasibility, program-split impact,
    retiring or promoting a course.
11. **Propose a Change** — build a single move, or bundle several, and apply them
    together as one named scenario.
12. **Scenario Comparison** — baseline vs. saved scenarios, side by side.
"""
)

st.info(
    "The Advisor Chat page needs an API key. Copy `.env.example` to `.env` — the "
    "default provider is Groq, which has a free tier (get a key at "
    "console.groq.com/keys). Anthropic and OpenAI also work if you set "
    "`LLM_PROVIDER` accordingly.",
    icon="🔑",
)
