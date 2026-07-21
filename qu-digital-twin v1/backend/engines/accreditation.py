"""
M10 - Accreditation & Compliance engine.

Unlike the other four department engines, this one isn't move-driven - it's a
validator (docs/department_simulation_architecture.md §4.5) meant to run against
ANY candidate state, from any engine, so a proposed change's compliance impact is
always visible next to its other effects.

Three checks, each against backend/data/accreditation_rules.json:
  1. Credit-hour-by-category minimums (does the curriculum still add up)
  2. Class size vs room-type cap (does any course's capacity exceed policy)
  3. Student-faculty ratio (is the department correctly staffed for its size)

Pure function, no LLM, no mutation.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from backend.state import DepartmentState


def _credit_hours_by_category(state: DepartmentState) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for rec in state.courses.values():
        cat = rec.get("category", "uncategorized")
        totals[cat] = totals.get(cat, 0) + rec["credits"]
    return totals


def check_credit_hour_minimums(state: DepartmentState) -> List[dict]:
    actual = _credit_hours_by_category(state)
    rules = state.accreditation_rules.get("min_credit_hours_by_category", {})
    results = []
    for category, minimum in rules.items():
        have = actual.get(category, 0)
        results.append({
            "rule": f"min_credit_hours[{category}]",
            "required": minimum,
            "actual": have,
            "pass": have >= minimum,
            "detail": f"{category} has {have} credit hours (minimum {minimum}).",
        })
    return results


def check_class_size(state: DepartmentState) -> List[dict]:
    max_by_type = state.accreditation_rules.get("max_class_size", {})
    results = []
    for code, rec in state.courses.items():
        cap = rec.get("seat_capacity")
        room_type = rec.get("requires_room_type")
        if cap is None or room_type is None or room_type not in max_by_type:
            continue
        limit = max_by_type[room_type]
        results.append({
            "rule": f"max_class_size[{room_type}]",
            "course": code,
            "required": limit,
            "actual": cap,
            "pass": cap <= limit,
            "detail": f"{code} ({rec['name']}) has seat_capacity {cap} in a "
            f"'{room_type}' room (policy max {limit}).",
        })
    return [r for r in results if not r["pass"]] + [r for r in results if r["pass"]]


def check_student_faculty_ratio(state: DepartmentState, total_students: Optional[int] = None) -> dict:
    """
    total_students defaults to an estimate: 4x the most recent CMPS151 (intro
    programming, taken by essentially every incoming student) enrollment, as a
    steady-state proxy for total majors across a 4-year program. Pass an explicit
    number (e.g. from an enrollment-growth scenario) to override.
    """
    if total_students is None:
        hist = state.demand_history.get("CMPS151", {})
        if hist:
            latest_term = sorted(hist.keys())[-1]
            total_students = hist[latest_term]["enrolled"] * 4
        else:
            total_students = 0

    active_fte = sum(f["fte"] for f in state.faculty.values() if f.get("status") == "active")
    ratio = round(total_students / active_fte, 1) if active_fte else None
    limit = state.accreditation_rules.get("max_student_faculty_ratio")

    return {
        "rule": "max_student_faculty_ratio",
        "required": limit,
        "actual": ratio,
        "pass": ratio is not None and limit is not None and ratio <= limit,
        "total_students_estimate": total_students,
        "active_faculty_fte": active_fte,
        "detail": f"Estimated {total_students} students / {active_fte} active faculty FTE "
        f"= {ratio} ratio (policy max {limit}).",
    }


def compliance_scorecard(state: DepartmentState, total_students: Optional[int] = None) -> dict:
    """The single entry point every other engine's scenario result should attach:
    a pass/fail scorecard plus a compact summary."""
    credit_checks = check_credit_hour_minimums(state)
    class_size_checks = check_class_size(state)
    ratio_check = check_student_faculty_ratio(state, total_students=total_students)

    all_checks = credit_checks + class_size_checks + [ratio_check]
    n_pass = sum(1 for c in all_checks if c["pass"])
    n_fail = len(all_checks) - n_pass

    return {
        "state_label": state.label,
        "credit_hour_checks": credit_checks,
        "class_size_checks": class_size_checks,
        "student_faculty_ratio_check": ratio_check,
        "summary": {
            "total_checks": len(all_checks),
            "passed": n_pass,
            "failed": n_fail,
            "fully_compliant": n_fail == 0,
        },
    }
