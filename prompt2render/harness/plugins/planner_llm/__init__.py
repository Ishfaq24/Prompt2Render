"""No live LLM planning call exists anywhere in prompt2render — see the migration plan's reconciliation #1.
The "plan" is the human-authored `> ANIM:` brief chunker_scene already extracted into
`scene_plan`. This plugin is an honest passthrough (marks each entry as planned) rather than
inventing an LLM call prompt2render doesn't make; planner and coder were already fused into one call
(scenes.py generate()) before this migration, and splitting them is a real behavior change,
deliberately not attempted here.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class PlannerLlmPlugin(Plugin):
    name = "planner_llm"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["scene_plan"]

    def run(self, context: SceneContext) -> SceneContext:
        for entry in context.scene_plan:
            entry.planned = True
        return context

    def _default_gate(self) -> bool:
        return False
