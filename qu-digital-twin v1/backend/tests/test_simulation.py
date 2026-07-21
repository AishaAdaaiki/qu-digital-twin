"""
Tests for M4 (T3.1 Cohort Simulator, T3.4 Monte Carlo). Verifies determinism
(same seed -> same result), that a full cohort run terminates and produces a
sane distribution, and that the Monte Carlo wrapper aggregates correctly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses
from backend.simulation import load_config, run_cohort_simulation, run_monte_carlo

COURSES = load_courses()
CONFIG = load_config()


def test_deterministic_with_same_seed():
    r1 = run_cohort_simulation(n_students=50, seed=7, courses=COURSES, config=CONFIG)
    r2 = run_cohort_simulation(n_students=50, seed=7, courses=COURSES, config=CONFIG)
    assert r1["graduation_term"] == r2["graduation_term"]


def test_different_seeds_can_differ():
    r1 = run_cohort_simulation(n_students=50, seed=1, courses=COURSES, config=CONFIG)
    r2 = run_cohort_simulation(n_students=50, seed=2, courses=COURSES, config=CONFIG)
    # not a strict requirement that they differ, but with 50 students and random
    # fail/withdraw draws it would be exceptionally unlikely for them to match
    assert r1["graduation_term"] != r2["graduation_term"]


def test_most_students_eventually_graduate_or_are_marked_stuck():
    result = run_cohort_simulation(n_students=100, seed=42, courses=COURSES, config=CONFIG)
    graduated = [t for t in result["graduation_term"] if t is not None]
    assert len(graduated) + result["n_stuck"] == 100
    assert result["mean_graduation_term"] is not None
    assert result["mean_graduation_term"] > 0


def test_bottleneck_courses_are_real_course_codes():
    result = run_cohort_simulation(n_students=100, seed=42, courses=COURSES, config=CONFIG)
    for code in result["bottleneck_courses"]:
        assert code in COURSES


def test_monte_carlo_aggregates_across_runs():
    mc = run_monte_carlo(n_students=30, n_runs=5, config=CONFIG, courses=COURSES, seed_start=0)
    assert len(mc["distribution"]) <= 30 * 5
    assert mc["mean_graduation_term"] is None or mc["mean_graduation_term"] > 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
