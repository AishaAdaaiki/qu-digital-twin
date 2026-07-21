import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.engines import space as space_engine
from app.state_session import get_current_state, set_current_state

st.set_page_config(page_title="Physical Space", page_icon="🏫", layout="wide")
st.title("🏫 Physical Space & Resources")
st.caption(
    f"M12 — thin wrapper over backend.engines.space. Models up to "
    f"{space_engine.SLOTS_PER_ROOM_PER_TERM} sections per room per term (a proxy "
    "for time-of-day slots), not a literal timetable."
)

state = get_current_state()

tab_util, tab_shortfall, tab_rooms = st.tabs(["Room Utilization", "Capacity Shortfall", "Add/Resize Rooms"])

with tab_util:
    term = st.selectbox("Term", options=["fall", "spring"], key="space_term")
    result = space_engine.auto_schedule_rooms(state, term)
    if result["infeasible_courses"]:
        st.error(f"{len(result['infeasible_courses'])} course(s) have no room this term:")
        st.dataframe(pd.DataFrame(result["infeasible_courses"]), use_container_width=True)
    else:
        st.success("Every course was assigned a room this term.")

    util = space_engine.room_utilization_report(state, term)
    df = pd.DataFrame(util)
    fig = px.bar(df, x="room", y="utilization", color="room_type", title=f"Room utilization — {term}",
                 hover_data=["building", "capacity", "sections_scheduled"])
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)

with tab_shortfall:
    term_sf = st.selectbox("Term", options=["fall", "spring"], key="shortfall_term")
    shortfall = space_engine.capacity_shortfall_by_type(state, term_sf)
    df = pd.DataFrame(shortfall)
    fig = px.bar(df, x="room_type", y=["slots_used", "unmet_demand_sections"], barmode="group",
                 title=f"Supply vs. unmet demand by room type — {term_sf}")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)

with tab_rooms:
    action = st.selectbox("Action", ["Add room", "Resize room", "Remove room"])
    if action == "Add room":
        col1, col2 = st.columns(2)
        with col1:
            room_id = st.text_input("Room ID", value="NEW_ROOM_1")
            building = st.text_input("Building", value="Engineering Building")
            capacity = st.number_input("Capacity", min_value=1, value=30)
        with col2:
            room_type = st.selectbox("Room type", ["lecture", "lab", "seminar"])
            equipment = st.text_input("Equipment (comma-separated)", value="desktop_workstations")
            cost = st.number_input("Operating cost/term (QAR)", min_value=0, value=12000)
        if st.button("Add room", type="primary"):
            record = {
                "building": building, "capacity": capacity, "room_type": room_type,
                "equipment": [e.strip() for e in equipment.split(",") if e.strip()],
                "operating_cost_per_term_qar": cost,
            }
            new_state = space_engine.apply_add_room(state, room_id, record)
            set_current_state(new_state)
            st.success(f"{room_id} added.")
            st.rerun()

    elif action == "Resize room":
        room_id = st.selectbox("Room", options=sorted(state.rooms.keys()))
        new_capacity = st.number_input("New capacity", min_value=1, value=state.rooms[room_id]["capacity"])
        if st.button("Resize", type="primary"):
            new_state = space_engine.apply_resize_room(state, room_id, new_capacity)
            set_current_state(new_state)
            st.success(f"{room_id} resized to {new_capacity}.")
            st.rerun()

    else:
        room_id = st.selectbox("Room to remove", options=sorted(state.rooms.keys()))
        if st.button("Remove", type="primary"):
            new_state = space_engine.apply_remove_room(state, room_id)
            set_current_state(new_state)
            st.success(f"{room_id} removed.")
            st.rerun()
