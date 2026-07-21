import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.interventions import apply_bundle
from app.state_session import get_current_state, set_current_state, save_scenario

st.set_page_config(page_title="Propose a Change", page_icon="🛠️", layout="wide")
st.title("🛠️ Propose a Change")
st.caption(
    "L3 — build one intervention, or stack several into a bundle, then apply them together "
    "as a single scenario. Nothing here mutates your current state until you click Apply."
)

state = get_current_state()

if "pending_bundle" not in st.session_state:
    st.session_state.pending_bundle = []

move_type = st.selectbox(
    "Move type",
    options=[
        "add_faculty", "remove_faculty", "set_faculty_status",
        "add_room", "remove_room", "resize_room",
        "change_course_category", "promote_elective_to_program", "retire_course",
    ],
)

intervention = {"type": move_type}

if move_type == "add_faculty":
    fid = st.text_input("New faculty ID", value="F_NEW")
    name = st.text_input("Name", value="Dr. New Hire")
    rank = st.selectbox("Rank", ["lecturer", "assistant_professor", "associate_professor", "full_professor", "adjunct"])
    max_courses = st.slider("Max courses/term", 1, 5, 3)
    qualified = st.multiselect("Qualified courses", options=sorted(state.courses.keys()))
    specializations = st.text_input("Specializations (comma-separated)", value="")
    intervention.update(faculty_id=fid, record={
        "name": name, "rank": rank, "fte": 1.0, "max_courses_per_term": max_courses,
        "qualified_courses": qualified, "specializations": [s.strip() for s in specializations.split(",") if s.strip()],
        "status": "active", "annual_salary_qar": 300000,
    })

elif move_type == "remove_faculty":
    fid = st.selectbox("Faculty", options=sorted(state.faculty.keys()), format_func=lambda f: f"{f} — {state.faculty[f]['name']}")
    intervention.update(faculty_id=fid)

elif move_type == "set_faculty_status":
    fid = st.selectbox("Faculty", options=sorted(state.faculty.keys()), format_func=lambda f: f"{f} — {state.faculty[f]['name']}")
    status = st.selectbox("New status", ["active", "on_leave", "sabbatical"])
    intervention.update(faculty_id=fid, status=status)

elif move_type == "add_room":
    rid = st.text_input("New room ID", value="NEW_ROOM")
    building = st.text_input("Building", value="Engineering Building")
    capacity = st.number_input("Capacity", min_value=1, value=30)
    room_type = st.selectbox("Room type", ["lecture", "lab", "seminar"])
    equipment = st.text_input("Equipment (comma-separated)", value="")
    intervention.update(room_id=rid, record={
        "building": building, "capacity": capacity, "room_type": room_type,
        "equipment": [e.strip() for e in equipment.split(",") if e.strip()],
        "operating_cost_per_term_qar": 12000,
    })

elif move_type == "remove_room":
    rid = st.selectbox("Room", options=sorted(state.rooms.keys()))
    intervention.update(room_id=rid)

elif move_type == "resize_room":
    rid = st.selectbox("Room", options=sorted(state.rooms.keys()))
    new_capacity = st.number_input("New capacity", min_value=1, value=state.rooms[rid]["capacity"])
    intervention.update(room_id=rid, new_capacity=new_capacity)

elif move_type == "change_course_category":
    code = st.selectbox("Course", options=sorted(state.courses.keys()))
    new_category = st.selectbox("New category", ["major_core", "major_supporting", "college", "core_curriculum", "major_elective"])
    intervention.update(code=code, new_category=new_category)

elif move_type == "promote_elective_to_program":
    code = st.selectbox("Elective", options=sorted(state.elective_catalog.keys()))
    intervention.update(code=code)

elif move_type == "retire_course":
    code = st.selectbox("Course", options=sorted(state.courses.keys()))
    intervention.update(code=code)

if st.button("Add to bundle"):
    st.session_state.pending_bundle.append(intervention)

st.divider()
st.subheader(f"Pending bundle ({len(st.session_state.pending_bundle)} move(s))")
for i, iv in enumerate(st.session_state.pending_bundle):
    col1, col2 = st.columns([5, 1])
    col1.json(iv, expanded=False)
    if col2.button("Remove", key=f"remove_{i}"):
        st.session_state.pending_bundle.pop(i)
        st.rerun()

col1, col2 = st.columns(2)
scenario_label = col1.text_input("Scenario label", value="New scenario")
if col2.button("Apply bundle", type="primary", disabled=not st.session_state.pending_bundle):
    try:
        new_state = apply_bundle(state, st.session_state.pending_bundle, label=scenario_label)
        set_current_state(new_state)
        save_scenario(new_state, scenario_label)
        st.session_state.pending_bundle = []
        st.success(f"Applied and saved as '{scenario_label}'. This is now your active state.")
        st.rerun()
    except ValueError as e:
        st.error(str(e))
