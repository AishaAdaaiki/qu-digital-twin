"""
Tests for M2 (T2.2 Graduation Audit, T2.3 Substitution Checker), run against the
real QU CS BSc curriculum in backend/data/courses.json (41 courses, 120 credit
hours). 5 authored student states for the audit, 10 authored course pairs for
substitution, as specified in the catalog brief.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses, load_substitution_rules
from backend.rule_engine import graduation_audit, substitution_check

COURSES = load_courses()
RULES = load_substitution_rules()

# ---------------------------------------------------------------------------
# T2.2 — 5 authored student states, spanning freshman year to final term
# ---------------------------------------------------------------------------

YEAR1_FALL = ["CMPS151", "MATH101", "CHEM101", "CHEM103", "ENGL202", "HIST121"]
YEAR1_SPRING = ["CMPS251", "MATH102", "MATH231", "PHYS191", "PHYS192", "ENGL203"]
YEAR2_FALL = ["CMPS200", "CMPS205", "PHYS193", "PHYS194"]
YEAR2_SPRING = ["CMPS303", "CMPS351", "CMPE263", "GENG200", "CORE_KS"]

STUDENT_STATES = {
    "freshman_day_one": [],
    "sophomore_midway": YEAR1_FALL + YEAR1_SPRING,
    "junior_on_track": YEAR1_FALL + YEAR1_SPRING + YEAR2_FALL + YEAR2_SPRING,
    "senior_final_term": [code for code in COURSES if code != "CMPS499"],
    "unknown_transfer_credit": ["CMPS151", "MATH101", "TRANSFER_XYZ999"],
}


def test_freshman_has_everything_remaining():
    result = graduation_audit(STUDENT_STATES["freshman_day_one"], COURSES)
    assert result["completed_credits"] == 0
    assert result["remaining_credits"] == result["total_program_credits"]
    assert result["total_program_credits"] == 120
    assert len(result["remaining"]) == len(COURSES)


def test_sophomore_midway_partial_progress():
    result = graduation_audit(STUDENT_STATES["sophomore_midway"], COURSES)
    assert "CMPS303" in result["remaining"]
    assert 0 < result["completed_credits"] < result["total_program_credits"]


def test_junior_on_track_grouped_by_category():
    result = graduation_audit(STUDENT_STATES["junior_on_track"], COURSES)
    assert "CMPS310" in result["remaining"]
    assert "major_core" in result["remaining_by_category"] or "major_elective" in result["remaining_by_category"]


def test_senior_final_term_only_capstone_left():
    result = graduation_audit(STUDENT_STATES["senior_final_term"], COURSES)
    assert result["remaining"] == ["CMPS499"]


def test_unknown_transfer_credit_flagged_not_silently_dropped():
    result = graduation_audit(STUDENT_STATES["unknown_transfer_credit"], COURSES)
    assert "TRANSFER_XYZ999" in result["unknown_completed"]
    assert "CMPS151" not in result["remaining"]


# ---------------------------------------------------------------------------
# T2.3 — 10 authored substitution pairs
# ---------------------------------------------------------------------------

SUBSTITUTION_CASES = [
    ("CMPS350", "CMPS405", "needs_advisor"),
    ("CMPS493", "CMPS499", "not_allowed"),
    ("MATH101", "MATH102", "not_allowed"),
    ("ENGL202", "ARAB100", "not_allowed"),
    ("CORE_KS", "NAT_SCI", "not_allowed"),
    ("HUM_FA", "SOC_BEH", "not_allowed"),
    ("CMPS200", "DAWA111", "not_allowed"),
    ("PHYS191", "CHEM101", "not_allowed"),
    ("CMPS303", "CMPS323", "not_allowed"),
    ("ELEC1", "ELEC2", "allowed"),
]


def test_substitution_cases():
    for course_a, course_b, expected in SUBSTITUTION_CASES:
        result = substitution_check(course_a, course_b, RULES, COURSES)
        assert result["verdict"] == expected, (
            f"{course_a} <-> {course_b}: expected {expected}, got {result['verdict']}"
        )
        assert result["justification"], "every verdict must carry a justification"


def test_no_encoded_rule_defers_to_advisor():
    # CMPS151 <-> CMPS405 has no encoded rule; must defer, not guess.
    result = substitution_check("CMPS151", "CMPS405", RULES, COURSES)
    assert result["verdict"] == "needs_advisor"


def test_unknown_course_defers_to_advisor():
    result = substitution_check("CMPS151", "FAKE999", RULES, COURSES)
    assert result["verdict"] == "needs_advisor"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
