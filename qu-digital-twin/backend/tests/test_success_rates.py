"""
Tests for the per-course success-rate model (backend/success_rates.py): own
historical rate lookup, the weighted prerequisite-chain nudge, and downstream
propagation when one course's rate is changed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses, load_demand_history
from backend.simulation import load_config
from backend import success_rates as sr

COURSES = load_courses()
DEMAND_HISTORY = load_demand_history()
CONFIG = load_config()


def test_historical_rate_averages_across_years():
    rate = sr.historical_rate(DEMAND_HISTORY, "CMPS151")
    entries = DEMAND_HISTORY["CMPS151"]
    expected = sum(v["pass_rate"] for v in entries.values()) / len(entries)
    assert abs(rate - expected) < 1e-9


def test_historical_rate_filters_by_term():
    # CMPS151 is fall-only, so filtering by "spring" should find nothing.
    assert sr.historical_rate(DEMAND_HISTORY, "CMPS151", term="spring") is None
    assert sr.historical_rate(DEMAND_HISTORY, "CMPS151", term="fall") is not None


def test_historical_rate_none_for_unknown_course():
    assert sr.historical_rate(DEMAND_HISTORY, "NOT_A_REAL_COURSE") is None


def test_effective_rate_with_no_prerequisites_equals_own_history():
    # CMPS151 has no prerequisites, so its effective rate is exactly its own history.
    own = sr.historical_rate(DEMAND_HISTORY, "CMPS151")
    eff = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151")
    assert abs(eff - own) < 1e-9


def test_effective_rate_is_nudged_by_prerequisite():
    # A course with a prerequisite should differ from its raw own-history rate
    # whenever the prerequisite's rate differs from its own.
    code = "CMPS251"
    own = sr.historical_rate(DEMAND_HISTORY, code)
    eff = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, code)
    prereq_rate = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151")
    if abs(own - prereq_rate) > 1e-6:
        assert abs(eff - own) > 1e-9
    expected = 0.8 * own + 0.2 * prereq_rate
    assert abs(eff - expected) < 1e-6


def test_effective_rate_falls_back_to_category_when_no_history():
    fake_courses = {
        "ZZZ999": {"name": "No-History Course", "credits": 3, "prerequisites": [],
                    "offered": ["fall"], "seat_capacity": None, "category": "major_elective"}
    }
    eff = sr.effective_rate(fake_courses, {}, CONFIG, "ZZZ999")
    assert abs(eff - sr.category_fallback_rate(CONFIG, "major_elective")) < 1e-9


def test_effective_rate_bounded_between_0_and_1():
    for code in COURSES:
        for term in COURSES[code].get("offered", []):
            r = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, code, term=term)
            assert 0.0 < r < 1.0


def test_build_course_probabilities_sum_to_one():
    probs = sr.build_course_probabilities_by_term(COURSES, DEMAND_HISTORY, CONFIG)
    assert probs  # non-empty
    for key, p in probs.items():
        total = p["pass"] + p["fail"] + p["withdraw"]
        assert abs(total - 1.0) < 1e-6
        assert p["pass"] > 0


def test_dependents_map_is_inverse_of_prerequisites():
    dependents = sr.build_dependents_map(COURSES)
    for code, record in COURSES.items():
        for prereq in record.get("prerequisites", []):
            assert code in dependents[prereq]


def test_downstream_of_includes_indirect_dependents():
    # CMPS151 -> CMPS251 -> CMPS351 (or similar multi-hop chain): whatever
    # directly depends on a direct dependent of CMPS151 should also appear.
    dependents = sr.build_dependents_map(COURSES)
    direct = dependents.get("CMPS151", [])
    downstream = sr.downstream_of(dependents, "CMPS151")
    assert set(direct).issubset(set(downstream))
    for d in direct:
        for indirect in dependents.get(d, []):
            assert indirect in downstream


def test_propagate_rate_change_lowers_downstream_when_new_rate_is_lower():
    current = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151")
    result = sr.propagate_rate_change(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151", new_rate=max(0.01, current - 0.3))
    assert result["affected_courses"], "CMPS151 should have downstream dependents in the real curriculum"
    for row in result["affected_courses"]:
        assert row["after"] <= row["before"] + 1e-9


def test_propagate_rate_change_effect_shrinks_with_distance():
    current = sr.effective_rate(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151")
    result = sr.propagate_rate_change(COURSES, DEMAND_HISTORY, CONFIG, "CMPS151", new_rate=max(0.01, current - 0.3))
    deltas = {row["course"]: abs(row["delta"]) for row in result["affected_courses"]}
    direct = set(sr.build_dependents_map(COURSES).get("CMPS151", []))
    indirect = set(deltas) - direct
    if direct and indirect:
        assert max(deltas[c] for c in direct) >= max(deltas[c] for c in indirect) - 1e-9


def test_propagate_rate_change_unknown_course_raises():
    import pytest
    with pytest.raises(ValueError):
        sr.propagate_rate_change(COURSES, DEMAND_HISTORY, CONFIG, "NOT_REAL", new_rate=0.5)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
