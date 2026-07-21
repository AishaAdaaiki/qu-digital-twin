import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from backend.engines import space as space_engine

STATE = load_state()


def test_generic_slot_codes_excluded_from_scheduling():
    result = space_engine.auto_schedule_rooms(STATE, "fall")
    for slot in ("ELEC1", "ELEC2", "ELEC3", "ELEC4"):
        assert slot not in result["assignment"]


def test_no_room_double_booked_beyond_slot_limit():
    result = space_engine.auto_schedule_rooms(STATE, "fall")
    for rid, used in result["room_usage"].items():
        assert used <= space_engine.SLOTS_PER_ROOM_PER_TERM


def test_assigned_room_matches_type_and_equipment():
    result = space_engine.auto_schedule_rooms(STATE, "fall")
    for code, rid in result["assignment"].items():
        if rid is None:
            continue
        room = STATE.rooms[rid]
        course = STATE.courses[code]
        assert room["room_type"] == course.get("requires_room_type", "lecture")
        assert set(course.get("equipment_needed", [])).issubset(set(room["equipment"]))
        assert room["capacity"] >= space_engine._course_seat_need(STATE, code)


def test_adding_a_room_can_resolve_an_infeasible_course():
    before = space_engine.auto_schedule_rooms(STATE, "fall")
    before_infeasible = {c["course"] for c in before["infeasible_courses"]}
    assert "CMPS303" in before_infeasible  # known bottleneck given current mock room sizes

    bigger_state = space_engine.apply_add_room(STATE, "ENG_LAB_BIG", {
        "building": "Engineering Building", "capacity": 40, "room_type": "lab",
        "equipment": ["desktop_workstations"], "operating_cost_per_term_qar": 16000,
    })
    after = space_engine.auto_schedule_rooms(bigger_state, "fall")
    after_infeasible = {c["course"] for c in after["infeasible_courses"]}
    assert "CMPS303" not in after_infeasible
    assert "ENG_LAB_BIG" not in STATE.rooms  # original untouched


def test_capacity_shortfall_report_totals_are_consistent():
    report = space_engine.capacity_shortfall_by_type(STATE, "fall")
    for row in report:
        assert row["slots_used"] <= row["total_capacity_slots"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
