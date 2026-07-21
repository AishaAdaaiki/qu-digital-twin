import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.state import load_state
from backend.engines import accreditation

STATE = load_state()


def test_credit_hour_checks_cover_all_categories():
    checks = accreditation.check_credit_hour_minimums(STATE)
    categories = {c["rule"] for c in checks}
    assert len(categories) == 5


def test_class_size_checks_only_cover_courses_with_capacity_and_room_type():
    checks = accreditation.check_class_size(STATE)
    for c in checks:
        assert "course" in c
        assert c["actual"] is not None


def test_student_faculty_ratio_check_computes_a_ratio():
    result = accreditation.check_student_faculty_ratio(STATE)
    assert result["actual"] is not None
    assert result["active_faculty_fte"] > 0


def test_student_faculty_ratio_accepts_override():
    result = accreditation.check_student_faculty_ratio(STATE, total_students=1000)
    assert result["total_students_estimate"] == 1000
    assert result["pass"] is False  # 1000 students should blow the ratio


def test_scorecard_summary_counts_match_individual_checks():
    scorecard = accreditation.compliance_scorecard(STATE)
    total = len(scorecard["credit_hour_checks"]) + len(scorecard["class_size_checks"]) + 1
    assert scorecard["summary"]["total_checks"] == total
    assert scorecard["summary"]["passed"] + scorecard["summary"]["failed"] == total


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
