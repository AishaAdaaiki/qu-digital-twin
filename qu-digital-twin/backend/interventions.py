"""
L3 - Intervention layer (docs/department_simulation_architecture.md §2, §7).

A single dispatcher over every "Move" the five engines expose. This is what the
frontend's Propose a Change page calls: build one intervention dict (or a bundle
of several), hand it to apply_intervention()/apply_bundle(), get back a brand new
DepartmentState. The input state is never touched - every apply_* underneath
already returns a fresh copy (state.copy()), this module just routes to the right
one and validates the intervention shape.

Intervention dict shape: {"type": "<move name>", **kwargs for that move}.
See INTERVENTION_TYPES below for the full list and required kwargs.
"""
from __future__ import annotations

from typing import List

from backend.engines import faculty as faculty_engine
from backend.engines import org as org_engine
from backend.engines import space as space_engine
from backend.state import DepartmentState

# type -> (handler, required kwargs) - used for both dispatch and frontend form generation
INTERVENTION_TYPES = {
    "add_faculty": (faculty_engine.apply_add_faculty, ["faculty_id", "record"]),
    "remove_faculty": (faculty_engine.apply_remove_faculty, ["faculty_id"]),
    "set_faculty_status": (faculty_engine.apply_set_faculty_status, ["faculty_id", "status"]),
    "add_room": (space_engine.apply_add_room, ["room_id", "record"]),
    "remove_room": (space_engine.apply_remove_room, ["room_id"]),
    "resize_room": (space_engine.apply_resize_room, ["room_id", "new_capacity"]),
    "change_course_category": (org_engine.apply_change_course_category, ["code", "new_category"]),
    "promote_elective_to_program": (org_engine.apply_promote_elective_to_program, ["code"]),
    "retire_course": (org_engine.apply_retire_course, ["code"]),
}


def apply_intervention(state: DepartmentState, intervention: dict) -> DepartmentState:
    """Apply one intervention dict, e.g. {"type": "add_faculty", "faculty_id": "F200",
    "record": {...}}. Raises ValueError on an unknown type or missing kwargs."""
    itype = intervention.get("type")
    if itype not in INTERVENTION_TYPES:
        raise ValueError(f"Unknown intervention type '{itype}'. Known types: {sorted(INTERVENTION_TYPES)}")

    handler, required = INTERVENTION_TYPES[itype]
    missing = [k for k in required if k not in intervention]
    if missing:
        raise ValueError(f"Intervention '{itype}' missing required field(s): {missing}")

    kwargs = {k: intervention[k] for k in required}
    return handler(state, **kwargs)


def apply_bundle(state: DepartmentState, interventions: List[dict], label: str = None) -> DepartmentState:
    """Apply several interventions in sequence, each building on the last, and
    return one final new state - e.g. 'hire 2 faculty AND open a new lab AND
    launch the AI minor' as a single combined proposal (docs §6)."""
    current = state
    for intervention in interventions:
        current = apply_intervention(current, intervention)
    if label:
        current.label = label
    return current
