"""No human-in-the-loop gate exists anywhere in prompt2render (docs/MIGRATION_INVENTORY.md §5). Stub that
never blocks — manual/async by definition, per the plugin-role table's "Off (manual, async —
never blocks an automated run)".
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class FeedbackHitlPlugin(Plugin):
    name = "feedback_hitl"

    def declare_dependencies(self) -> list[str]:
        return ["render_artifacts", "check_results"]

    def declare_effects(self) -> list[str]:
        return ["hitl_annotations"]

    def run(self, context: SceneContext) -> SceneContext:
        return context   # nothing to annotate without a human in the loop

    def _default_gate(self) -> bool:
        return False
