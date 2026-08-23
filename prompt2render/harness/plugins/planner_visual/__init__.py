"""Backward-compatible import for the harness visual planner.

The canonical implementation lives in ``planner_script`` alongside the
script planner. Keeping the implementation in one location ensures that
script planning and visual-contract planning evolve under the same upstream
contract.

This module exists solely to preserve legacy import paths and should contain
no planning logic.
"""

from ..planner_script import PlannerVisualPlugin

__all__ = [
    "PlannerVisualPlugin",
]