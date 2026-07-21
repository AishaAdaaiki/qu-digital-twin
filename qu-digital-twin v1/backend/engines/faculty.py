"""
M11 - Faculty & Staffing engine.

Reads backend.state.DepartmentState.faculty + .courses and answers workload and
hiring questions (docs/department_simulation_architecture.md §4.2). Like the rest
of the system, this models one section per offered course per term (matching how
M3/M4 already work) rather than a full multi-section timetable.

Two kinds of function here:
  - Analysis (workload_report, auto_assign_faculty, hiring_impact) - pure, read-only.
  - Moves (apply_add_faculty, apply_remove_faculty, apply_set_faculty_status) - each
    returns a NEW DepartmentState via state.copy(), never mutating the original.
    These are what backend/interventions.py dispatches to.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.state import DepartmentState, GENERIC_SLOT_CODES


def _courses_offered(state: DepartmentState, term: str) -> List[str]:
    return [
        code for code, rec in state.courses.items()
        if term in rec.get("offered", []) and code not in GENERIC_SLOT_CODES
    ]


def auto_assign_faculty(state: DepartmentState, term: str) -> dict:
    """
    Greedy assignment: for each course offered this term, assign the
    least-loaded active faculty member who is qualified for it. Courses with no
    eligible instructor (none qualified, or all qualified instructors already at
    max_courses_per_term) come back as 'unteachable'.
    """
    courses = _courses_offered(state, term)
    load: Dict[str, int] = {fid: 0 for fid, f in state.faculty.items() if f.get("status") == "active"}
    assignment: Dict[str, Optional[str]] = {}
    unteachable = []

    # stable order: courses with fewer qualified instructors get assigned first,
    # so a scarce specialist isn't accidentally used up on a course with plenty
    # of other options.
    def n_qualified(code):
        return sum(1 for fid, f in state.faculty.items() if code in f.get("qualified_courses", []) and f.get("status") == "active")

    for code in sorted(courses, key=n_qualified):
        candidates = [
            fid for fid, f in state.faculty.items()
            if f.get("status") == "active"
            and code in f.get("qualified_courses", [])
            and load[fid] < f.get("max_courses_per_term", 0)
        ]
        if not candidates:
            assignment[code] = None
            unteachable.append(code)
            continue
        chosen = min(candidates, key=lambda fid: load[fid])
        assignment[code] = chosen
        load[chosen] += 1

    return {
        "term": term,
        "assignment": assignment,
        "unteachable_courses": unteachable,
        "faculty_load": load,
    }


def workload_report(state: DepartmentState, term: str) -> List[dict]:
    """Per active faculty member: assigned course count vs. max_courses_per_term,
    flagged over/under/at capacity."""
    result = auto_assign_faculty(state, term)
    report = []
    for fid, f in state.faculty.items():
        if f.get("status") != "active":
            continue
        assigned = result["faculty_load"].get(fid, 0)
        max_load = f.get("max_courses_per_term", 0)
        status = "overloaded" if assigned > max_load else ("underused" if assigned < max_load * 0.5 else "at_capacity")
        report.append({
            "faculty_id": fid, "name": f.get("name"), "rank": f.get("rank"),
            "assigned_courses": assigned, "max_courses_per_term": max_load, "status": status,
        })
    return sorted(report, key=lambda r: -r["assigned_courses"])


def student_faculty_ratio_trend(state: DepartmentState) -> dict:
    """Active faculty FTE now vs. a simple headcount proxy (see accreditation.py's
    check_student_faculty_ratio for the same assumption, reused here for the
    Faculty & Staffing dashboard rather than the compliance page)."""
    from backend.engines.accreditation import check_student_faculty_ratio
    return check_student_faculty_ratio(state)


def hiring_impact(state: DepartmentState, new_faculty: dict, term: str) -> dict:
    """
    What would adding one hypothetical faculty member unlock? Runs auto_assign
    on the current state and on a copy with the new hire added, and reports the
    difference in unteachable courses - without touching the real roster.
    """
    before = auto_assign_faculty(state, term)
    after_state = apply_add_faculty(state, faculty_id="_HYPOTHETICAL_", record=new_faculty)
    after = auto_assign_faculty(after_state, term)

    newly_teachable = sorted(set(before["unteachable_courses"]) - set(after["unteachable_courses"]))
    return {
        "term": term,
        "unteachable_before": before["unteachable_courses"],
        "unteachable_after": after["unteachable_courses"],
        "newly_teachable_courses": newly_teachable,
        "hire_taught_courses": [c for c, fid in after["assignment"].items() if fid == "_HYPOTHETICAL_"],
    }


# ---------------------------------------------------------------------------
# Moves - each returns a new DepartmentState, original untouched.
# ---------------------------------------------------------------------------

def apply_add_faculty(state: DepartmentState, faculty_id: str, record: dict) -> DepartmentState:
    new_state = state.copy()
    new_state.faculty[faculty_id] = record
    return new_state


def apply_remove_faculty(state: DepartmentState, faculty_id: str) -> DepartmentState:
    if faculty_id not in state.faculty:
        raise ValueError(f"Unknown faculty_id '{faculty_id}'")
    new_state = state.copy()
    del new_state.faculty[faculty_id]
    return new_state


def apply_set_faculty_status(state: DepartmentState, faculty_id: str, status: str) -> DepartmentState:
    if faculty_id not in state.faculty:
        raise ValueError(f"Unknown faculty_id '{faculty_id}'")
    if status not in ("active", "on_leave", "sabbatical"):
        raise ValueError(f"Unknown status '{status}'")
    new_state = state.copy()
    new_state.faculty[faculty_id]["status"] = status
    return new_state
