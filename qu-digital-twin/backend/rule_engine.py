"""
M2 — Rule Engines (catalog tasks T2.2 Graduation Audit Tool, T2.3 Course-Substitution
Checker).

Two pure functions. No state, no I/O beyond the data passed in, no LLM calls. Both
are used directly by the Streamlit frontend (M8) and are the only two tools the
advising agent (M6) is allowed to call for these two jobs — the agent must never
improvise a "remaining requirements" list or a substitution verdict from its own
knowledge.
"""
from __future__ import annotations

from typing import Dict, List


def graduation_audit(completed: List[str], courses: Dict[str, dict]) -> dict:
    """
    Compare a student's completed courses against the full program and report what's
    left, grouped by category, plus a credit summary.

    Returns:
        {
            "remaining": [course codes not yet completed],
            "remaining_by_category": {category: [course codes]},
            "completed_credits": int,
            "remaining_credits": int,
            "total_program_credits": int,
            "on_track": bool,   # True if no remaining course has an unmet prereq
                                 # among courses NOT in remaining (i.e. no logical
                                 # dead end given what's already completed)
            "unknown_completed": [codes in `completed` not found in the catalog],
        }
    """
    completed_set = set(completed)
    unknown = [c for c in completed if c not in courses]
    valid_completed = completed_set - set(unknown)

    remaining = [code for code in courses if code not in valid_completed]

    remaining_by_category: Dict[str, List[str]] = {}
    for code in remaining:
        cat = courses[code].get("category", "uncategorized")
        remaining_by_category.setdefault(cat, []).append(code)

    completed_credits = sum(courses[c]["credits"] for c in valid_completed)
    total_credits = sum(c["credits"] for c in courses.values())
    remaining_credits = total_credits - completed_credits

    # on_track: every remaining course's prerequisites are either completed or
    # also remaining-but-reachable (i.e. no prereq points to a course that doesn't
    # exist). This is a structural sanity check, not a graduation-timeline promise.
    on_track = True
    for code in remaining:
        for prereq in courses[code]["prerequisites"]:
            if prereq not in courses:
                on_track = False

    return {
        "remaining": sorted(remaining),
        "remaining_by_category": {
            k: sorted(v) for k, v in remaining_by_category.items()
        },
        "completed_credits": completed_credits,
        "remaining_credits": remaining_credits,
        "total_program_credits": total_credits,
        "on_track": on_track,
        "unknown_completed": unknown,
    }


def substitution_check(
    course_a: str,
    course_b: str,
    rules: List[dict],
    courses: Dict[str, dict],
) -> dict:
    """
    Look up whether course_b can substitute for course_a (order-insensitive lookup)
    under the encoded QU-style substitution rules.

    Returns:
        {"verdict": "allowed" | "not_allowed" | "needs_advisor",
         "justification": str}
    """
    if course_a not in courses or course_b not in courses:
        unknown = [c for c in (course_a, course_b) if c not in courses]
        return {
            "verdict": "needs_advisor",
            "justification": f"Unknown course code(s): {', '.join(unknown)}. "
            "An advisor must confirm the course exists before a verdict can be given.",
        }

    for rule in rules:
        pair = {rule["course_a"], rule["course_b"]}
        if pair == {course_a, course_b}:
            return {"verdict": rule["verdict"], "justification": rule["condition"]}

    return {
        "verdict": "needs_advisor",
        "justification": f"No encoded substitution rule exists for {course_a} <-> "
        f"{course_b}. This pair has not been pre-approved, so an advisor must "
        "review it manually.",
    }
