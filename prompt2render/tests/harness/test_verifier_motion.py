"""Tier 3 Phase 12 ("motion traces"): VerifierMotionPlugin.

Unlike observer_visual (which records raw deltas with no judgment),
verifier_motion owns the warn/pass decision -- these tests exercise that
decision directly: threshold crossing, hold-state suppression, and the
various "cannot judge" skip paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.plugins.verifier_motion import VerifierMotionPlugin
from prompt2render.harness.semantic_plan import (
    SemanticAnimationIR,
    SemanticSectionIR,
    SemanticStateIR,
)


def _artifact_with_motion(stem: str, traces: list[dict]) -> RenderArtifact:
    artifact = RenderArtifact(stem=stem)
    artifact.motion = {"status": "ok", "traces": traces}
    return artifact


def test_flags_low_delta_non_hold_state():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = _artifact_with_motion(
        "01",
        [{"state": "s1", "delta": 0.0001, "start": 0.1, "end": 1.9}],
    )

    plugin = VerifierMotionPlugin()
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert len(results) == 1
    assert results[0]["finding_type"] == "motion_absence"
    assert results[0]["status"] == "warn"
    assert "s1" in results[0]["detail"]


def test_suppresses_hold_flagged_state():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = _artifact_with_motion(
        "01",
        [{"state": "static", "delta": 0.0001, "start": 0.1, "end": 1.9}],
    )
    ctx.semantic_ir = SemanticAnimationIR(
        schema_version="1.0",
        source_ir_hash="deadbeef",
        sections=[
            SemanticSectionIR(
                index=1,
                stem="01",
                title="T",
                states=[SemanticStateIR(name="static", cue=0, hold=True)],
            )
        ],
    )

    plugin = VerifierMotionPlugin()
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert len(results) == 1
    assert results[0]["status"] == "pass"
    assert results[0]["finding_type"] == "motion_trace"


def test_high_delta_is_pass():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = _artifact_with_motion(
        "01",
        [{"state": "s1", "delta": 0.4, "start": 0.1, "end": 1.9}],
    )

    plugin = VerifierMotionPlugin()
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert results == [
        {
            "status": "pass",
            "stem": "01",
            "finding_type": "motion_trace",
            "category": "SPATIAL",
            "detail": "1 state(s) traced, motion present",
        }
    ]


def test_missing_motion_record_skips():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = RenderArtifact(stem="01")  # .motion is None

    plugin = VerifierMotionPlugin()
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert results[0]["status"] == "skip"
    assert results[0]["finding_type"] == "motion_trace_unavailable"


def test_non_ok_motion_status_skips():
    ctx = SceneContext()
    artifact = RenderArtifact(stem="01")
    artifact.motion = {"status": "skip", "detail": "no cv2", "traces": []}
    ctx.render_artifacts["01"] = artifact

    plugin = VerifierMotionPlugin()
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert results[0]["status"] == "skip"
    assert results[0]["detail"] == "no cv2"


def test_gate_override_promotes_to_blocking():
    ctx = SceneContext()
    ctx.render_artifacts["01"] = _artifact_with_motion(
        "01",
        [{"state": "s1", "delta": 0.0, "start": 0.0, "end": 1.0}],
    )

    plugin = VerifierMotionPlugin(config={"gate_override": True})
    plugin.run(ctx)

    results = ctx.check_results["verifier_motion"]
    assert results[0]["status"] == "fail"
    assert results[0]["severity"] == "BLOCKING"


def test_default_gate_is_advisory():
    assert VerifierMotionPlugin()._default_gate() is False
