"""
M9 - Enrollment & Demand Forecasting engine.

Reads backend.state.DepartmentState (courses, elective_catalog, demand_history)
and answers five kinds of question, per docs/department_simulation_architecture.md
§4.1 and §5:

  1. forecast_course_demand   - where is a course's enrollment trending
  2. oversubscription_report  - which courses are over/under capacity right now
  3. simulate_mandatory_shock - what if we make an elective mandatory
  4. simulate_retirement      - what if we retire a course (demand goes where?)
  5. propose_new_elective     - is a brand-new elective idea feasible

All functions are pure: they take a DepartmentState and return plain dicts/lists,
never mutating the state. Nothing here calls an LLM - "propose_new_elective"'s
similarity scoring is TF-IDF (backend/text_similarity.py), fully deterministic.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from backend.state import DepartmentState, GENERIC_SLOT_CODES
from backend.text_similarity import TfidfIndex


def _sorted_terms(history: Dict[str, dict]) -> List[str]:
    """demand_history keys look like '2022_fall' - sort chronologically."""
    def sort_key(term_key: str):
        year, term = term_key.split("_")
        term_order = {"spring": 0, "summer": 1, "fall": 2}
        return (int(year), term_order.get(term, 0))
    return sorted(history.keys(), key=sort_key)


def forecast_course_demand(state: DepartmentState, code: str, n_terms_ahead: int = 2) -> dict:
    """
    Simple linear-trend forecast over a course's demand_history. Returns the
    historical series plus `n_terms_ahead` projected points, and a plain-language
    trend direction so the frontend doesn't need to interpret slope itself.
    """
    history = state.demand_history.get(code)
    if not history:
        return {"course": code, "error": "no demand history for this course"}

    terms = _sorted_terms(history)
    enrolled = [history[t]["enrolled"] for t in terms]
    capacity = [history[t]["capacity"] for t in terms]

    x = list(range(len(enrolled)))
    n = len(x)
    if n < 2:
        slope, intercept = 0.0, enrolled[0] if enrolled else 0
    else:
        mean_x = sum(x) / n
        mean_y = sum(enrolled) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, enrolled))
        den = sum((xi - mean_x) ** 2 for xi in x) or 1
        slope = num / den
        intercept = mean_y - slope * mean_x

    forecast_points = [
        {"period": f"forecast_{i+1}", "projected_enrolled": max(0, round(intercept + slope * (n - 1 + i)))}
        for i in range(1, n_terms_ahead + 1)
    ]

    if slope > 0.5:
        trend = "growing"
    elif slope < -0.5:
        trend = "declining"
    else:
        trend = "flat"

    return {
        "course": code,
        "history": [{"period": t, **history[t]} for t in terms],
        "forecast": forecast_points,
        "trend_direction": trend,
        "trend_slope_per_term": round(slope, 2),
        "current_capacity": capacity[-1] if capacity else None,
    }


def oversubscription_report(state: DepartmentState, waitlist_threshold: int = 3) -> List[dict]:
    """Every course whose most recent demand-history term is at/over capacity or
    has a meaningful waitlist, flagged for either 'increase capacity' or (if
    consistently under capacity) 'possible over-provisioning'."""
    flags = []
    for code, history in state.demand_history.items():
        terms = _sorted_terms(history)
        if not terms:
            continue
        latest = history[terms[-1]]
        utilization = latest["enrolled"] / latest["capacity"] if latest["capacity"] else None
        name = state.courses.get(code, state.elective_catalog.get(code, {})).get("name", code)
        if latest["waitlisted"] >= waitlist_threshold:
            flags.append({
                "course": code, "name": name, "status": "oversubscribed",
                "enrolled": latest["enrolled"], "capacity": latest["capacity"],
                "waitlisted": latest["waitlisted"], "utilization": round(utilization, 2) if utilization else None,
            })
        elif utilization is not None and utilization < 0.5:
            flags.append({
                "course": code, "name": name, "status": "underenrolled",
                "enrolled": latest["enrolled"], "capacity": latest["capacity"],
                "waitlisted": latest["waitlisted"], "utilization": round(utilization, 2),
            })
    return sorted(flags, key=lambda f: (f["status"] != "oversubscribed", -f.get("waitlisted", 0)))


def simulate_mandatory_shock(state: DepartmentState, code: str, cohort_size_estimate: int = 100) -> dict:
    """What happens if `code` (currently an elective) becomes mandatory: demand
    jumps to roughly the size of the class cohort instead of self-selected
    enrollment. Flags whether current capacity can absorb it."""
    history = state.demand_history.get(code)
    current_capacity = None
    if code in state.courses:
        current_capacity = state.courses[code].get("seat_capacity")
    if current_capacity is None and history:
        terms = _sorted_terms(history)
        current_capacity = history[terms[-1]]["capacity"] if terms else None

    current_enrolled = None
    if history:
        terms = _sorted_terms(history)
        current_enrolled = history[terms[-1]]["enrolled"] if terms else None

    projected_demand = cohort_size_estimate
    capacity_gap = None
    if current_capacity is not None:
        capacity_gap = projected_demand - current_capacity

    return {
        "course": code,
        "current_enrolled": current_enrolled,
        "current_capacity": current_capacity,
        "projected_demand_if_mandatory": projected_demand,
        "capacity_gap": capacity_gap,
        "feasible_without_changes": capacity_gap is not None and capacity_gap <= 0,
    }


def simulate_retirement(state: DepartmentState, code: str, top_k: int = 3) -> dict:
    """What happens if `code` is retired: its most recent enrollment gets
    redistributed across the most textually-similar remaining courses/electives,
    weighted by similarity - a simple but explainable proxy for 'where would those
    students actually go'."""
    corpus = _description_corpus(state, exclude={code})
    index = TfidfIndex(corpus)

    query_text = _course_description(state, code)
    if not query_text:
        return {"course": code, "error": "no description available to find similar courses"}

    history = state.demand_history.get(code, {})
    terms = _sorted_terms(history)
    displaced = history[terms[-1]]["enrolled"] if terms else 0

    matches = index.query(query_text, top_k=top_k)
    total_sim = sum(score for _, score in matches) or 1
    redistribution = [
        {
            "course": match_code,
            "name": _course_name(state, match_code),
            "similarity": round(score, 3),
            "redistributed_students": round(displaced * (score / total_sim)),
        }
        for match_code, score in matches
    ]

    return {"course": code, "displaced_students": displaced, "redistribution": redistribution}


def simulate_intake_shock(state: DepartmentState, pct_change: float) -> List[dict]:
    """Scale every course's most recent enrollment by `pct_change` (e.g. 0.2 for
    +20% intake) and flag which courses would go over capacity as a result."""
    flagged = []
    for code, history in state.demand_history.items():
        terms = _sorted_terms(history)
        if not terms:
            continue
        latest = history[terms[-1]]
        projected = round(latest["enrolled"] * (1 + pct_change))
        if latest["capacity"] and projected > latest["capacity"]:
            flagged.append({
                "course": code,
                "name": state.courses.get(code, state.elective_catalog.get(code, {})).get("name", code),
                "current_enrolled": latest["enrolled"],
                "projected_enrolled": projected,
                "capacity": latest["capacity"],
                "overflow": projected - latest["capacity"],
            })
    return sorted(flagged, key=lambda f: -f["overflow"])


# ---------------------------------------------------------------------------
# New-elective feasibility (docs §5 / §5.1)
# ---------------------------------------------------------------------------

def _description_corpus(state: DepartmentState, exclude: Optional[set] = None) -> Dict[str, str]:
    exclude = exclude or set()
    corpus = {}
    for code, rec in state.courses.items():
        if code in GENERIC_SLOT_CODES or code in exclude:
            continue
        desc = rec.get("description")
        if desc:
            corpus[code] = f"{rec.get('name', '')}. {desc}"
    for code, rec in state.elective_catalog.items():
        if code in exclude:
            continue
        desc = rec.get("description")
        if desc:
            corpus[code] = f"{rec.get('name', '')}. {desc}"
    return corpus


def _course_description(state: DepartmentState, code: str) -> Optional[str]:
    rec = state.courses.get(code) or state.elective_catalog.get(code)
    if not rec or not rec.get("description"):
        return None
    return f"{rec.get('name', '')}. {rec['description']}"


def _course_name(state: DepartmentState, code: str) -> str:
    rec = state.courses.get(code) or state.elective_catalog.get(code) or {}
    return rec.get("name", code)


def propose_new_elective(
    state: DepartmentState,
    name: str,
    description: str,
    credits: int = 3,
    requires_room_type: Optional[str] = None,
    equipment_needed: Optional[List[str]] = None,
    top_k: int = 5,
) -> dict:
    """
    Feasibility report for a brand-new elective idea (docs §5, §5.1). Four
    independent legs, each reported separately so it's clear which one (if any)
    is the actual constraint - a course never gets a flat "infeasible" just for
    lacking a dedicated instructor; that case is "feasible, flagged" per the
    project's decided policy (see docs §9).
    """
    corpus = _description_corpus(state)
    index = TfidfIndex(corpus)
    matches = index.query(f"{name}. {description}", top_k=top_k)

    if not matches:
        return {
            "name": name,
            "verdict": "insufficient_evidence",
            "rationale": "No existing course description is textually similar enough to estimate "
            "demand or resourcing from. This doesn't mean the idea is bad - it means the catalog "
            "has no comparable precedent to reason from.",
            "similar_courses": [],
        }

    # --- demand leg ---
    weighted_demand = 0.0
    total_sim = 0.0
    similar_courses = []
    for code, score in matches:
        hist = state.demand_history.get(code, {})
        terms = _sorted_terms(hist)
        latest = hist[terms[-1]] if terms else None
        if latest:
            weighted_demand += latest["enrolled"] * score
            total_sim += score
        similar_courses.append({
            "course": code, "name": _course_name(state, code), "similarity": round(score, 3),
            "recent_enrollment": latest["enrolled"] if latest else None,
            "recent_pass_rate": latest["pass_rate"] if latest else None,
        })
    projected_demand = round(weighted_demand / total_sim) if total_sim else None

    # --- resourcing legs: inherit room/equipment from the closest match unless given ---
    top_code = matches[0][0]
    top_rec = state.courses.get(top_code) or state.elective_catalog.get(top_code) or {}
    inferred_room_type = requires_room_type or top_rec.get("requires_room_type", "lecture")
    inferred_equipment = equipment_needed if equipment_needed is not None else top_rec.get("equipment_needed", [])

    room_candidates = [
        r for r in state.rooms.values()
        if r["room_type"] == inferred_room_type
        and set(inferred_equipment).issubset(set(r.get("equipment", [])))
    ]
    room_feasible = len(room_candidates) > 0
    best_room_capacity = max((r["capacity"] for r in room_candidates), default=0)

    # --- faculty leg: keyword overlap between description and specializations ---
    from backend.text_similarity import tokenize
    desc_tokens = set(tokenize(f"{name} {description}"))
    faculty_matches = []
    for fid, rec in state.faculty.items():
        spec_tokens = set()
        for spec in rec.get("specializations", []):
            spec_tokens.update(tokenize(spec.replace("_", " ")))
        overlap = desc_tokens & spec_tokens
        if overlap and rec.get("status") == "active":
            faculty_matches.append({
                "faculty_id": fid, "name": rec.get("name"),
                "matched_on": sorted(overlap), "max_courses_per_term": rec.get("max_courses_per_term"),
            })

    # --- verdict ---
    warnings = []
    if not faculty_matches:
        warnings.append("no current faculty specialization overlaps this topic - would require hiring or retraining")
    if not room_feasible:
        warnings.append(f"no room in inventory matches room_type='{inferred_room_type}' with equipment {inferred_equipment}")
    if projected_demand is not None and best_room_capacity and projected_demand > best_room_capacity:
        warnings.append(f"projected demand ({projected_demand}) exceeds the best available room's capacity ({best_room_capacity})")

    if warnings and not room_feasible:
        verdict = "infeasible_no_room"  # only a hard blocker: literally nowhere to hold it
    elif warnings:
        verdict = "feasible_flagged"
    else:
        verdict = "feasible"

    return {
        "name": name,
        "description": description,
        "credits": credits,
        "verdict": verdict,
        "projected_first_year_demand": projected_demand,
        "similar_courses": similar_courses,
        "inferred_requires_room_type": inferred_room_type,
        "inferred_equipment_needed": inferred_equipment,
        "room_candidates": [r for r in state.rooms if state.rooms[r] in room_candidates],
        "faculty_matches": faculty_matches,
        "warnings": warnings,
        "rationale": _build_rationale(similar_courses, faculty_matches, room_feasible, warnings),
    }


def _build_rationale(similar_courses: List[dict], faculty_matches: List[dict], room_feasible: bool, warnings: List[str]) -> str:
    if not similar_courses:
        return "No comparable courses found."
    top = similar_courses[0]
    parts = [
        f"Most similar to {top['course']} ({top['name']}, similarity {top['similarity']})"
    ]
    if len(similar_courses) > 1:
        second = similar_courses[1]
        parts.append(f"and {second['course']} ({second['name']}, similarity {second['similarity']})")
    if faculty_matches:
        parts.append(f"; {len(faculty_matches)} active faculty member(s) have a specialization match")
    else:
        parts.append("; no active faculty member has a specialization match")
    parts.append("; a matching room exists" if room_feasible else "; no matching room exists in inventory")
    return " ".join(parts) + "."
