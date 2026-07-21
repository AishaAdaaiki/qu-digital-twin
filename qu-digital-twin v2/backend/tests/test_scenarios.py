"""
Tests for M5 (T3.2 Bottleneck Finder, T3.3 Term Capacity Stress Test).
Uses small n_students/n_runs to keep the suite fast; correctness of the underlying
engine is already covered by test_simulation.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses
from backend.simulation import load_config
from backend.scenarios import (
    run_scenario,
    capacity_bottleneck_ranking,
    remove_summer_scenario,
    term_restriction_comparison,
)

COURSES = load_courses()
CONFIG = load_config()


def test_run_scenario_returns_comparable_means():
    result = run_scenario(
        CONFIG,
        {"target": "course", "course": "CMPS303", "param": "seat_capacity", "value": 5},
        courses=COURSES,
        n_students=40,
        n_runs=3,
    )
    assert result["baseline_mean"] is not None
    assert result["scenario_mean"] is not None
    assert 0 <= result["affected_students_pct"] <= 100


def test_capacity_bottleneck_ranking_returns_top5_real_courses():
    ranking = capacity_bottleneck_ranking(courses=COURSES, config=CONFIG, n_students=40, n_runs=2)
    assert len(ranking) <= 5
    for r in ranking:
        assert r["course"] in COURSES
        assert r["halved_capacity"] <= r["original_capacity"]


def test_remove_summer_scenario_runs():
    result = remove_summer_scenario(courses=COURSES, config=CONFIG, n_students=40, n_runs=3)
    assert result["scenario"] == "remove_summer"
    assert result["scenario_mean"] is not None


def test_term_restriction_comparison_across_3_courses():
    candidates = ["CMPS303", "CMPS351", "CMPS405"]
    results = term_restriction_comparison(
        candidates, term="fall", courses=COURSES, config=CONFIG, n_students=40, n_runs=2
    )
    assert len(results) == 3
    for r, code in zip(results, candidates):
        assert r["course"] == code
        assert r["restricted_to"] == "fall"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
