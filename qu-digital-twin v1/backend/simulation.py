"""
M4 — Cohort Simulation + Monte Carlo (catalog tasks T3.1 Single-Cohort Flow
Simulator, T3.4 Graduation-Time Monte Carlo).

Reads exclusively from courses.json (via data_layer.load_courses) so M5's
scenario runner can swap in modified configs without touching this logic.

All randomness goes through a seeded numpy Generator, so every run is
reproducible given the same seed.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from backend.data_layer import load_courses

CONFIG_PATH = Path(__file__).parent / "data" / "simulation_config.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


class CohortSimulator:
    """
    Simulates a cohort of students moving term-by-term through one program's
    curriculum. One instance = one deterministic run for a given seed.
    """

    def __init__(
        self,
        courses: Dict[str, dict],
        config: dict,
        n_students: int = 100,
        seed: int = 0,
    ):
        self.courses = courses
        self.config = config
        self.n_students = n_students
        self.rng = np.random.default_rng(seed)
        self.term_cycle = config["term_cycle"]
        self.max_terms = config["max_terms"]
        self.max_credits = config["max_credits_per_term"]
        self.rates = config["pass_fail_withdraw_by_category"]

        self.total_courses = set(courses.keys())

        # per-student state
        self.completed = [set() for _ in range(n_students)]
        self.graduation_term = [None] * n_students  # term index (1-based) or None if stuck
        self.fail_counts = defaultdict(int)          # course -> total fail events (bottleneck signal)
        self.capacity_block_counts = defaultdict(int)  # course -> total capacity-block events

    def _base_gates_met(self, code: str, completed: set) -> bool:
        record = self.courses[code]
        if not all(p in completed for p in record["prerequisites"]):
            return False
        one_of = record.get("one_of_prerequisites")
        if one_of and not any(p in completed for p in one_of):
            return False
        min_credits = record.get("min_credits_required")
        if min_credits is not None:
            completed_credits = sum(self.courses[c]["credits"] for c in completed if c in self.courses)
            if completed_credits < min_credits:
                return False
        return True

    def _eligible_courses(self, completed: set, term: str) -> List[str]:
        eligible = []
        for code in self.courses:
            record = self.courses[code]
            if code in completed or term not in record["offered"]:
                continue
            if not self._base_gates_met(code, completed):
                continue
            # true mutual corequisites (e.g. a lecture/lab pair) must either be
            # already completed or co-enrollable this same term - otherwise `code`
            # isn't really eligible on its own.
            partners_ok = True
            for partner in record.get("symmetric_corequisites", []):
                if partner in completed:
                    continue
                if term not in self.courses[partner]["offered"] or not self._base_gates_met(partner, completed):
                    partners_ok = False
                    break
            if not partners_ok:
                continue
            eligible.append(code)
        return eligible

    def _bundle_for(self, code: str, completed: set) -> List[str]:
        bundle = [code]
        for partner in self.courses[code].get("symmetric_corequisites", []):
            if partner not in completed:
                bundle.append(partner)
        return bundle

    def _select_courses(self, eligible: List[str], completed: set) -> List[str]:
        category_priority = {
            "major_core": 0,
            "major_supporting": 0,
            "college": 1,
            "core_curriculum": 2,
            "major_elective": 3,
        }
        ordered = sorted(
            eligible,
            key=lambda c: (category_priority.get(self.courses[c].get("category", "major_elective"), 9), c),
        )
        plan, used = [], 0
        planned_set: set = set()
        for code in ordered:
            if code in planned_set:
                continue
            bundle = [c for c in self._bundle_for(code, completed) if c not in planned_set]
            bundle_credit = sum(self.courses[c]["credits"] for c in bundle)
            if used + bundle_credit <= self.max_credits:
                plan.extend(bundle)
                planned_set.update(bundle)
                used += bundle_credit
        return plan

    def run(self) -> dict:
        # seat_capacity enforcement is applied per (term_index, course): every student
        # requesting a capacity-limited course in the same term-offering competes for
        # a fixed number of seats.
        active = set(range(self.n_students))

        for term_idx in range(1, self.max_terms + 1):
            if not active:
                break
            term = self.term_cycle[(term_idx - 1) % len(self.term_cycle)]

            requests: Dict[str, List[int]] = defaultdict(list)
            student_plans: Dict[int, List[str]] = {}

            for s in list(active):
                eligible = self._eligible_courses(self.completed[s], term)
                plan = self._select_courses(eligible, self.completed[s])
                student_plans[s] = plan
                for code in plan:
                    requests[code].append(s)

            # enforce seat capacity: randomly admit up to capacity, bump the rest
            blocked_this_term: Dict[int, set] = defaultdict(set)
            for code, students in requests.items():
                cap = self.courses[code]["seat_capacity"]
                if cap is not None and len(students) > cap:
                    admitted = set(self.rng.choice(students, size=cap, replace=False).tolist())
                    for s in students:
                        if s not in admitted:
                            blocked_this_term[s].add(code)
                            self.capacity_block_counts[code] += 1

            for s in list(active):
                plan = [c for c in student_plans[s] if c not in blocked_this_term[s]]
                for code in plan:
                    cat = self.courses[code].get("category", "major_elective")
                    r = self.rates.get(cat, self.rates["major_elective"])
                    outcome = self.rng.choice(
                        ["pass", "fail", "withdraw"],
                        p=[r["pass"], r["fail"], r["withdraw"]],
                    )
                    if outcome == "pass":
                        self.completed[s].add(code)
                    else:
                        self.fail_counts[code] += 1

                if self.completed[s] == self.total_courses:
                    self.graduation_term[s] = term_idx
                    active.discard(s)

        stuck_students = [s for s in range(self.n_students) if self.graduation_term[s] is None]
        stuck_reasons = defaultdict(int)
        for s in stuck_students:
            remaining = self.total_courses - self.completed[s]
            for code in remaining:
                stuck_reasons[code] += 1

        bottlenecks = sorted(
            self.total_courses,
            key=lambda c: (self.fail_counts[c] + self.capacity_block_counts[c] + stuck_reasons[c]),
            reverse=True,
        )[:5]

        graduated_terms = [t for t in self.graduation_term if t is not None]

        return {
            "n_students": self.n_students,
            "graduation_term": self.graduation_term,
            "mean_graduation_term": float(np.mean(graduated_terms)) if graduated_terms else None,
            "median_graduation_term": float(np.median(graduated_terms)) if graduated_terms else None,
            "std_graduation_term": float(np.std(graduated_terms)) if graduated_terms else None,
            "n_stuck": len(stuck_students),
            "fail_counts": dict(self.fail_counts),
            "capacity_block_counts": dict(self.capacity_block_counts),
            "stuck_reasons": dict(stuck_reasons),
            "bottleneck_courses": bottlenecks,
        }


def run_cohort_simulation(
    n_students: int = 100,
    seed: int = 0,
    courses: Optional[Dict[str, dict]] = None,
    config: Optional[dict] = None,
) -> dict:
    courses = courses or load_courses()
    config = config or load_config()
    sim = CohortSimulator(courses, config, n_students=n_students, seed=seed)
    return sim.run()


def run_monte_carlo(
    n_students: int,
    n_runs: int,
    config: Optional[dict] = None,
    courses: Optional[Dict[str, dict]] = None,
    seed_start: int = 0,
) -> dict:
    """
    Run the cohort simulation n_runs times with different seeds and aggregate.

    Returns:
        {
            "mean_graduation_term": float,
            "std": float,
            "distribution": list[int],       # every graduated student's term, across all runs
            "n_stuck_total": int,
            "bottleneck_courses": list[str], # top 5 aggregated across all runs
        }
    """
    courses = courses or load_courses()
    config = config or load_config()

    all_terms: List[int] = []
    stuck_total = 0
    agg_scores: Dict[str, int] = defaultdict(int)

    for i in range(n_runs):
        result = run_cohort_simulation(
            n_students=n_students, seed=seed_start + i, courses=courses, config=config
        )
        all_terms.extend([t for t in result["graduation_term"] if t is not None])
        stuck_total += result["n_stuck"]
        for code, count in result["fail_counts"].items():
            agg_scores[code] += count
        for code, count in result["capacity_block_counts"].items():
            agg_scores[code] += count

    bottlenecks = sorted(agg_scores, key=agg_scores.get, reverse=True)[:5]

    return {
        "mean_graduation_term": float(np.mean(all_terms)) if all_terms else None,
        "std": float(np.std(all_terms)) if all_terms else None,
        "distribution": all_terms,
        "n_stuck_total": stuck_total,
        "bottleneck_courses": bottlenecks,
    }


def sensitivity_analysis(
    baseline_config: Optional[dict] = None,
    courses: Optional[Dict[str, dict]] = None,
    n_students: int = 200,
    n_runs: int = 20,
) -> List[dict]:
    """
    Perturb one parameter family at a time (core pass rate, math pass rate, seat
    capacity scale) and measure the effect on mean graduation time vs. baseline.
    Returns results sorted by |delta| descending (biggest driver of variance first).
    """
    courses = courses or load_courses()
    baseline_config = baseline_config or load_config()

    baseline = run_monte_carlo(n_students, n_runs, config=baseline_config, courses=courses, seed_start=1000)
    baseline_mean = baseline["mean_graduation_term"]

    perturbations = []

    # 1) major_core pass rate -5pp (fail absorbs the difference)
    cfg = json.loads(json.dumps(baseline_config))
    r = cfg["pass_fail_withdraw_by_category"]["major_core"]
    delta = 0.05
    r["pass"] -= delta
    r["fail"] += delta
    perturbations.append(("major_core_pass_rate_-5pp", cfg))

    # 2) college (math/physics/chem) pass rate -5pp
    cfg = json.loads(json.dumps(baseline_config))
    r = cfg["pass_fail_withdraw_by_category"]["college"]
    r["pass"] -= delta
    r["fail"] += delta
    perturbations.append(("college_pass_rate_-5pp", cfg))

    # 3) withdrawal rate +5pp across major_core (pass absorbs)
    cfg = json.loads(json.dumps(baseline_config))
    r = cfg["pass_fail_withdraw_by_category"]["major_core"]
    r["pass"] -= delta
    r["withdraw"] += delta
    perturbations.append(("major_core_withdraw_rate_+5pp", cfg))

    # 4) seat capacity halved for all capacity-limited courses
    cfg = json.loads(json.dumps(baseline_config))
    limited_courses = json.loads(json.dumps(courses))
    for code, rec in limited_courses.items():
        if rec["seat_capacity"] is not None:
            rec["seat_capacity"] = max(1, rec["seat_capacity"] // 2)
    perturbations.append(("seat_capacity_halved", (cfg, limited_courses)))

    results = []
    for name, payload in perturbations:
        if isinstance(payload, tuple):
            cfg_variant, courses_variant = payload
        else:
            cfg_variant, courses_variant = payload, courses
        mc = run_monte_carlo(n_students, n_runs, config=cfg_variant, courses=courses_variant, seed_start=1000)
        delta_mean = (mc["mean_graduation_term"] - baseline_mean) if mc["mean_graduation_term"] and baseline_mean else None
        results.append(
            {
                "parameter": name,
                "baseline_mean_terms": baseline_mean,
                "perturbed_mean_terms": mc["mean_graduation_term"],
                "delta_terms": delta_mean,
            }
        )

    results.sort(key=lambda r: abs(r["delta_terms"]) if r["delta_terms"] is not None else 0, reverse=True)
    return results


if __name__ == "__main__":
    result = run_cohort_simulation(n_students=100, seed=42)
    print(f"Mean graduation term: {result['mean_graduation_term']:.2f}, "
          f"stuck: {result['n_stuck']}, bottlenecks: {result['bottleneck_courses']}")
