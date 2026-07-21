"""
M5 — What-If Analysis (catalog tasks T3.2 Prerequisite Bottleneck Finder,
T3.3 Term Capacity Stress Test).

Reuses the M4 CohortSimulator/Monte Carlo engine unchanged. Every scenario here is
just a modified `courses` dict or `config` dict fed into the same simulation logic
— no separate simulation code path, so scenario results are directly comparable to
baseline.
"""
from __future__ import annotations

import copy
from typing import Dict, List, Optional

from backend.data_layer import load_courses
from backend.simulation import load_config, run_monte_carlo


def apply_modification(courses: dict, config: dict, modification: dict):
    """
    modification formats:
      {"target": "course", "course": "CMPS251", "param": "offered", "value": ["fall"]}
      {"target": "course", "course": "CMPS251", "param": "seat_capacity", "value": 17}
      {"target": "term_cycle", "value": ["fall", "spring"]}   # e.g. drop summer
    """
    courses2 = copy.deepcopy(courses)
    config2 = copy.deepcopy(config)

    target = modification["target"]
    if target == "course":
        courses2[modification["course"]][modification["param"]] = modification["value"]
    elif target == "term_cycle":
        config2["term_cycle"] = modification["value"]
    else:
        raise ValueError(f"Unknown modification target: {target}")

    return courses2, config2


def run_scenario(
    baseline_config: dict,
    modification: dict,
    courses: Optional[Dict[str, dict]] = None,
    n_students: int = 500,
    n_runs: int = 10,
    seed_start: int = 2000,
) -> dict:
    """
    Run baseline vs. one modified scenario with matched seeds for a fair
    paired comparison.

    Returns:
        {"baseline_mean": float, "scenario_mean": float,
         "delta_terms": float, "affected_students_pct": float}
    """
    courses = courses or load_courses()
    scenario_courses, scenario_config = apply_modification(courses, baseline_config, modification)

    baseline = run_monte_carlo(
        n_students, n_runs, config=baseline_config, courses=courses, seed_start=seed_start
    )
    scenario = run_monte_carlo(
        n_students, n_runs, config=scenario_config, courses=scenario_courses, seed_start=seed_start
    )

    baseline_dist = baseline["distribution"]
    scenario_dist = scenario["distribution"]
    paired_len = min(len(baseline_dist), len(scenario_dist))
    changed = sum(
        1 for i in range(paired_len) if baseline_dist[i] != scenario_dist[i]
    )
    affected_pct = (changed / paired_len * 100) if paired_len else 0.0

    delta = None
    if baseline["mean_graduation_term"] is not None and scenario["mean_graduation_term"] is not None:
        delta = scenario["mean_graduation_term"] - baseline["mean_graduation_term"]

    return {
        "baseline_mean": baseline["mean_graduation_term"],
        "scenario_mean": scenario["mean_graduation_term"],
        "delta_terms": delta,
        "affected_students_pct": affected_pct,
        "scenario_n_stuck": scenario["n_stuck_total"],
        "baseline_n_stuck": baseline["n_stuck_total"],
    }


# ---------------------------------------------------------------------------
# T3.2 — Prerequisite Bottleneck Finder: which courses hurt most if their seats
# are cut, ranked, with a capacity sensitivity curve for the top course.
# ---------------------------------------------------------------------------

def capacity_bottleneck_ranking(
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
    n_students: int = 300,
    n_runs: int = 8,
) -> List[dict]:
    courses = courses or load_courses()
    config = config or load_config()

    capacity_courses = [c for c, r in courses.items() if r["seat_capacity"] is not None]
    results = []
    for code in capacity_courses:
        current_cap = courses[code]["seat_capacity"]
        halved = max(1, current_cap // 2)
        result = run_scenario(
            config,
            {"target": "course", "course": code, "param": "seat_capacity", "value": halved},
            courses=courses,
            n_students=n_students,
            n_runs=n_runs,
        )
        results.append({"course": code, "original_capacity": current_cap, "halved_capacity": halved, **result})

    results.sort(key=lambda r: (r["delta_terms"] or 0), reverse=True)
    return results[:5]


def capacity_sensitivity_curve(
    course: str,
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
    n_students: int = 300,
    n_runs: int = 8,
    capacity_levels: Optional[List[int]] = None,
) -> List[dict]:
    """For one course, sweep several capacity levels and report the mean graduation
    time at each — the "sensitivity curve" the brief asks for."""
    courses = courses or load_courses()
    config = config or load_config()
    original_cap = courses[course]["seat_capacity"]
    if original_cap is None:
        raise ValueError(f"{course} has unlimited capacity; nothing to sweep.")

    capacity_levels = capacity_levels or sorted(
        {max(1, original_cap // 4), max(1, original_cap // 2), max(1, int(original_cap * 0.75)), original_cap}
    )

    curve = []
    for cap in capacity_levels:
        scenario_courses = copy.deepcopy(courses)
        scenario_courses[course]["seat_capacity"] = cap
        mc = run_monte_carlo(n_students, n_runs, config=config, courses=scenario_courses, seed_start=3000)
        curve.append({"seat_capacity": cap, "mean_graduation_term": mc["mean_graduation_term"]})

    return sorted(curve, key=lambda r: r["seat_capacity"])


# ---------------------------------------------------------------------------
# T3.3 — Term Capacity Stress Test
# ---------------------------------------------------------------------------

def restrict_course_to_term_scenario(
    course: str,
    term: str,
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
    n_students: int = 300,
    n_runs: int = 8,
) -> dict:
    courses = courses or load_courses()
    config = config or load_config()
    result = run_scenario(
        config,
        {"target": "course", "course": course, "param": "offered", "value": [term]},
        courses=courses,
        n_students=n_students,
        n_runs=n_runs,
    )
    return {"course": course, "restricted_to": term, **result}


def remove_summer_scenario(
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
    n_students: int = 300,
    n_runs: int = 8,
) -> dict:
    courses = courses or load_courses()
    config = config or load_config()
    result = run_scenario(
        config,
        {"target": "term_cycle", "value": ["fall", "spring"]},
        courses=courses,
        n_students=n_students,
        n_runs=n_runs,
    )
    return {"scenario": "remove_summer", **result}


def term_restriction_comparison(
    course_candidates: List[str],
    term: str = "fall",
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
    n_students: int = 300,
    n_runs: int = 8,
) -> List[dict]:
    """Run the term-restriction scenario across 3 candidate core courses so results
    are comparable in one table (per the T3.3 brief: 'try 3 alternative scenarios')."""
    return [
        restrict_course_to_term_scenario(c, term, courses=courses, config=config, n_students=n_students, n_runs=n_runs)
        for c in course_candidates
    ]


if __name__ == "__main__":
    top5 = capacity_bottleneck_ranking(n_students=150, n_runs=5)
    print("Top capacity bottlenecks:")
    for r in top5:
        print(f"  {r['course']}: delta {r['delta_terms']:.2f} terms, {r['affected_students_pct']:.1f}% affected")
