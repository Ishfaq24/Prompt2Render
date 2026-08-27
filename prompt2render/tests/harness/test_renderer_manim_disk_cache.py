"""RendererManimPlugin should not re-render a scene whose code is unchanged
and whose ``sections/<stem>.mp4`` already exists on disk from a prior
process.

Regression: unlike generator_manim (which caches generated code to disk and
prints "cached, skipping"), renderer_manim only ever consulted the
in-memory, per-process ``context.render_artifacts`` map. Since every
``prompt2render harness`` invocation starts a fresh SceneContext, an
unchanged scene was re-rendered (a real Manim subprocess, minutes per scene)
on every single run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, SceneContext
from prompt2render.harness.plugins.renderer_manim import RendererManimPlugin


def _script_md(tmp_path: Path) -> Path:
    script = tmp_path / "script.md"
    script.write_text(
        "## 1 - Intro\n> ANIM: intro brief\n\nHello.\n",
        encoding="utf-8",
    )
    return script


def _ctx_with_code_artifact(tmp_path: Path) -> tuple[SceneContext, Path]:
    ctx = SceneContext(project_dir=tmp_path, prompt=_script_md(tmp_path))

    py_file = tmp_path / "build" / "manim" / "scene_01.py"
    py_file.parent.mkdir(parents=True, exist_ok=True)
    py_file.write_text("class Scene01:\n    pass\n", encoding="utf-8")

    ctx.code_artifacts["01"] = CodeArtifact(
        stem="01", path=py_file, generated=True, accepted=False
    )
    return ctx, py_file


def test_skips_render_when_clip_already_on_disk_and_code_unchanged(
    tmp_path, monkeypatch
):
    ctx, py_file = _ctx_with_code_artifact(tmp_path)

    clip = tmp_path / "sections" / "01.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"0" * 10)
    # Clip must be at least as new as the code that (would) produce it.
    now = time.time()
    import os

    os.utime(py_file, (now - 10, now - 10))
    os.utime(clip, (now, now))

    def _boom(*a, **kw):
        raise AssertionError("manim_scene must not be called for a cached render")

    monkeypatch.setattr(
        "prompt2render.harness.plugins.renderer_manim.manim_scene", _boom
    )

    RendererManimPlugin({}).run(ctx)

    assert "01" in ctx.render_artifacts
    assert ctx.render_artifacts["01"].clip == clip
    assert ctx.render_artifacts["01"].manifest == [{"png": None, "mp4": str(clip)}]


def test_rerenders_when_code_is_newer_than_the_existing_clip(tmp_path, monkeypatch):
    ctx, py_file = _ctx_with_code_artifact(tmp_path)

    clip = tmp_path / "sections" / "01.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"0" * 10)

    now = time.time()
    import os

    # Code regenerated AFTER the on-disk clip -> clip is stale, must re-render.
    os.utime(clip, (now - 10, now - 10))
    os.utime(py_file, (now, now))

    called = {}

    def _fake_manim_scene(proj, script, pyfile, scene, index, out_dir=None):
        called["ran"] = True
        new_clip = clip.parent / "01.mp4"
        new_clip.write_bytes(b"1" * 10)
        return new_clip

    monkeypatch.setattr(
        "prompt2render.harness.plugins.renderer_manim.manim_scene",
        _fake_manim_scene,
    )

    RendererManimPlugin({}).run(ctx)

    assert called.get("ran") is True


def test_rerenders_when_stem_is_in_repair_context_even_with_a_disk_clip(
    tmp_path, monkeypatch
):
    ctx, py_file = _ctx_with_code_artifact(tmp_path)
    ctx.repair_context = {"01": object()}

    clip = tmp_path / "sections" / "01.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"0" * 10)

    now = time.time()
    import os

    os.utime(py_file, (now - 10, now - 10))
    os.utime(clip, (now, now))

    called = {}

    def _fake_manim_scene(proj, script, pyfile, scene, index, out_dir=None):
        called["ran"] = True
        new_clip = clip.parent / "01.mp4"
        new_clip.write_bytes(b"1" * 10)
        return new_clip

    monkeypatch.setattr(
        "prompt2render.harness.plugins.renderer_manim.manim_scene",
        _fake_manim_scene,
    )

    RendererManimPlugin({}).run(ctx)

    assert called.get("ran") is True
