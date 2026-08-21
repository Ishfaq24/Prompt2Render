"""Wraps stills.render_many — the actual live renderer.

Not in the original 14 target folders (those name only `renderer_manim/`, correct for the
Code2Video-assumed architecture where Manim was the only renderer). Since Stage 0 resolved that
Prompt2Render migrates the live scenekit pipeline, this folder is a necessary addition — see the
migration plan's reconciliation #7. Usually a no-op in practice: `generator_code`'s underlying
call already rendered and accepted each section's stills, so `stills.is_current()` finds them
current unless a scene module was hand-edited afterward — matching prompt2render.py's own `_stills_jobs`.
"""
from __future__ import annotations

from ...context import RenderArtifact, SceneContext
from ...plugin import Plugin
from .... import align, stills


class RendererStillsPlugin(Plugin):
    name = "renderer_stills"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["render_artifacts"]

    def run(self, context: SceneContext) -> SceneContext:
        force = bool(self.config.get("force", False))
        jobs = []
        stems = []
        for stem, artifact in context.code_artifacts.items():
            if not artifact.accepted or artifact.path is None:
                continue
            outdir = stills.stills_dir(context.project_dir, stem)
            stems.append(stem)
            if not force and stills.is_current(artifact.path, outdir):
                continue
            n = len(align.load(context.project_dir, stem)["sentences"])
            jobs.append((stem, artifact.path, outdir, n - 1))

        if jobs:
            stills.render_many(jobs, workers=self.config.get("jobs"))

        for stem in stems:
            outdir = stills.stills_dir(context.project_dir, stem)
            manifest_path = outdir / "manifest.json"
            manifest = stills.manifest(context.project_dir, stem) if manifest_path.exists() else []
            context.render_artifacts[stem] = RenderArtifact(
                stem=stem, outdir=outdir, manifest=manifest,
                audit=stills.audit_record(outdir))
        return context
