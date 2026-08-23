"""Harness planning stages for narration and animation briefs.

The narration stage delegates only placeholder drafting to the existing draft.py
workflow. It never overwrites a user's authored narration unless force=true is
explicitly configured. The visual stage adds a deterministic contract to each
animation brief, so the coder receives the same layout and state requirements
for every topic without spending one extra LLM request per section.
"""
from __future__ import annotations

from ..context import SceneContext
from ..plugin import Plugin
from ... import cfg, draft


class PlannerScriptPlugin(Plugin):
    name = "planner_script"

    def declare_dependencies(self) -> list[str]:
        return ["prompt"]

    def declare_effects(self) -> list[str]:
        return ["script_artifact"]

    def run(self, context: SceneContext) -> SceneContext:
        force = bool(self.config.get("force", False))
        draft.draft(context.project_dir, force=force)
        return context

    def _default_gate(self) -> bool:
        return True


class PlannerVisualPlugin(Plugin):
    name = "planner_visual"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "pedagogy_verified"]

    def declare_effects(self) -> list[str]:
        return ["animation_plan"]

    def run(self, context: SceneContext) -> SceneContext:
        contract = (
            "\n\nHARNESS ANIMATION CONTRACT:"
            "\n- State the visual claim and the exact values shown in this section."
            "\n- Use one major visual per zone: title y=7.6..8.6, primary y=4.0..7.0, "
            "secondary y=1.5..3.5, caption y=0.85."
            "\n- Keep persistent objects at the same coordinates across adjacent sections."
            "\n- Every transition must preserve values unless the narration explicitly changes them."
            "\n- Use progressive reveal steps instead of placing unrelated major elements on one frame."
            "\n- Any illegal rule demonstration must be physically illegal and visibly marked; never relabel a legal state."
            "\n- Use only documented Scenekit primitives and valid input shapes."
        )
        for entry in context.scene_plan:
            if "HARNESS ANIMATION CONTRACT:" not in entry.anim:
                entry.anim = (entry.anim.rstrip() + contract).strip()
        return context

    def _default_gate(self) -> bool:
        return True
