import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from backend.engines import demand as demand_engine

STATE = load_state()


def test_forecast_returns_history_and_projection():
    result = demand_engine.forecast_course_demand(STATE, "CMPS303", n_terms_ahead=2)
    assert result["course"] == "CMPS303"
    assert len(result["history"]) == 3
    assert len(result["forecast"]) == 2
    assert result["trend_direction"] in ("growing", "declining", "flat")


def test_forecast_unknown_course_reports_error():
    result = demand_engine.forecast_course_demand(STATE, "FAKE999")
    assert "error" in result


def test_oversubscription_report_structure():
    report = demand_engine.oversubscription_report(STATE)
    assert isinstance(report, list)
    for row in report:
        assert row["status"] in ("oversubscribed", "underenrolled")


def test_mandatory_shock_flags_capacity_gap():
    result = demand_engine.simulate_mandatory_shock(STATE, "CMPS460", cohort_size_estimate=150)
    assert result["projected_demand_if_mandatory"] == 150
    assert result["capacity_gap"] is not None
    assert result["capacity_gap"] > 0  # 150 students will not fit in a GPU lab section


def test_retirement_redistributes_to_similar_courses():
    result = demand_engine.simulate_retirement(STATE, "CMPE355")
    assert result["course"] == "CMPE355"
    assert result["displaced_students"] >= 0
    assert isinstance(result["redistribution"], list)


def test_intake_shock_flags_overflow():
    flagged = demand_engine.simulate_intake_shock(STATE, pct_change=0.5)
    assert isinstance(flagged, list)
    for row in flagged:
        assert row["overflow"] > 0


def test_propose_new_elective_finds_similar_ml_courses():
    result = demand_engine.propose_new_elective(
        STATE,
        name="Deep Learning for Computer Vision",
        description="Convolutional neural networks, image classification, object detection, "
        "and deep learning architectures applied to visual data.",
    )
    codes = [c["course"] for c in result["similar_courses"]]
    assert "CMPE480" in codes  # Computer Vision should be the closest match
    assert result["verdict"] in ("feasible", "feasible_flagged", "infeasible_no_room")


def test_propose_new_elective_with_no_similarity_returns_insufficient_evidence():
    result = demand_engine.propose_new_elective(
        STATE, name="Xyzzy Plugh Wibble", description="qwzxjk vprmlq zzyx flrbnt"
    )
    assert result["verdict"] == "insufficient_evidence"


def test_propose_new_elective_never_hard_blocks_on_missing_faculty_alone():
    # Faculty gap alone must be a flag, not a hard block (project decision, docs §9)
    result = demand_engine.propose_new_elective(
        STATE, name="Quantum Computing", description="Quantum circuits, qubits, quantum algorithms, and quantum error correction."
    )
    if not result["faculty_matches"] and result["room_candidates"]:
        assert result["verdict"] != "infeasible_no_room"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
