"""Storyboard -> AnimationIR bridge and validation gate.

Builds the typed, versioned, hashed :class:`~..animation_ir.AnimationIR`
(Phase 1) from ``context.storyboard_plan`` and stores it on the context.
Runs after ``verifier_storyboard`` so it never does this work on a
storyboard that already failed structural validation; its own remaining
failure surface is deep structural malformation (non-list ``sections``,
non-dict entries) that ``verifier_storyboard``'s ``.get()``-based checks
don't defend against.

Reuses the existing ``storyboard_failure`` finding_type/routing-table entry
(-> ``planner_llm``) rather than introducing a new one: the repair action for
either check failing is identical -- re-plan that storyboard section --
and ``planner_llm.revert_scene``/``regenerate_one`` are already fully
generic over finding_type.
"""
from __future__ import annotations

from ..animation_ir import AnimationIRValidationError, from_storyboard_plan
from ..context import SceneContext
from ..finding import Category, Finding, Severity, next_finding_id
from ..plugin import Plugin


class VerifierAnimationIrPlugin(Plugin):
    name = "verifier_animation_ir"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "storyboard_plan", "storyboard_verified"]

    def declare_effects(self) -> list[str]:
        return ["check_results", "animation_ir"]

    def run(self, context: SceneContext) -> SceneContext:
        try:
            context.animation_ir = from_storyboard_plan(context.storyboard_plan)
            context.check_results[self.name] = []
        except AnimationIRValidationError as exc:
            finding = Finding(
                finding_id=next_finding_id("air"),
                scene_id=exc.stem or "__all__",
                category=Category.STORYBOARD,
                severity=Severity.BLOCKING,
                message=str(exc),
                finding_type="storyboard_failure",
            )
            context.check_results[self.name] = [finding.as_check_result()]

        return context

    def _default_gate(self) -> bool:
        return True
