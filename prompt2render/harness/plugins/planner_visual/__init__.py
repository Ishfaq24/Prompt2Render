"""No live visual-planning call exists in prompt2render — scenes.py's one LLM call already produces
executable drawing code directly, with no separate visual-requirements intermediate. True no-op,
kept only because the target plugin-folder list requires the role to exist. Disabled by default
in config.yaml.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class PlannerVisualPlugin(Plugin):
    name = "planner_visual"

    def declare_dependencies(self) -> list[str]:
        return []

    def declare_effects(self) -> list[str]:
        return []

    def run(self, context: SceneContext) -> SceneContext:
        return context

    def _default_gate(self) -> bool:
        return False
