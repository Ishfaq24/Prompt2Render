"""Wraps project.parse_script — real, existing code.

Scoped differently than the brief's "auto-chunk long-form content into scenes": prompt2render sections are
manually delineated by a human writing `## N - Title` headers in script.md. There is no automatic
long-form chunking to wrap (see the migration plan's reconciliation #3); this plugin's job is
converting the file-based reach-around (script.md's structure) into an explicit `scene_plan` read.
"""
from __future__ import annotations

from ...context import ScenePlanEntry, SceneContext
from ...plugin import Plugin
from ....project import parse_script


class ChunkerScenePlugin(Plugin):
    name = "chunker_scene"

    def declare_dependencies(self) -> list[str]:
        return ["prompt"]

    def declare_effects(self) -> list[str]:
        return ["scene_plan"]

    def run(self, context: SceneContext) -> SceneContext:
        script = parse_script(context.prompt)
        context.scene_plan = [
            ScenePlanEntry(index=sec.index, stem=sec.stem, title=sec.title,
                           anim=sec.anim, narration_text=sec.narration)
            for sec in script.sections
        ]
        return context
