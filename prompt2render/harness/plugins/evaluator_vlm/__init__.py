"""No vision-model call exists anywhere in prompt2render (docs/MIGRATION_INVENTORY.md §0/§3: this is
precisely the Code2Video capability that was retired — its layout critic needed a vision-model
call the affordable Gemini AI Studio endpoint didn't support, which is why scenekit.audit()'s
deterministic pixel-geometry check replaced it). Stub: runs, reports nothing, fabricates no VLM
call. Stage 5's ablation runner reports this column as honestly unpopulated rather than faked.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class EvaluatorVlmPlugin(Plugin):
    name = "evaluator_vlm"

    def declare_dependencies(self) -> list[str]:
        return ["render_artifacts", "scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        context.check_results[self.name] = []
        return context

    def _default_gate(self) -> bool:
        return False
