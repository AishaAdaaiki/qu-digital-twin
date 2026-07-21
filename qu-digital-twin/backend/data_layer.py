"""
M1 — Data Layer.

Single source of truth for the whole system. Every other module (rule_engine,
planner, simulation, scenarios, agent) reads courses through this module and
never opens backend/data/courses.json directly. That keeps the JSON schema in
exactly one place: if the schema changes, only load_courses() needs to change.

Schema (per course code):
    {
        "name": str,
        "credits": int,
        "prerequisites": list[str],   # course codes; corequisites from the source
                                       # catalog are merged in here (see README)
        "offered": list[str],         # subset of ["fall", "spring", "summer"]
        "seat_capacity": int | None,  # None = unlimited
        "category": str,              # "major_core" | "major_supporting" |
                                       # "college" | "core_curriculum" | "major_elective"

        # Optional extra gate, used only where the real program has a compound
        # graduation-eligibility rule that a flat AND-of-prerequisites can't
        # express (currently just Senior Project I: needs CMPS310 AND (CMPS350
        # OR CMPS405) AND >=84 completed credit hours):
        "one_of_prerequisites": list[str] | None,  # at least one must be completed
        "min_credits_required": int | None,        # completed credits threshold

        # Optional true mutual corequisites (e.g. a lecture/lab pair where each
        # course lists the other as a corequisite). planner.py/simulation.py
        # schedule these as a bundle rather than requiring one before the other,
        # since that would create an unsatisfiable cycle:
        "symmetric_corequisites": list[str] | None,
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

DATA_DIR = Path(__file__).parent / "data"
COURSES_PATH = DATA_DIR / "courses.json"
SUBSTITUTION_RULES_PATH = DATA_DIR / "substitution_rules.json"
ELECTIVE_CATALOG_PATH = DATA_DIR / "elective_catalog.json"
DEMAND_HISTORY_PATH = DATA_DIR / "demand_history.json"
FACULTY_PATH = DATA_DIR / "faculty.json"
ROOMS_PATH = DATA_DIR / "rooms.json"
ACCREDITATION_RULES_PATH = DATA_DIR / "accreditation_rules.json"

REQUIRED_FIELDS = {"name", "credits", "prerequisites", "offered", "seat_capacity"}


def load_courses(path: Path = COURSES_PATH) -> Dict[str, dict]:
    """Load and validate the course graph. Raises ValueError on schema violations."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    courses = {k: v for k, v in raw.items() if not k.startswith("_")}

    for code, record in courses.items():
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"{code} is missing required fields: {missing}")
        for prereq in record["prerequisites"]:
            if prereq not in courses:
                raise ValueError(f"{code} lists unknown prerequisite '{prereq}'")
        for prereq in record.get("one_of_prerequisites") or []:
            if prereq not in courses:
                raise ValueError(f"{code} lists unknown one_of_prerequisites entry '{prereq}'")

    return courses


def load_substitution_rules(path: Path = SUBSTITUTION_RULES_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_json_dict(path: Path) -> Dict[str, dict]:
    """Shared loader for the department-simulation data files (§3 of
    docs/department_simulation_architecture.md): elective_catalog, demand_history,
    faculty, rooms, accreditation_rules. All follow the same convention as
    courses.json - keys starting with '_' are metadata, not records."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_elective_catalog(path: Path = ELECTIVE_CATALOG_PATH) -> Dict[str, dict]:
    return _load_json_dict(path)


def load_demand_history(path: Path = DEMAND_HISTORY_PATH) -> Dict[str, dict]:
    return _load_json_dict(path)


def load_faculty(path: Path = FACULTY_PATH) -> Dict[str, dict]:
    return _load_json_dict(path)


def load_rooms(path: Path = ROOMS_PATH) -> Dict[str, dict]:
    return _load_json_dict(path)


def load_accreditation_rules(path: Path = ACCREDITATION_RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def total_program_credits(courses: Dict[str, dict]) -> int:
    return sum(c["credits"] for c in courses.values())


if __name__ == "__main__":
    courses = load_courses()
    print(f"Loaded {len(courses)} courses, {total_program_credits(courses)} total credits.")
