import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state


def test_load_state_loads_all_domains():
    state = load_state()
    assert len(state.courses) == 41
    assert len(state.elective_catalog) == 18
    assert len(state.faculty) >= 15
    assert len(state.rooms) >= 8
    assert len(state.demand_history) == 59
    assert "min_credit_hours_by_category" in state.accreditation_rules
    assert state.label == "Baseline"


def test_copy_is_a_deep_copy_not_a_reference():
    state = load_state()
    copy_state = state.copy(label="Scenario A")
    copy_state.faculty["NEW_ID"] = {"name": "test"}
    copy_state.courses["CMPS151"]["credits"] = 999

    assert "NEW_ID" not in state.faculty
    assert state.courses["CMPS151"]["credits"] != 999
    assert copy_state.label == "Scenario A"
    assert state.label == "Baseline"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
