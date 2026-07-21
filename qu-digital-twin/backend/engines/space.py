"""
M12 - Physical Space & Resources engine.

Reads backend.state.DepartmentState.rooms + .courses and answers room-capacity
and scheduling-feasibility questions (docs/department_simulation_architecture.md
§4.3). Simplification, documented here rather than hidden: a room can host up to
`SLOTS_PER_ROOM_PER_TERM` different course sections per term (a proxy for
"morning / midday / afternoon" time blocks), since exact meeting-time scheduling
is already handled at the individual-student level by M3's detect_conflicts() /
mock_schedule.json - this engine reasons about aggregate room capacity, not a
literal timetable.

Same two-kind-of-function split as faculty.py: analysis functions are pure and
read-only; apply_* functions return a new DepartmentState via state.copy().
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.state import DepartmentState, GENERIC_SLOT_CODES

SLOTS_PER_ROOM_PER_TERM = 3


def _courses_offered(state: DepartmentState, term: str) -> List[str]:
    return [
        code for code, rec in state.courses.items()
        if term in rec.get("offered", []) and code not in GENERIC_SLOT_CODES
    ]


def _course_seat_need(state: DepartmentState, code: str) -> int:
    rec = state.courses[code]
    if rec.get("seat_capacity"):
        return rec["seat_capacity"]
    hist = state.demand_history.get(code, {})
    if hist:
        latest = sorted(hist.keys())[-1]
        return hist[latest]["capacity"]
    return 30  # fallback default


def auto_schedule_rooms(state: DepartmentState, term: str) -> dict:
    """
    Greedy best-fit: for each course offered this term (largest seat-need first),
    assign the smallest available room of the right type/equipment that still
    fits it, respecting SLOTS_PER_ROOM_PER_TERM. Courses with `requires_room_type`
    unset default to 'lecture'. Returns the assignment plus any infeasible courses.
    """
    courses = _courses_offered(state, term)
    room_usage: Dict[str, int] = {rid: 0 for rid in state.rooms}
    assignment: Dict[str, Optional[str]] = {}
    infeasible = []

    ordered = sorted(courses, key=lambda c: -_course_seat_need(state, c))
    for code in ordered:
        rec = state.courses[code]
        room_type = rec.get("requires_room_type", "lecture")
        equipment = set(rec.get("equipment_needed", []))
        seats_needed = _course_seat_need(state, code)

        candidates = [
            rid for rid, r in state.rooms.items()
            if r["room_type"] == room_type
            and equipment.issubset(set(r.get("equipment", [])))
            and r["capacity"] >= seats_needed
            and room_usage[rid] < SLOTS_PER_ROOM_PER_TERM
        ]
        if not candidates:
            assignment[code] = None
            infeasible.append({
                "course": code, "name": rec["name"], "room_type_needed": room_type,
                "equipment_needed": sorted(equipment), "seats_needed": seats_needed,
            })
            continue

        # best-fit: smallest room that still fits, to leave bigger rooms free
        chosen = min(candidates, key=lambda rid: state.rooms[rid]["capacity"])
        assignment[code] = chosen
        room_usage[chosen] += 1

    return {"term": term, "assignment": assignment, "infeasible_courses": infeasible, "room_usage": room_usage}


def room_utilization_report(state: DepartmentState, term: str) -> List[dict]:
    result = auto_schedule_rooms(state, term)
    report = []
    for rid, room in state.rooms.items():
        used = result["room_usage"].get(rid, 0)
        report.append({
            "room": rid, "building": room["building"], "room_type": room["room_type"],
            "capacity": room["capacity"], "sections_scheduled": used,
            "slots_available": SLOTS_PER_ROOM_PER_TERM,
            "utilization": round(used / SLOTS_PER_ROOM_PER_TERM, 2),
        })
    return sorted(report, key=lambda r: -r["utilization"])


def capacity_shortfall_by_type(state: DepartmentState, term: str) -> List[dict]:
    """Aggregate demand vs. supply per room type - how many more course-sections
    of each type could be absorbed, or how many are short, this term."""
    result = auto_schedule_rooms(state, term)
    by_type_supply: Dict[str, int] = {}
    for room in state.rooms.values():
        by_type_supply[room["room_type"]] = by_type_supply.get(room["room_type"], 0) + SLOTS_PER_ROOM_PER_TERM

    by_type_used: Dict[str, int] = {}
    for code, rid in result["assignment"].items():
        if rid:
            rtype = state.rooms[rid]["room_type"]
            by_type_used[rtype] = by_type_used.get(rtype, 0) + 1

    by_type_shortfall: Dict[str, int] = {}
    for c in result["infeasible_courses"]:
        by_type_shortfall[c["room_type_needed"]] = by_type_shortfall.get(c["room_type_needed"], 0) + 1

    all_types = set(by_type_supply) | set(by_type_used) | set(by_type_shortfall)
    return [
        {
            "room_type": t,
            "total_capacity_slots": by_type_supply.get(t, 0),
            "slots_used": by_type_used.get(t, 0),
            "unmet_demand_sections": by_type_shortfall.get(t, 0),
        }
        for t in sorted(all_types)
    ]


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

def apply_add_room(state: DepartmentState, room_id: str, record: dict) -> DepartmentState:
    new_state = state.copy()
    new_state.rooms[room_id] = record
    return new_state


def apply_remove_room(state: DepartmentState, room_id: str) -> DepartmentState:
    if room_id not in state.rooms:
        raise ValueError(f"Unknown room_id '{room_id}'")
    new_state = state.copy()
    del new_state.rooms[room_id]
    return new_state


def apply_resize_room(state: DepartmentState, room_id: str, new_capacity: int) -> DepartmentState:
    if room_id not in state.rooms:
        raise ValueError(f"Unknown room_id '{room_id}'")
    new_state = state.copy()
    new_state.rooms[room_id]["capacity"] = new_capacity
    return new_state
