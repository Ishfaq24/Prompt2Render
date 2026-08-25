"""Tier 3 Phases 11-12 (F3/F4; motion traces): ObserverVisualPlugin.

``visual_observe.observe_clip``/``observe_motion`` are unit-tested in
tests/test_visual_observe.py; here the plugin's own responsibility is
tested in isolation via monkeypatch -- wiring RenderArtifact.audit/.motion
correctly, no-oping for already-observed/non-Manim stems, and never
touching check_results (verifier_spatial/verifier_motion own turning the
evidence into findings, for either renderer).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import prompt2render.harness.plugins.observer_visual as observer_visual_module
from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.plugins.observer_visual import ObserverVisualPlugin
from prompt2render.harness.temporal_ir import SectionTiming, StateTiming, TemporalIR


def _manim_artifact(stem: str, mp4: str = "clip.mp4") -> RenderArtifact:
    return RenderArtifact(
        stem=stem,
        manifest=[{"png": None, "mp4": mp4}],
    )


def test_populates_audit_for_manim_stem(tmp_path, monkeypatch):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.render_artifacts["01"] = _manim_artifact("01")

    fake_record = {"status": "pass", "unit": "frames", "stills": 3, "warnings": []}
    captured = {}

    def _fake_observe(clip_path, section_timing, *, scratch_dir, **kwargs):
        captured["clip_path"] = clip_path
        captured["scratch_dir"] = scratch_dir
        return fake_record

    monkeypatch.setattr(observer_visual_module.visual_observe, "observe_clip", _fake_observe)

    plugin = ObserverVisualPlugin()
    plugin.run(ctx)

    assert ctx.render_artifacts["01"].audit == fake_record
    assert captured["clip_path"] == Path("clip.mp4")
    assert captured["scratch_dir"] == tmp_path / "build" / "harness" / "visual_observe" / "01"


def test_populates_motion_for_manim_stem(tmp_path, monkeypatch):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.render_artifacts["01"] = _manim_artifact("01")

    monkeypatch.setattr(
        observer_visual_module.visual_observe,
        "observe_clip",
        lambda *a, **kw: {"status": "pass", "unit": "frames", "stills": 1, "warnings": []},
    )

    fake_motion = {"status": "ok", "traces": [{"state": "s1", "delta": 0.4, "start": 0.1, "end": 1.9}]}
    captured = {}

    def _fake_observe_motion(clip_path, section_timing, *, scratch_dir):
        captured["clip_path"] = clip_path
        captured["scratch_dir"] = scratch_dir
        return fake_motion

    monkeypatch.setattr(observer_visual_module.visual_observe, "observe_motion", _fake_observe_motion)

    plugin = ObserverVisualPlugin()
    plugin.run(ctx)

    assert ctx.render_artifacts["01"].motion == fake_motion
    assert captured["clip_path"] == Path("clip.mp4")
    assert captured["scratch_dir"] == tmp_path / "build" / "harness" / "visual_observe" / "01"


def test_skips_stem_that_already_has_audit(monkeypatch):
    ctx = SceneContext()
    artifact = _manim_artifact("01")
    artifact.audit = {"status": "pass", "stills": 5, "warnings": []}
    ctx.render_artifacts["01"] = artifact

    called = []
    monkeypatch.setattr(
        observer_visual_module.visual_observe,
        "observe_clip",
        lambda *a, **kw: called.append(1),
    )
    monkeypatch.setattr(
        observer_visual_module.visual_observe,
        "observe_motion",
        lambda *a, **kw: called.append(1),
    )

    plugin = ObserverVisualPlugin()
    plugin.run(ctx)

    assert called == []
    assert ctx.render_artifacts["01"].audit == {"status": "pass", "stills": 5, "warnings": []}
    assert ctx.render_artifacts["01"].motion is None


def test_skips_stem_with_no_mp4_manifest_entry(monkeypatch):
    """A stills-rendered stem's manifest has no "mp4" key -- nothing to
    observe, and this must never crash trying to Path(None)."""

    ctx = SceneContext()
    ctx.render_artifacts["01"] = RenderArtifact(
        stem="01",
        manifest=[{"png": "still_001.png"}],
    )

    called = []
    monkeypatch.setattr(
        observer_visual_module.visual_observe,
        "observe_clip",
        lambda *a, **kw: called.append(1),
    )

    plugin = ObserverVisualPlugin()
    plugin.run(ctx)

    assert called == []
    assert ctx.render_artifacts["01"].audit is None


def test_never_writes_check_results():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = _manim_artifact("01")

    plugin = ObserverVisualPlugin()
    plugin.run(ctx)

    assert "observer_visual" not in ctx.check_results


def test_passes_matching_section_timing_by_stem(monkeypatch):
    ctx = SceneContext()
    ctx.render_artifacts["02"] = _manim_artifact("02")

    timing_02 = SectionTiming(
        index=2,
        stem="02",
        target_duration=5.0,
        total_gap_seconds=0.0,
        states=[StateTiming(name="s", cue=0, run_time=1.0, wait=1.0)],
    )
    ctx.temporal_ir = TemporalIR(
        schema_version="1.0",
        source_semantic_hash="deadbeef",
        sections=[timing_02],
    )

    captured = {}

    def _fake_observe(clip_path, section_timing, *, scratch_dir, **kwargs):
        captured["section_timing"] = section_timing
        return {"status": "pass", "unit": "frames", "stills": 1, "warnings": []}

    monkeypatch.setattr(observer_visual_module.visual_observe, "observe_clip", _fake_observe)

    ObserverVisualPlugin().run(ctx)

    assert captured["section_timing"] is timing_02


def test_default_gate_is_advisory():
    assert ObserverVisualPlugin()._default_gate() is False


def test_declares_no_render_artifacts_effect():
    """render_artifacts is already owned by whichever renderer produced it
    -- declaring it here too would collide (only check_results is a
    mergeable effect)."""

    plugin = ObserverVisualPlugin()
    assert "render_artifacts" not in plugin.declare_effects()
    assert plugin.declare_dependencies() == ["render_artifacts"]
