"""
Tests for the per-course seat-capacity model (backend/capacity_model.py):
real recorded capacity taking priority over the static courses.json field,
the most-recent-year preference, and the scenario-building helpers used by
M5's capacity what-if analysis.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses, load_demand_history
from backend import capacity_model as cm

COURSES = load_courses()
DEMAND_HISTORY = load_demand_history()


def test_historical_capacity_uses_most_recent_year():
    fake_history = {
        "XYZ": {
            "2022_fall": {"capacity": 10, "pass_rate": 0.5},
            "2024_fall": {"capacity": 40, "pass_rate": 0.5},
            "2023_fall": {"capacity": 20, "pass_rate": 0.5},
        }
    }
    assert cm.historical_capacity(fake_history, "XYZ") == 40


def test_historical_capacity_filters_by_term():
    fake_history = {
        "XYZ": {
            "2023_fall": {"capacity": 10, "pass_rate": 0.5},
            "2023_spring": {"capacity": 99, "pass_rate": 0.5},
        }
    }
    assert cm.historical_capacity(fake_history, "XYZ", term="fall") == 10
    assert cm.historical_capacity(fake_history, "XYZ", term="spring") == 99


def test_historical_capacity_none_for_unknown_course():
    assert cm.historical_capacity(DEMAND_HISTORY, "NOT_A_REAL_COURSE") is None


def test_effective_capacity_prefers_real_history_over_static_field():
    # CMPS151 is "unlimited" (None) in courses.json but has real capacity on
    # record in demand_history.json - the real number must win.
    assert COURSES["CMPS151"]["seat_capacity"] is None
    eff = cm.effective_capacity(COURSES, DEMAND_HISTORY, "CMPS151", term="fall")
    assert eff is not None
    assert eff == cm.historical_capacity(DEMAND_HISTORY, "CMPS151", term="fall")


def test_effective_capacity_falls_back_to_static_field_with_no_history():
    fake_courses = {"ZZZ999": {"seat_capacity": 17}}
    assert cm.effective_capacity(fake_courses, {}, "ZZZ999") == 17


def test_effective_capacity_none_when_truly_unlimited():
    fake_courses = {"ZZZ999": {"seat_capacity": None}}
    assert cm.effective_capacity(fake_courses, {}, "ZZZ999") is None


def test_all_capacities_by_term_covers_every_offered_term():
    result = cm.all_capacities_by_term(COURSES, DEMAND_HISTORY)
    for code, record in COURSES.items():
        for term in record.get("offered", []):
            assert (code, term) in result


def test_override_capacity_sets_every_recorded_year():
    dh2 = cm.override_capacity_in_history(DEMAND_HISTORY, "CMPS151", 5)
    for entry in dh2["CMPS151"].values():
        assert entry["capacity"] == 5
    # original untouched
    assert all(v["capacity"] != 5 or v == dh2["CMPS151"][k] for k, v in DEMAND_HISTORY["CMPS151"].items())


def test_override_capacity_does_not_mutate_original():
    original_snapshot = {k: dict(v) for k, v in DEMAND_HISTORY["CMPS151"].items()}
    cm.override_capacity_in_history(DEMAND_HISTORY, "CMPS151", 5)
    assert DEMAND_HISTORY["CMPS151"] == {k: dict(v) for k, v in original_snapshot.items()}


def test_scale_capacity_halves_and_rounds_down():
    dh2 = cm.scale_capacity_in_history(DEMAND_HISTORY, 0.5)
    for code, entries in dh2.items():
        for term_key, entry in entries.items():
            original = DEMAND_HISTORY[code][term_key]["capacity"]
            assert entry["capacity"] == max(1, int(original * 0.5))


def test_scale_capacity_respects_codes_filter():
    dh2 = cm.scale_capacity_in_history(DEMAND_HISTORY, 0.5, codes={"CMPS151"})
    for term_key, entry in dh2["CMPS151"].items():
        assert entry["capacity"] == max(1, int(DEMAND_HISTORY["CMPS151"][term_key]["capacity"] * 0.5))
    # an untouched course should be unchanged
    other_code = next(c for c in DEMAND_HISTORY if c != "CMPS151" and c != "_meta")
    for term_key, entry in dh2[other_code].items():
        assert entry["capacity"] == DEMAND_HISTORY[other_code][term_key]["capacity"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
