"""
M13 - Org Structure & Curriculum Design engine.

The most complex of the five (docs/department_simulation_architecture.md §4.4) and
deliberately built as a *reuse* layer over M9-M12 rather than its own separate
model: a new minor's feasibility is just M9's resourcing legs run per-course, a
program split's impact is just the credit-hour and faculty-overlap math over two
course subsets, a retirement's impact is M9's simulate_retirement plus an
affected-student estimate.

Honest limitation: courses.json models exactly one program. A "split" here is an
analysis (what WOULD happen, credit hours and faculty overlap both sides) rather
than a Move that produces two live DepartmentStates, since that would need a
bigger schema change (multi-program support) than this pass includes - see
docs/department_simulation_architecture.md for the flagged follow-up.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.engines import demand as demand_engine
from backend.engines.accreditation import check_credit_hour_minimums
from backend.engines.faculty import auto_assign_faculty
from backend.engines.space import auto_schedule_rooms
from backend.state import DepartmentState


def _course_lookup(state: DepartmentState, code: str) -> Optional[dict]:
    return state.courses.get(code) or state.elective_catalog.get(code)


def new_minor_feasibility(state: DepartmentState, minor_name: str, course_codes: List[str]) -> dict:
    """
    Is a proposed minor/concentration (a named bundle of existing elective_catalog
    or courses.json codes) actually supportable right now? Per-course faculty and
    room checks, reusing the same resourcing logic as M9's new-elective engine.
    """
    unknown = [c for c in course_codes if _course_lookup(state, c) is None]
    if unknown:
        return {"minor_name": minor_name, "error": f"Unknown course code(s): {', '.join(unknown)}"}

    total_credits = sum(_course_lookup(state, c)["credits"] for c in course_codes)
    per_course = []
    for code in course_codes:
        rec = _course_lookup(state, code)
        qualified_active = [
            fid for fid, f in state.faculty.items()
            if code in f.get("qualified_courses", []) and f.get("status") == "active"
        ]
        room_type = rec.get("requires_room_type", "lecture")
        equipment = set(rec.get("equipment_needed", []))
        room_candidates = [
            rid for rid, r in state.rooms.items()
            if r["room_type"] == room_type and equipment.issubset(set(r.get("equipment", [])))
        ]
        per_course.append({
            "course": code, "name": rec.get("name", code), "credits": rec["credits"],
            "qualified_active_faculty": qualified_active,
            "room_type_needed": room_type, "room_candidates": room_candidates,
            "feasible": bool(room_candidates),  # faculty gap alone is a flag, not a blocker - same policy as M9
            "flagged": not qualified_active,
        })

    hard_blockers = [c["course"] for c in per_course if not c["feasible"]]
    flagged = [c["course"] for c in per_course if c["flagged"]]

    if hard_blockers:
        verdict = "infeasible_no_room"
    elif flagged:
        verdict = "feasible_flagged"
    else:
        verdict = "feasible"

    return {
        "minor_name": minor_name, "course_codes": course_codes, "total_credits": total_credits,
        "per_course": per_course, "verdict": verdict,
        "hard_blockers": hard_blockers, "flagged_courses": flagged,
    }


def split_program_impact(state: DepartmentState, new_program_name: str, courses_to_move: List[str]) -> dict:
    """
    What would splitting `courses_to_move` out into a new program (e.g. CS -> CS +
    AI/Data Science) look like? Reports credit-hour distribution on both sides,
    which faculty are qualified for moved courses (and therefore need to be
    shared or reassigned), and an affected-student estimate from the most recent
    demand_history enrollment of the moved courses.
    """
    unknown = [c for c in courses_to_move if c not in state.courses]
    if unknown:
        return {"error": f"Unknown course code(s) in courses.json: {', '.join(unknown)}"}

    remaining_codes = [c for c in state.courses if c not in courses_to_move]

    def credit_totals(codes):
        totals: Dict[str, int] = {}
        for c in codes:
            cat = state.courses[c].get("category", "uncategorized")
            totals[cat] = totals.get(cat, 0) + state.courses[c]["credits"]
        return totals

    moved_totals = credit_totals(courses_to_move)
    remaining_totals = credit_totals(remaining_codes)

    faculty_needed = {
        fid: [c for c in f.get("qualified_courses", []) if c in courses_to_move]
        for fid, f in state.faculty.items()
    }
    faculty_needed = {fid: cs for fid, cs in faculty_needed.items() if cs}
    shared_faculty = {
        fid: cs for fid, cs in faculty_needed.items()
        if any(qc not in courses_to_move for qc in state.faculty[fid].get("qualified_courses", []))
    }

    affected_students = 0
    for code in courses_to_move:
        hist = state.demand_history.get(code, {})
        if hist:
            latest = sorted(hist.keys())[-1]
            affected_students = max(affected_students, hist[latest]["enrolled"])

    return {
        "new_program_name": new_program_name,
        "moved_courses": courses_to_move,
        "moved_credit_hours_by_category": moved_totals,
        "moved_total_credits": sum(moved_totals.values()),
        "remaining_credit_hours_by_category": remaining_totals,
        "remaining_total_credits": sum(remaining_totals.values()),
        "faculty_qualified_for_moved_courses": faculty_needed,
        "faculty_needed_by_both_programs": shared_faculty,
        "estimated_affected_students": affected_students,
        "note": "This is an impact analysis, not an executable state change - courses.json "
        "models a single program, so an actual split needs a follow-up schema change to "
        "represent two live programs at once.",
    }


def retirement_impact(state: DepartmentState, code: str, grandfather_terms: int = 2) -> dict:
    """Wraps M9's simulate_retirement with an affected-student estimate and a
    grandfathering note - students already relying on this course for a
    requirement get `grandfather_terms` more terms where it's still offered."""
    redistribution = demand_engine.simulate_retirement(state, code)
    rec = _course_lookup(state, code)
    return {
        "course": code,
        "name": rec.get("name", code) if rec else code,
        "category": rec.get("category") if rec else None,
        "demand_redistribution": redistribution,
        "grandfather_terms": grandfather_terms,
        "note": f"Students who need {code} for a declared requirement would have "
        f"{grandfather_terms} more terms to complete it before it's fully retired.",
    }


def credit_hour_distribution_diff(old_state: DepartmentState, new_state: DepartmentState) -> dict:
    """Before/after credit-hour-by-category comparison, reusing M10's compliance
    check on both states so a curriculum change's accreditation impact is visible
    alongside the raw numbers."""
    old_checks = {c["rule"]: c for c in check_credit_hour_minimums(old_state)}
    new_checks = {c["rule"]: c for c in check_credit_hour_minimums(new_state)}
    diff = []
    for rule in old_checks:
        diff.append({
            "category": rule.replace("min_credit_hours[", "").rstrip("]"),
            "before": old_checks[rule]["actual"],
            "after": new_checks.get(rule, {}).get("actual"),
            "required": old_checks[rule]["required"],
            "before_pass": old_checks[rule]["pass"],
            "after_pass": new_checks.get(rule, {}).get("pass"),
        })
    return {"old_label": old_state.label, "new_label": new_state.label, "by_category": diff}


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

def apply_change_course_category(state: DepartmentState, code: str, new_category: str) -> DepartmentState:
    if code not in state.courses:
        raise ValueError(f"Unknown course code '{code}'")
    new_state = state.copy()
    new_state.courses[code]["category"] = new_category
    return new_state


def apply_promote_elective_to_program(state: DepartmentState, code: str) -> DepartmentState:
    """Move a concrete elective_catalog course into the live courses.json graph -
    e.g. formally adding it as a required course for a new minor/concentration."""
    if code not in state.elective_catalog:
        raise ValueError(f"'{code}' is not in elective_catalog")
    if code in state.courses:
        raise ValueError(f"'{code}' is already part of the program")
    new_state = state.copy()
    rec = dict(new_state.elective_catalog[code])
    rec["prerequisites"] = rec.pop("suggested_prerequisites", [])
    rec["offered"] = [rec.pop("typical_term", "fall")]
    rec["seat_capacity"] = None
    new_state.courses[code] = rec
    return new_state


def apply_retire_course(state: DepartmentState, code: str) -> DepartmentState:
    if code not in state.courses:
        raise ValueError(f"Unknown course code '{code}'")
    new_state = state.copy()
    del new_state.courses[code]
    # drop it from any other course's prerequisites too, so the graph stays valid
    for rec in new_state.courses.values():
        rec["prerequisites"] = [p for p in rec["prerequisites"] if p != code]
        if rec.get("one_of_prerequisites"):
            rec["one_of_prerequisites"] = [p for p in rec["one_of_prerequisites"] if p != code]
    return new_state
