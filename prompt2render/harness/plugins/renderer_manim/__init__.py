"""Wraps visuals.py::manim_scene() — the opt-in Manim escape hatch, disabled by default
(docs/MIGRATION_INVENTORY.md §5: "deliberately never LLM-driven ... wrap as a disabled-by-default
plugin"). Unlike every other plugin here, prompt2render never batches this over scene_plan — it's always a
single, manual `prompt2render manim <slug> <pyfile> <scene> <index>` call for one hand-authored hero shot.
This plugin mirrors that: it only acts when config names an explicit `py_file`/`scene`/`index` to
render; otherwise it's a no-op, same as the escape hatch being unused on a normal run.
"""
from __future__ import annotations

from pathlib import Path

from ...context import RenderArtifact, SceneContext
from ...plugin import Plugin
from ....project import parse_script
from ....visuals import manim_scene


class RendererManimPlugin(Plugin):
    name = "renderer_manim"

    def declare_dependencies(self) -> list[str]:
        return []

    def declare_effects(self) -> list[str]:
        return ["render_artifacts"]

    def run(self, context: SceneContext) -> SceneContext:
        py_file = self.config.get("py_file")
        scene = self.config.get("scene")
        index = self.config.get("index")
        if not (py_file and scene and index is not None):
            return context   # no-op: nothing configured to render, matches unused-by-default

        script = parse_script(context.prompt)
        out = manim_scene(context.project_dir, script, Path(py_file), scene, int(index))
        stem = f"{int(index):02d}"
        context.render_artifacts[stem] = RenderArtifact(stem=stem, outdir=out.parent,
                                                         manifest=[{"png": None, "mp4": str(out)}])
        return context

    def _default_gate(self) -> bool:
        return False
