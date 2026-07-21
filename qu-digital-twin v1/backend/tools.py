"""
CrewAI tool wrappers around the M2 (rule_engine) and M3 (planner) pure functions.

These are the ONLY way the M6 advising agent is allowed to produce a schedule,
a graduation-requirements list, a substitution verdict, or a conflict check. Every
tool here just calls the corresponding backend function and serializes the result
as JSON text for the LLM to read and relay — it never lets the LLM fill in the
answer itself. This is the architectural guarantee described in the project brief:
facts come from function calls, not from LLM generation.
"""
from __future__ import annotations

import json
from typing import List, Optional

from crewai.tools import BaseTool

from backend.data_layer import load_courses, load_substitution_rules
from backend.rule_engine import graduation_audit, substitution_check
from backend.planner import plan_term, detect_conflicts

_COURSES = load_courses()
_RULES = load_substitution_rules()
try:
    with open(__file__.rsplit("/", 1)[0] + "/data/mock_schedule.json") as _f:
        _SCHEDULE = {k: v for k, v in json.load(_f).items() if not k.startswith("_")}
except FileNotFoundError:
    _SCHEDULE = {}


class GraduationAuditTool(BaseTool):
    name: str = "graduation_audit"
    description: str = (
        "Given a student's completed course codes, return exactly what's left to "
        "graduate from the CS BSc program, grouped by category, with a credit "
        "summary. ALWAYS use this tool to answer 'what do I have left' questions "
        "— never guess remaining requirements yourself."
    )

    def _run(self, completed_courses: List[str]) -> str:
        result = graduation_audit(completed_courses, _COURSES)
        return json.dumps(result)


class SubstitutionCheckTool(BaseTool):
    name: str = "substitution_check"
    description: str = (
        "Given two course codes, return whether one can substitute for the other: "
        "'allowed', 'not_allowed', or 'needs_advisor', with a justification. ALWAYS "
        "use this tool before confirming any substitution — never improvise a verdict."
    )

    def _run(self, course_a: str, course_b: str) -> str:
        result = substitution_check(course_a, course_b, _RULES, _COURSES)
        return json.dumps(result)


class PlanTermTool(BaseTool):
    name: str = "plan_term"
    description: str = (
        "Given a student's completed course codes and preferences (term, "
        "max_credits, min_credits, avoid_courses, preferred_courses), return a "
        "valid next-term schedule that respects prerequisites and the credit cap. "
        "ALWAYS use this tool to produce a schedule — never generate a course list "
        "from memory."
    )

    def _run(
        self,
        completed_courses: List[str],
        term: str = "fall",
        max_credits: int = 15,
        min_credits: int = 12,
        avoid_courses: Optional[List[str]] = None,
        preferred_courses: Optional[List[str]] = None,
    ) -> str:
        preferences = {
            "term": term,
            "max_credits": max_credits,
            "min_credits": min_credits,
            "avoid_courses": avoid_courses or [],
            "preferred_courses": preferred_courses or [],
        }
        plan = plan_term(completed_courses, preferences, _COURSES, max_credits=max_credits)
        total_credits = sum(_COURSES[c]["credits"] for c in plan)
        return json.dumps({"plan": plan, "total_credits": total_credits, "term": term})


class DetectConflictsTool(BaseTool):
    name: str = "detect_conflicts"
    description: str = (
        "Given a proposed list of course codes and the student's completed courses, "
        "return any prerequisite gaps or mock-schedule time overlaps. ALWAYS call "
        "this before presenting a schedule as final, and before recommending any "
        "course the student hasn't already had prerequisites for."
    )

    def _run(self, proposed_courses: List[str], completed_courses: List[str]) -> str:
        conflicts = detect_conflicts(proposed_courses, completed_courses, _COURSES, _SCHEDULE)
        return json.dumps({"conflicts": conflicts, "clean": len(conflicts) == 0})


def build_tools() -> list:
    return [
        GraduationAuditTool(),
        SubstitutionCheckTool(),
        PlanTermTool(),
        DetectConflictsTool(),
    ]
