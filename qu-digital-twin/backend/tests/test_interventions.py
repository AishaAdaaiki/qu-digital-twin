import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from backend.state import load_state
from backend.interventions import apply_intervention, apply_bundle, INTERVENTION_TYPES

STATE = load_state()


def test_all_intervention_types_are_dispatchable():
    # sanity: every registered type has a real callable behind it
    for itype, (handler, required) in INTERVENTION_TYPES.items():
        assert callable(handler)
        assert isinstance(required, list)


def test_unknown_intervention_type_raises():
    with pytest.raises(ValueError):
        apply_intervention(STATE, {"type": "not_a_real_move"})


def test_missing_required_field_raises():
    with pytest.raises(ValueError):
        apply_intervention(STATE, {"type": "add_faculty", "faculty_id": "F999"})  # missing 'record'


def test_apply_intervention_returns_new_state_not_mutating_original():
    new_state = apply_intervention(STATE, {
        "type": "resize_room", "room_id": "ENG_LAB_1", "new_capacity": 99,
    })
    assert new_state.rooms["ENG_LAB_1"]["capacity"] == 99
    assert STATE.rooms["ENG_LAB_1"]["capacity"] != 99


def test_apply_bundle_chains_multiple_interventions():
    bundle = [
        {"type": "add_faculty", "faculty_id": "F900", "record": {
            "name": "Bundle Test", "rank": "adjunct", "fte": 0.5, "max_courses_per_term": 1,
            "qualified_courses": [], "specializations": [], "status": "active", "annual_salary_qar": 60000,
        }},
        {"type": "resize_room", "room_id": "ENG_LAB_1", "new_capacity": 50},
    ]
    result = apply_bundle(STATE, bundle, label="Bundle scenario")
    assert "F900" in result.faculty
    assert result.rooms["ENG_LAB_1"]["capacity"] == 50
    assert result.label == "Bundle scenario"
    assert "F900" not in STATE.faculty
    assert STATE.rooms["ENG_LAB_1"]["capacity"] != 50


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
