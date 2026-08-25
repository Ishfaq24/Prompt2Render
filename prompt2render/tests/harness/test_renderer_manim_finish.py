"""Tier 2 Phase 8-9: RendererManimFinishPlugin -- collects clips from
context.render_artifacts and calls finish.finish_manim, recording the
result into context.video_artifacts. finish_manim itself is unit-tested in
test_finish_manim.py; this covers the plugin-level wiring only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import RenderArtifact, SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.renderer_manim import RendererManimFinishPlugin


def _script_md(tmp_path) -> Path:
    script = tmp_path / "script.md"
    script.write_text(
        "## 1 - Intro\n> ANIM: intro brief\n\nHello.\n\n"
        "## 2 - Next\n> ANIM: next brief\n\nWorld.\n",
        encoding="utf-8",
    )
    return script


def test_collects_clips_and_records_video_artifacts(tmp_path, monkeypatch):
    ctx = SceneContext(project_dir=tmp_path, prompt=_script_md(tmp_path))
    ctx.scene_plan = [
        ScenePlanEntry(index=1, stem="01", title="Intro"),
        ScenePlanEntry(index=2, stem="02", title="Next"),
    ]
    ctx.render_artifacts["01"] = RenderArtifact(stem="01", clip=tmp_path / "a.mp4")
    ctx.render_artifacts["02"] = RenderArtifact(stem="02", clip=tmp_path / "b.mp4")

    final_path = tmp_path / "out" / "final.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"0" * 10)

    import prompt2render.finish as finish_module

    called_with = {}

    def fake_finish_manim(proj, script, section_clips, burn=False):
        called_with["proj"] = proj
        called_with["section_clips"] = section_clips
        called_with["burn"] = burn
        return final_path

    # RendererManimFinishPlugin.run() does `from .... import finish` -- a
    # local import inside the method -- so the target to patch is
    # prompt2render.finish itself (the shared module object), not the
    # importing file's namespace. Same pattern this session already hit for
    # cfg.warn/align.load.
    monkeypatch.setattr(finish_module, "finish_manim", fake_finish_manim)

    plugin = RendererManimFinishPlugin({"burn": True})
    plugin.run(ctx)

    assert called_with["section_clips"] == {
        "01": tmp_path / "a.mp4",
        "02": tmp_path / "b.mp4",
    }
    assert called_with["burn"] is True
    assert ctx.video_artifacts["01"].final_mp4 == final_path
    assert ctx.video_artifacts["02"].final_mp4 == final_path


def test_gate_is_hard_by_default():
    assert RendererManimFinishPlugin()._default_gate() is True
