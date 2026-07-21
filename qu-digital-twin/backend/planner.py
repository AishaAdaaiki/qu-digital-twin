"""
M3 — Planner + Conflict Detector (catalog tasks T2.4 Basic Term-by-Term Planner,
T2.5 Schedule Conflict Detector).

plan_term() greedily builds one valid next term from the prerequisite graph.
detect_conflicts() checks a proposed course list for prerequisite gaps and, using
a mock schedule (QU section times aren't public), for meeting-time overlaps.

Both are pure functions over the data passed in — no LLM, no hidden state.
"""
from __future__ import annotations

from typing import Dict, List, Optional

DEFAULT_PREFERENCES = {
    "term": "fall",        # term being planned for: fall | spring | summer
    "preferred_courses": [],
    "avoid_courses": [],
    "min_credits": 12,
    "max_credits": 18,
}


def _base_gates_met(code: str, completed: set, courses: Dict[str, dict]) -> bool:
    """Plain AND-of-prerequisites plus the one_of_prerequisites / min_credits_required
    gates, ignoring symmetric_corequisites (used both directly and to check whether a
    mutual-corequisite partner could itself be co-enrolled, without recursing back
    through the pair)."""
    record = courses[code]
    if not all(p in completed for p in record["prerequisites"]):
        return False

    one_of = record.get("one_of_prerequisites")
    if one_of and not any(p in completed for p in one_of):
        return False

    min_credits = record.get("min_credits_required")
    if min_credits is not None:
        completed_credits = sum(courses[c]["credits"] for c in completed if c in courses)
        if completed_credits < min_credits:
            return False

    return True


def _prereqs_met(code: str, completed: set, courses: Dict[str, dict], term: Optional[str] = None) -> bool:
    """
    True if `code` is eligible given a completed-course set. Handles the plain
    AND-of-prerequisites case, the two optional extra gates some courses carry
    (currently just Senior Project I: `one_of_prerequisites` / `min_credits_required`),
    and true mutual corequisites (e.g. a lecture/lab pair, each listing the other as
    a corequisite) via `symmetric_corequisites`: eligible only if every such partner
    is already completed, or could be co-enrolled this same term (its own prereqs
    are met and it's offered in `term`).
    """
    if not _base_gates_met(code, completed, courses):
        return False

    for partner in courses[code].get("symmetric_corequisites", []):
        if partner in completed:
            continue
        if term is not None and term not in courses[partner]["offered"]:
            return False
        if not _base_gates_met(partner, completed, courses):
            return False

    return True


def _bundle_for(code: str, completed: set, courses: Dict[str, dict]) -> List[str]:
    """The set of courses that must be scheduled together with `code` this term:
    itself plus any not-yet-completed symmetric corequisite partners."""
    bundle = [code]
    for partner in courses[code].get("symmetric_corequisites", []):
        if partner not in completed:
            bundle.append(partner)
    return bundle


def plan_term(
    completed: List[str],
    preferences: dict,
    courses: Dict[str, dict],
    max_credits: int = 18,
) -> List[str]:
    """
    Build one valid next-term schedule.

    Constraints enforced:
      - every planned course's prerequisites are in `completed`
      - the course is offered in the requested term
      - total credits <= max_credits (and preferences['max_credits'] if given)
      - a course already in `completed` is never re-planned
      - preferences['avoid_courses'] are excluded
      - preferences['preferred_courses'] are scheduled first, if eligible

    Returns a list of course codes (empty list if nothing is eligible this term).
    """
    prefs = {**DEFAULT_PREFERENCES, **(preferences or {})}
    term = prefs["term"]
    cap = min(max_credits, prefs.get("max_credits", max_credits))
    min_credits = prefs.get("min_credits", 0)
    avoid = set(prefs.get("avoid_courses", []))
    preferred = [c for c in prefs.get("preferred_courses", []) if c not in avoid]

    completed_set = set(completed)

    eligible = [
        code
        for code in courses
        if code not in completed_set
        and code not in avoid
        and term in courses[code]["offered"]
        and _prereqs_met(code, completed_set, courses, term=term)
    ]

    # Preferred courses first (if eligible), then remaining eligible courses sorted
    # by category priority (major/support core before college/gen-ed before
    # electives) then course code for determinism.
    category_priority = {
        "major_core": 0,
        "major_supporting": 0,
        "college": 1,
        "core_curriculum": 2,
        "major_elective": 3,
    }
    ordered_rest = sorted(
        [c for c in eligible if c not in preferred],
        key=lambda c: (category_priority.get(courses[c].get("category", "major_elective"), 9), c),
    )
    ordering = [c for c in preferred if c in eligible] + ordered_rest

    plan: List[str] = []
    planned_set: set = set()
    credits_used = 0
    for code in ordering:
        if code in planned_set:
            continue
        bundle = [c for c in _bundle_for(code, completed_set, courses) if c not in planned_set]
        bundle_credit = sum(courses[c]["credits"] for c in bundle)
        if credits_used + bundle_credit <= cap:
            plan.extend(bundle)
            planned_set.update(bundle)
            credits_used += bundle_credit

    # best-effort note: if under min_credits, that's surfaced by the caller (agent/
    # frontend) rather than silently over-filled, since forcing more courses could
    # violate the cap or prerequisite logic.
    return plan


def detect_conflicts(
    proposed: List[str],
    completed: List[str],
    courses: Dict[str, dict],
    schedule: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    """
    Check a proposed course list for:
      - prereq_gap: a proposed course whose prerequisites (or one_of_prerequisites /
        min_credits_required gate) aren't satisfied by `completed`
      - corequisite_gap: a proposed course whose true mutual corequisite (e.g. a
        lecture/lab pair) isn't in `completed` and isn't also in `proposed`
      - time_overlap: two proposed courses whose mock meeting times overlap

    `schedule` maps course -> {"day": str, "start": "HH:MM", "end": "HH:MM"}.
    If not supplied, time_overlap checks are skipped (only prereq_gap reported).

    Returns a list of conflict dicts: {"type": ..., "course": ..., "detail": ...}
    (for time_overlap, "course" holds "A vs B").
    """
    completed_set = set(completed)
    conflicts: List[dict] = []

    for code in proposed:
        if code not in courses:
            conflicts.append(
                {"type": "unknown_course", "course": code, "detail": f"'{code}' is not in the catalog."}
            )
            continue
        missing = [p for p in courses[code]["prerequisites"] if p not in completed_set]
        if missing:
            conflicts.append(
                {
                    "type": "prereq_gap",
                    "course": code,
                    "detail": f"{code} requires {', '.join(missing)}, not yet completed.",
                }
            )
        elif not _prereqs_met(code, completed_set, courses):
            # plain prerequisites are satisfied but an extra gate (one_of_prerequisites
            # / min_credits_required) is not -- e.g. Senior Project I's 84-CH threshold
            # or its CMPS350-or-CMPS405 requirement.
            record = courses[code]
            reasons = []
            one_of = record.get("one_of_prerequisites")
            if one_of and not any(p in completed_set for p in one_of):
                reasons.append(f"needs at least one of {', '.join(one_of)}")
            min_credits = record.get("min_credits_required")
            if min_credits is not None:
                completed_credits = sum(courses[c]["credits"] for c in completed_set if c in courses)
                if completed_credits < min_credits:
                    reasons.append(f"needs {min_credits} completed credit hours (has {completed_credits})")
            conflicts.append(
                {
                    "type": "prereq_gap",
                    "course": code,
                    "detail": f"{code} {'; '.join(reasons) if reasons else 'has an unmet eligibility gate'}.",
                }
            )

        for partner in courses[code].get("symmetric_corequisites", []):
            if partner not in completed_set and partner not in proposed:
                conflicts.append(
                    {
                        "type": "corequisite_gap",
                        "course": code,
                        "detail": f"{code} must be taken together with its corequisite "
                        f"{partner} (or {partner} must already be completed).",
                    }
                )

    if schedule:
        def to_minutes(hhmm: str) -> int:
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        valid = [c for c in proposed if c in schedule]
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                a, b = valid[i], valid[j]
                sa, sb = schedule[a], schedule[b]
                if sa["day"] != sb["day"]:
                    continue
                a_start, a_end = to_minutes(sa["start"]), to_minutes(sa["end"])
                b_start, b_end = to_minutes(sb["start"]), to_minutes(sb["end"])
                if a_start < b_end and b_start < a_end:
                    conflicts.append(
                        {
                            "type": "time_overlap",
                            "course": f"{a} vs {b}",
                            "detail": f"{a} ({sa['start']}-{sa['end']}) overlaps {b} "
                            f"({sb['start']}-{sb['end']}) on {sa['day']}.",
                        }
                    )

    return conflicts
