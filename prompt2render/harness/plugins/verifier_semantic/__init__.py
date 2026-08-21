"""No live semantic-correctness checker exists in prompt2render — nothing verifies generated code against
the intent in scene_plan beyond what scenekit's geometric audit catches (verifier_spatial). Stub:
runs, always reports a clean pass, no fabricated checking logic. Soft gate by default.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class VerifierSemanticPlugin(Plugin):
    name = "verifier_semantic"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts", "scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        context.check_results[self.name] = []
        return context

    def _default_gate(self) -> bool:
        return False
