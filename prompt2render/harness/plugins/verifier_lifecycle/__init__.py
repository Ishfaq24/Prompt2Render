"""Confirmed to have zero existing implementation anywhere in prompt2render (docs/MIGRATION_INVENTORY.md
§7: no cross-scene object identity exists — each section renders independently; grepping prompt2render/ and
scenes.py for object|lifecycle|identity|persist|carry.*forward turns up no real hits). Ships as
the always-`[]` shell the migration brief specifies for Stage 5's ablation runner.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class VerifierLifecyclePlugin(Plugin):
    name = "verifier_lifecycle"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts", "object_table"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        context.check_results[self.name] = []
        return context

    def _default_gate(self) -> bool:
        return False
