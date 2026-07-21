import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from backend.engines import org as org_engine

STATE = load_state()


def test_new_minor_feasibility_reports_all_courses():
    result = org_engine.new_minor_feasibility(
        STATE, "AI & Data Science Minor", ["CMPS403", "CMPS460", "CMPS453", "CMPS360"]
    )
    assert result["total_credits"] == 12
    assert len(result["per_course"]) == 4
    assert result["verdict"] in ("feasible", "feasible_flagged", "infeasible_no_room")


def test_new_minor_feasibility_flags_unknown_course():
    result = org_engine.new_minor_feasibility(STATE, "Bad Minor", ["FAKE999"])
    assert "error" in result


def test_split_program_impact_partitions_credits_correctly():
    total_before = sum(c["credits"] for c in STATE.courses.values())
    result = org_engine.split_program_impact(STATE, "AI & Data Science", ["CMPS380", "CMPS405"])
    assert result["moved_total_credits"] + result["remaining_total_credits"] == total_before


def test_split_program_impact_unknown_course_errors():
    result = org_engine.split_program_impact(STATE, "X", ["FAKE999"])
    assert "error" in result


def test_retirement_impact_includes_redistribution_and_grandfathering():
    result = org_engine.retirement_impact(STATE, "CMPE355")
    assert result["course"] == "CMPE355"
    assert "demand_redistribution" in result
    assert result["grandfather_terms"] == 2


def test_promote_elective_adds_to_program_without_mutating_original():
    new_state = org_engine.apply_promote_elective_to_program(STATE, "CMPS460")
    assert "CMPS460" in new_state.courses
    assert "CMPS460" not in STATE.courses
    assert new_state.courses["CMPS460"]["offered"] == ["spring"]


def test_promote_already_present_course_raises():
    import pytest
    with pytest.raises(ValueError):
        org_engine.apply_promote_elective_to_program(STATE, "CMPS151")


def test_retire_course_removes_it_and_cleans_up_prereq_references():
    new_state = org_engine.apply_retire_course(STATE, "CMPS251")
    assert "CMPS251" not in new_state.courses
    for rec in new_state.courses.values():
        assert "CMPS251" not in rec["prerequisites"]
    assert "CMPS251" in STATE.courses  # original untouched


def test_credit_hour_distribution_diff_shows_no_change_when_states_equal():
    diff = org_engine.credit_hour_distribution_diff(STATE, STATE)
    for row in diff["by_category"]:
        assert row["before"] == row["after"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
