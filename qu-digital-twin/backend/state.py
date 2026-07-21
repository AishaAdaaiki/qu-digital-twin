"""
Department state container (docs/department_simulation_architecture.md §1-3).

A DepartmentState bundles every data domain the department-level engines (M9-M13)
read from into one object. It's the "state" half of the CURRENT STATE + INTERVENTION
-> CANDIDATE NEW STATE pattern: engines and interventions take a DepartmentState in
and return a new one out, never mutating the original.

Each field maps 1:1 to a swappable JSON file in backend/data/ (or an uploaded
replacement from the frontend's State Manager page) via the loaders in
data_layer.py, so none of this module's code changes when the underlying data
does.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Dict, Optional

from backend import data_layer

# Course codes that are structural graduation-requirement placeholders ("pick one
# from the elective pool"), not real teachable/schedulable courses. Every engine
# that reasons about staffing, rooms, or scheduling excludes these; only the
# audit/planner (M2/M3) treat them as real slots to fill.
GENERIC_SLOT_CODES = {"ELEC1", "ELEC2", "ELEC3", "ELEC4"}


@dataclass
class DepartmentState:
    courses: Dict[str, dict] = field(default_factory=dict)
    substitution_rules: list = field(default_factory=list)
    mock_schedule: Dict[str, dict] = field(default_factory=dict)
    simulation_config: dict = field(default_factory=dict)
    elective_catalog: Dict[str, dict] = field(default_factory=dict)
    demand_history: Dict[str, dict] = field(default_factory=dict)
    faculty: Dict[str, dict] = field(default_factory=dict)
    rooms: Dict[str, dict] = field(default_factory=dict)
    accreditation_rules: dict = field(default_factory=dict)

    # Free-form label so scenarios saved for comparison (§6 Scenario Comparison)
    # can be told apart, e.g. "Baseline" vs "Hire 2 AI faculty + launch AI minor".
    label: str = "Baseline"

    def copy(self, label: Optional[str] = None) -> "DepartmentState":
        """Deep-copy every field so an intervention can freely mutate the copy
        without touching the original state - the non-mutation guarantee the
        whole intervention layer (backend/interventions.py) relies on."""
        new = DepartmentState(
            **{f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self) if f.name != "label"}
        )
        new.label = label if label is not None else self.label
        return new


def load_state(
    data_dir: Optional[Path] = None,
    overrides: Optional[Dict[str, Path]] = None,
    label: str = "Baseline",
) -> DepartmentState:
    """
    Load a full DepartmentState from backend/data/ (the bundled mock defaults),
    optionally overriding individual files - e.g. `overrides={"faculty": Path(
    "/tmp/uploaded_faculty.json")}` when the frontend's State Manager page has a
    freshly uploaded file for just one domain. Every other field still loads from
    the default location, so you never have to supply all nine files just to
    swap one.
    """
    overrides = overrides or {}

    def path_for(name: str, default: Path) -> Path:
        return overrides.get(name, default)

    return DepartmentState(
        courses=data_layer.load_courses(path_for("courses", data_layer.COURSES_PATH)),
        substitution_rules=data_layer.load_substitution_rules(
            path_for("substitution_rules", data_layer.SUBSTITUTION_RULES_PATH)
        ),
        mock_schedule=data_layer._load_json_dict(
            path_for("mock_schedule", data_layer.DATA_DIR / "mock_schedule.json")
        ),
        simulation_config=data_layer._load_json_dict(
            path_for("simulation_config", data_layer.DATA_DIR / "simulation_config.json")
        ),
        elective_catalog=data_layer.load_elective_catalog(
            path_for("elective_catalog", data_layer.ELECTIVE_CATALOG_PATH)
        ),
        demand_history=data_layer.load_demand_history(path_for("demand_history", data_layer.DEMAND_HISTORY_PATH)),
        faculty=data_layer.load_faculty(path_for("faculty", data_layer.FACULTY_PATH)),
        rooms=data_layer.load_rooms(path_for("rooms", data_layer.ROOMS_PATH)),
        accreditation_rules=data_layer.load_accreditation_rules(
            path_for("accreditation_rules", data_layer.ACCREDITATION_RULES_PATH)
        ),
        label=label,
    )


if __name__ == "__main__":
    state = load_state()
    print(
        f"Loaded state '{state.label}': {len(state.courses)} courses, "
        f"{len(state.elective_catalog)} catalog electives, {len(state.faculty)} faculty, "
        f"{len(state.rooms)} rooms, {len(state.demand_history)} courses with demand history."
    )
