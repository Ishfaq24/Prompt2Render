"""RendererManimFinishPlugin -- collects clips from context.render_artifacts
and calls finish.finish_manim, recording the result into
context.video_artifacts and context.program. finish_manim itself is
unit-tested in test_finish_manim.py; this covers the plugin-level wiring.

Regression note: these tests used to construct ``RenderArtifact(clip=...)``
by hand, which masked a live bug -- no renderer in the codebase ever
assigned ``clip``, so in a real run this plugin always received an empty
clip map and ``finish_manim`` exited, making out/final.mp4 unreachable in
--manim mode. The tests below now build artifacts the way the *renderer*
actually does (manifest-only, and clip-populated) so the wiring is proven
against the real contract rather than a convenient fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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


def _wire_fake_finish(monkeypatch, tmp_path):
    """Patch finish.finish_manim and return (final_path, called_with).

    RendererManimFinishPlugin.run() does `from .... import finish` -- a
    local import inside the method -- so the target to patch is
    prompt2render.finish itself (the shared module object), not the
    importing file's namespace.
    """

    final_path = tmp_path / "out" / "final.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"0" * 10)

    import prompt2render.finish as finish_module

    called_with: dict = {}

    def fake_finish_manim(proj, script, section_clips, burn=False):
        called_with["proj"] = proj
        called_with["section_clips"] = section_clips
        called_with["burn"] = burn
        return final_path

    monkeypatch.setattr(finish_module, "finish_manim", fake_finish_manim)

    return final_path, called_with


def _two_section_ctx(tmp_path) -> SceneContext:
    ctx = SceneContext(project_dir=tmp_path, prompt=_script_md(tmp_path))
    ctx.scene_plan = [
        ScenePlanEntry(index=1, stem="01", title="Intro"),
        ScenePlanEntry(index=2, stem="02", title="Next"),
    ]
    return ctx


def test_collects_clips_from_manifest_as_the_renderer_writes_them(
    tmp_path, monkeypatch
):
    """The real regression guard for the unreachable-final.mp4 bug.

    Builds the artifacts the way RendererManimPlugin._render_one does --
    without hand-setting `clip` -- and requires the finish stage to still
    resolve every section's clip. Before the fix this produced an empty
    section_clips map.
    """

    ctx = _two_section_ctx(tmp_path)
    ctx.render_artifacts["01"] = RenderArtifact(
        stem="01", manifest=[{"png": None, "mp4": str(tmp_path / "a.mp4")}]
    )
    ctx.render_artifacts["02"] = RenderArtifact(
        stem="02", manifest=[{"png": None, "mp4": str(tmp_path / "b.mp4")}]
    )

    final_path, called_with = _wire_fake_finish(monkeypatch, tmp_path)

    RendererManimFinishPlugin({"burn": True}).run(ctx)

    assert called_with["section_clips"] == {
        "01": tmp_path / "a.mp4",
        "02": tmp_path / "b.mp4",
    }
    assert called_with["burn"] is True
    assert ctx.video_artifacts["01"].final_mp4 == final_path
    assert ctx.video_artifacts["02"].final_mp4 == final_path


def test_collects_clips_from_explicit_clip_field(tmp_path, monkeypatch):
    ctx = _two_section_ctx(tmp_path)
    ctx.render_artifacts["01"] = RenderArtifact(stem="01", clip=tmp_path / "a.mp4")
    ctx.render_artifacts["02"] = RenderArtifact(stem="02", clip=tmp_path / "b.mp4")

    final_path, called_with = _wire_fake_finish(monkeypatch, tmp_path)

    RendererManimFinishPlugin().run(ctx)

    assert called_with["section_clips"] == {
        "01": tmp_path / "a.mp4",
        "02": tmp_path / "b.mp4",
    }


def test_records_program_artifact_stamped_with_scene_revisions(
    tmp_path, monkeypatch
):
    ctx = _two_section_ctx(tmp_path)
    ctx.scene_versions = {"01": 1, "02": 3}
    ctx.render_artifacts["01"] = RenderArtifact(
        stem="01", manifest=[{"mp4": str(tmp_path / "a.mp4")}]
    )
    ctx.render_artifacts["02"] = RenderArtifact(
        stem="02", manifest=[{"mp4": str(tmp_path / "b.mp4")}]
    )

    final_path, _ = _wire_fake_finish(monkeypatch, tmp_path)

    RendererManimFinishPlugin().run(ctx)

    assert ctx.program is not None
    assert ctx.program.final_mp4 == final_path
    assert ctx.program.source_revisions == {"01": 1, "02": 3}
    assert ctx.program.source_fingerprint

    # A later repair of scene 02 must make the programme stale.
    from prompt2render.harness import lineage

    assert not lineage.program_is_stale(ctx)
    lineage.bump(ctx, "02")
    assert lineage.program_is_stale(ctx)


def test_gate_is_hard_by_default():
    assert RendererManimFinishPlugin()._default_gate() is True
