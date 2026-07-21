import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from backend.engines import faculty as faculty_engine

STATE = load_state()


def test_generic_slot_codes_excluded_from_staffing():
    result = faculty_engine.auto_assign_faculty(STATE, "fall")
    for slot in ("ELEC1", "ELEC2", "ELEC3", "ELEC4"):
        assert slot not in result["assignment"]
        assert slot not in result["unteachable_courses"]


def test_no_faculty_assigned_beyond_max_load():
    result = faculty_engine.auto_assign_faculty(STATE, "fall")
    for fid, load in result["faculty_load"].items():
        max_load = STATE.faculty[fid]["max_courses_per_term"]
        assert load <= max_load


def test_on_leave_faculty_never_assigned():
    result = faculty_engine.auto_assign_faculty(STATE, "fall")
    on_leave = {fid for fid, f in STATE.faculty.items() if f.get("status") != "active"}
    assigned_faculty = {fid for fid in result["assignment"].values() if fid}
    assert not (on_leave & assigned_faculty)


def test_workload_report_only_includes_active_faculty():
    report = faculty_engine.workload_report(STATE, "fall")
    reported_ids = {r["faculty_id"] for r in report}
    for fid in reported_ids:
        assert STATE.faculty[fid]["status"] == "active"


def test_hiring_impact_never_worsens_teachability():
    hire = {
        "name": "Dr. Test Hire", "rank": "assistant_professor", "fte": 1.0, "max_courses_per_term": 3,
        "qualified_courses": ["CMPS200"], "specializations": ["computing_ethics"],
        "status": "active", "annual_salary_qar": 300000,
    }
    impact = faculty_engine.hiring_impact(STATE, hire, "fall")
    assert set(impact["unteachable_after"]).issubset(set(impact["unteachable_before"]))


def test_add_remove_faculty_moves_do_not_mutate_original():
    new_state = faculty_engine.apply_add_faculty(STATE, "F999", {
        "name": "Temp", "rank": "adjunct", "fte": 0.5, "max_courses_per_term": 1,
        "qualified_courses": [], "specializations": [], "status": "active", "annual_salary_qar": 50000,
    })
    assert "F999" in new_state.faculty
    assert "F999" not in STATE.faculty

    removed_state = faculty_engine.apply_remove_faculty(new_state, "F999")
    assert "F999" not in removed_state.faculty
    assert "F999" in new_state.faculty  # new_state itself still untouched


def test_remove_unknown_faculty_raises():
    import pytest
    with pytest.raises(ValueError):
        faculty_engine.apply_remove_faculty(STATE, "NOT_REAL")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
