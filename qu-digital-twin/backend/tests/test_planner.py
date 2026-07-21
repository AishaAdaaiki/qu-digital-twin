"""
Tests for M3 (T2.4 Planner, T2.5 Conflict Detector), run against the real QU CS
BSc curriculum. 5+ starting states from different points in the program
(freshman -> final term), verifying the planner never violates a prerequisite,
the Senior Project I compound gate (CMPS310 AND (CMPS350 OR CMPS405) AND >=84
completed credit hours), or the credit cap; and that the conflict detector
catches both prereq gaps and mock time overlaps.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.data_layer import load_courses
from backend.planner import plan_term, detect_conflicts

COURSES = load_courses()
with open(Path(__file__).parent.parent / "data" / "mock_schedule.json") as f:
    SCHEDULE = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

YEAR1_FALL = ["CMPS151", "MATH101", "CHEM101", "CHEM103", "ENGL202", "HIST121"]
YEAR1_SPRING = ["CMPS251", "MATH102", "MATH231", "PHYS191", "PHYS192", "ENGL203"]
YEAR2_FALL = ["CMPS200", "CMPS205", "PHYS193", "PHYS194"]
YEAR2_SPRING = ["CMPS303", "CMPS351", "CMPE263", "GENG200", "CORE_KS"]

STARTING_STATES = {
    "freshman": [],
    "sophomore": YEAR1_FALL + YEAR1_SPRING,
    "mid_degree": YEAR1_FALL + YEAR1_SPRING + YEAR2_FALL + YEAR2_SPRING,
    # Everything done except the two capstone courses AND the one_of gate courses -
    # CMPS493 must NOT be eligible yet even though CMPS310 and >=84 credits are done.
    "near_capstone_gate_unmet": [
        c for c in COURSES if c not in ("CMPS493", "CMPS499", "CMPS350", "CMPS405")
    ],
    # Same, but CMPS350/CMPS405 (the one_of pair) are both done - gate satisfied.
    "near_capstone_gate_met": [c for c in COURSES if c not in ("CMPS493", "CMPS499")],
    "final_term": [c for c in COURSES if c != "CMPS499"],
}


def _assert_valid_plan(completed, plan, max_credits):
    completed_set = set(completed)
    total = 0
    for code in plan:
        assert code not in completed_set, f"{code} already completed, replanned"
        missing = [p for p in COURSES[code]["prerequisites"] if p not in completed_set]
        assert not missing, f"{code} planned despite missing prereqs {missing}"
        total += COURSES[code]["credits"]
    assert total <= max_credits, f"plan uses {total} credits > cap {max_credits}"


def test_freshman_gets_intro_courses_no_prereq():
    plan = plan_term(STARTING_STATES["freshman"], {"term": "fall"}, COURSES, max_credits=18)
    _assert_valid_plan(STARTING_STATES["freshman"], plan, 18)
    assert len(plan) > 0
    assert all(not COURSES[c]["prerequisites"] for c in plan)


def test_sophomore_plan_respects_credit_cap():
    plan = plan_term(
        STARTING_STATES["sophomore"], {"term": "fall", "max_credits": 15}, COURSES, max_credits=18
    )
    _assert_valid_plan(STARTING_STATES["sophomore"], plan, 15)


def test_mid_degree_plan_valid():
    plan = plan_term(STARTING_STATES["mid_degree"], {"term": "fall"}, COURSES, max_credits=18)
    _assert_valid_plan(STARTING_STATES["mid_degree"], plan, 18)
    assert len(plan) > 0


def test_senior_project_gate_blocks_until_one_of_satisfied():
    plan = plan_term(
        STARTING_STATES["near_capstone_gate_unmet"], {"term": "fall"}, COURSES, max_credits=18
    )
    assert "CMPS493" not in plan, "CMPS493 must not be offered until CMPS350 or CMPS405 is done"


def test_senior_project_gate_opens_once_one_of_satisfied():
    plan = plan_term(
        STARTING_STATES["near_capstone_gate_met"], {"term": "fall"}, COURSES, max_credits=18
    )
    _assert_valid_plan(STARTING_STATES["near_capstone_gate_met"], plan, 18)
    assert "CMPS493" in plan


def test_final_term_plan_offers_only_cmps499():
    # CMPS499 (Senior Project II) is offered in spring per the source catalog.
    plan = plan_term(STARTING_STATES["final_term"], {"term": "spring"}, COURSES, max_credits=18)
    _assert_valid_plan(STARTING_STATES["final_term"], plan, 18)
    assert plan == ["CMPS499"]


def test_avoid_courses_respected():
    plan = plan_term(
        STARTING_STATES["freshman"], {"term": "fall", "avoid_courses": ["CMPS151"]}, COURSES, max_credits=18
    )
    assert "CMPS151" not in plan


# ---------------------------------------------------------------------------
# Conflict detector
# ---------------------------------------------------------------------------

def test_prereq_gap_detected():
    conflicts = detect_conflicts(["CMPS251"], [], COURSES, SCHEDULE)
    types = [c["type"] for c in conflicts]
    assert "prereq_gap" in types


def test_senior_project_gate_gap_detected():
    # CMPS310 done and >=84 credits, but neither CMPS350 nor CMPS405 done.
    conflicts = detect_conflicts(
        ["CMPS493"], STARTING_STATES["near_capstone_gate_unmet"], COURSES, SCHEDULE
    )
    gap = next((c for c in conflicts if c["course"] == "CMPS493"), None)
    assert gap is not None
    assert "CMPS350" in gap["detail"] or "CMPS405" in gap["detail"]


def test_time_overlap_detected():
    # CMPS200 and CMPS205 are deliberately given identical mock time slots.
    conflicts = detect_conflicts(["CMPS200", "CMPS205"], [], COURSES, SCHEDULE)
    types = [c["type"] for c in conflicts]
    assert "time_overlap" in types


def test_no_conflicts_for_clean_valid_plan():
    plan = plan_term(STARTING_STATES["freshman"], {"term": "fall", "max_credits": 8}, COURSES, max_credits=8)
    conflicts = detect_conflicts(plan, STARTING_STATES["freshman"], COURSES, SCHEDULE)
    prereq_gaps = [c for c in conflicts if c["type"] == "prereq_gap"]
    assert prereq_gaps == []


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
