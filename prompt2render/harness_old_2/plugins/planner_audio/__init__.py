"""Doesn't plan narration — narration already exists, synthesized and force-aligned by
voice.py/align.py from script.md directly, well before this harness's generation loop runs (see
the migration plan's reconciliation #2). This plugin's honest role is ingesting that
already-produced timing into context.narration, not generating it.
"""
from __future__ import annotations

from ...context import NarrationEntry, SceneContext
from ...plugin import Plugin
from .... import align


class PlannerAudioPlugin(Plugin):
    name = "planner_audio"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "alignment_artifact"]

    def declare_effects(self) -> list[str]:
        return ["narration"]

    def run(self, context: SceneContext) -> SceneContext:
        for entry in context.scene_plan:
            data = align.load(context.project_dir, entry.stem)
            context.narration[entry.stem] = NarrationEntry(
                stem=entry.stem, sentences=data["sentences"], source="align")
        return context
