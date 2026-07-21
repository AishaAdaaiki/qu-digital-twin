"""
Per-course, per-semester seat-capacity model feeding M4's cohort simulation.

Same motivation as backend/success_rates.py: `courses.json` has exactly one
static `seat_capacity` per course (frequently `None`, i.e. "unlimited"), which
doesn't reflect reality - `demand_history.json` already records the actual
capacity that was offered each year, per term, and it's often a real number
even where courses.json says "unlimited" (e.g. CMPS151 is capped at 24 seats
every year on record, but courses.json never says so).

effective_capacity() prefers the most recent year on record for that course's
term - capacity is a structural/scheduling fact (how many seats fit in the
assigned room), so "what it is right now" matters more than a multi-year
average the way it does for pass rates. It falls back, in order:

    1. Most recent year's capacity for that (course, term) in demand_history.json
    2. The static seat_capacity in courses.json
    3. None (genuinely unlimited - no cap enforced)
"""
from __future__ import annotations

import copy
from typing import Dict, Optional, Set


def historical_capacity(demand_history: Dict[str, dict], code: str, term: Optional[str] = None) -> Optional[int]:
    """Most recent year's capacity on record for `code` (optionally filtered
    to one term). Returns None if there's no history for that course/term."""
    entries = demand_history.get(code)
    if not entries:
        return None
    matching = {
        k: v for k, v in entries.items()
        if (term is None or k.endswith(f"_{term}")) and "capacity" in v
    }
    if not matching:
        return None
    latest_key = max(matching, key=lambda k: int(k.split("_")[0]))  # "YYYY_term" -> YYYY
    return matching[latest_key]["capacity"]


def effective_capacity(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
    code: str,
    term: Optional[str] = None,
) -> Optional[int]:
    """The capacity to actually enforce for (code, term): real recent history
    first, the static courses.json field second, None (unlimited) last."""
    cap = historical_capacity(demand_history, code, term)
    if cap is not None:
        return cap
    record = courses.get(code, {})
    return record.get("seat_capacity")


def all_capacities_by_term(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
) -> Dict[tuple, Optional[int]]:
    """(code, term) -> effective capacity, for every course/term in courses.json."""
    result = {}
    for code, record in courses.items():
        for term in record.get("offered", []):
            result[(code, term)] = effective_capacity(courses, demand_history, code, term)
    return result


def override_capacity_in_history(demand_history: Dict[str, dict], code: str, new_capacity: int) -> Dict[str, dict]:
    """Deep-copies demand_history and sets every recorded year's capacity for
    `code` to exactly `new_capacity`. Used to build single-course seat-
    capacity what-if scenarios (M5) - modifying courses.json's static
    seat_capacity alone has no effect once real history exists for a course,
    since effective_capacity() prefers the most recent recorded year."""
    dh2 = copy.deepcopy(demand_history)
    if code in dh2:
        for entry in dh2[code].values():
            if "capacity" in entry:
                entry["capacity"] = new_capacity
    return dh2


def scale_capacity_in_history(
    demand_history: Dict[str, dict], factor: float, codes: Optional[Set[str]] = None
) -> Dict[str, dict]:
    """Deep-copies demand_history and scales every recorded capacity by
    `factor` (rounded down, minimum 1) - for courses in `codes` if given,
    else every course. Used for global "what if every capacity-limited course
    lost N% of its seats" sensitivity sweeps."""
    dh2 = copy.deepcopy(demand_history)
    for code, entries in dh2.items():
        if codes is not None and code not in codes:
            continue
        for entry in entries.values():
            if "capacity" in entry:
                entry["capacity"] = max(1, int(entry["capacity"] * factor))
    return dh2
