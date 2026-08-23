"""Compatibility import for the harness animation planner.

The implementation lives beside planner_script so script and visual planning
can be versioned as one upstream contract. The registry imports that class
directly; this re-export keeps older imports working.
"""
from ..planner_script import PlannerVisualPlugin

__all__ = ["PlannerVisualPlugin"]
