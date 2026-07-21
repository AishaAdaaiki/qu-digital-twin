"""
Per-course, per-semester success-rate model feeding M4's cohort simulation and
M5's what-if analysis (replaces the flat per-category pass/fail/withdraw
assumption in simulation_config.json with a course-specific, network-aware
"effective rate").

Two ingredients per course:

  1. Its own historical pass rate, read straight from
     backend/data/demand_history.json, which is keyed "{year}_{term}" per
     course (e.g. "2023_fall") - so a course offered in both Fall and Spring
     already has separate rates per semester; a course offered in only one
     term just has one.

  2. A "prerequisite chain" nudge: the effective rate of a course's direct
     prerequisites, blended in at a configurable weight. Rationale (a
     documented assumption, not measured QU data): a course whose
     prerequisites have weak historical pass rates likely sees somewhat
     weaker performance too, because students arrive less prepared.

        effective_rate(course) =
              weight * own_historical_rate
            + (1 - weight) * average(effective_rate(p) for p in direct prerequisites)

     weight defaults to 0.8 (80% the course's own performance, 20% its
     prerequisite chain), recursing all the way back to courses with no
     prerequisites. Courses with no demand_history on record (new electives,
     the generic ELEC1-4 slots) fall back to their category's flat rate from
     simulation_config.json.

Propagation is directional and transitive: change one course's rate and
every course that has it as a prerequisite - directly or through a chain -
can shift too. propagate_rate_change() walks that "is a prerequisite of"
graph forward and reports the before/after effective rate for every course
downstream of the one you changed.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional

DEFAULT_WEIGHT = 0.8


def historical_rate(demand_history: Dict[str, dict], code: str, term: Optional[str] = None) -> Optional[float]:
    """Average pass_rate across every year on record for `code`. If `term` is
    given, only years offered in that term are averaged (e.g. only "*_fall"
    entries). Returns None if there's no history at all for that course/term."""
    entries = demand_history.get(code)
    if not entries:
        return None
    rates = [
        v["pass_rate"]
        for k, v in entries.items()
        if (term is None or k.endswith(f"_{term}")) and "pass_rate" in v
    ]
    if not rates:
        return None
    return sum(rates) / len(rates)


def category_fallback_rate(config: dict, category: str) -> float:
    rates = config["pass_fail_withdraw_by_category"]
    return rates.get(category, rates["major_elective"])["pass"]


def fail_withdraw_split(config: dict, category: str) -> tuple:
    """Returns (fail_share, withdraw_share) of the non-pass probability mass,
    taken from that category's simulation_config.json ratio and normalized to
    sum to 1.0 - used to split an effective pass rate's remainder between
    fail and withdraw without inventing a second free parameter."""
    rates = config["pass_fail_withdraw_by_category"]
    r = rates.get(category, rates["major_elective"])
    non_pass = r["fail"] + r["withdraw"]
    if non_pass <= 0:
        return 0.5, 0.5
    return r["fail"] / non_pass, r["withdraw"] / non_pass


def effective_rate(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
    config: dict,
    code: str,
    term: Optional[str] = None,
    weight: float = DEFAULT_WEIGHT,
    _memo: Optional[Dict[str, float]] = None,
) -> float:
    """
    Network-adjusted effective pass rate for `code`.

    `term=None` returns the "blended" rate (averaged across all its own
    history) - this is what gets memoized and reused when this course shows
    up as someone else's prerequisite. Pass a specific term to get the
    semester-specific rate for display or for feeding the simulator, which
    still nudges in from prerequisites' blended rates.
    """
    if _memo is None:
        _memo = {}
    if term is None and code in _memo:
        return _memo[code]

    record = courses.get(code, {})
    own = historical_rate(demand_history, code, term)
    if own is None:
        own = category_fallback_rate(config, record.get("category", "major_elective"))

    prereqs = [p for p in record.get("prerequisites", []) if p in courses]
    if prereqs:
        prereq_vals = [
            effective_rate(courses, demand_history, config, p, term=None, weight=weight, _memo=_memo)
            for p in prereqs
        ]
        avg_prereq = sum(prereq_vals) / len(prereq_vals)
        result = weight * own + (1 - weight) * avg_prereq
    else:
        result = own

    result = min(0.99, max(0.01, result))

    if term is None:
        _memo[code] = result
    return result


def all_effective_rates_by_term(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
    config: dict,
    weight: float = DEFAULT_WEIGHT,
) -> Dict[str, Dict[str, float]]:
    """code -> {term: effective_rate} for every term that course is offered in."""
    memo: Dict[str, float] = {}
    result = {}
    for code, record in courses.items():
        result[code] = {
            term: effective_rate(courses, demand_history, config, code, term=term, weight=weight, _memo=memo)
            for term in record.get("offered", [])
        }
    return result


def build_course_probabilities_by_term(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
    config: dict,
    weight: float = DEFAULT_WEIGHT,
) -> Dict[tuple, dict]:
    """(code, term) -> {"pass": p, "fail": f, "withdraw": w}, ready to feed
    directly into the cohort simulator's random draw per attempt."""
    rates_by_term = all_effective_rates_by_term(courses, demand_history, config, weight=weight)
    probs = {}
    for code, by_term in rates_by_term.items():
        category = courses[code].get("category", "major_elective")
        fail_share, withdraw_share = fail_withdraw_split(config, category)
        for term, p_pass in by_term.items():
            non_pass = 1 - p_pass
            probs[(code, term)] = {
                "pass": p_pass,
                "fail": non_pass * fail_share,
                "withdraw": non_pass * withdraw_share,
            }
    return probs


def build_dependents_map(courses: Dict[str, dict]) -> Dict[str, List[str]]:
    """code -> [courses that list `code` as a direct prerequisite]."""
    dependents: Dict[str, List[str]] = defaultdict(list)
    for code, record in courses.items():
        for prereq in record.get("prerequisites", []):
            dependents[prereq].append(code)
    return dependents


def downstream_of(dependents_map: Dict[str, List[str]], code: str) -> List[str]:
    """Every course transitively dependent on `code` (BFS, so results come
    back ordered nearest-hop-first)."""
    seen, order, queue = set(), [], deque(dependents_map.get(code, []))
    while queue:
        c = queue.popleft()
        if c in seen:
            continue
        seen.add(c)
        order.append(c)
        queue.extend(dependents_map.get(c, []))
    return order


def propagate_rate_change(
    courses: Dict[str, dict],
    demand_history: Dict[str, dict],
    config: dict,
    code: str,
    new_rate: float,
    weight: float = DEFAULT_WEIGHT,
) -> dict:
    """
    "What if course `code`'s effective rate became `new_rate`?" - reports the
    before/after effective rate for `code` itself and every course downstream
    of it in the prerequisite chain (direct and indirect), sorted by the size
    of the resulting shift.
    """
    if code not in courses:
        raise ValueError(f"Unknown course: {code}")

    current_rate = effective_rate(courses, demand_history, config, code, term=None, weight=weight)
    dependents_map = build_dependents_map(courses)
    downstream_codes = downstream_of(dependents_map, code)

    affected = []
    for dcode in downstream_codes:
        before = effective_rate(courses, demand_history, config, dcode, term=None, weight=weight, _memo={})
        after = effective_rate(
            courses, demand_history, config, dcode, term=None, weight=weight, _memo={code: new_rate}
        )
        affected.append({
            "course": dcode,
            "name": courses[dcode]["name"],
            "before": round(before, 4),
            "after": round(after, 4),
            "delta": round(after - before, 4),
        })

    affected.sort(key=lambda r: abs(r["delta"]), reverse=True)

    return {
        "course": code,
        "name": courses[code]["name"],
        "current_effective_rate": round(current_rate, 4),
        "new_rate": round(new_rate, 4),
        "weight": weight,
        "affected_courses": affected,
    }
