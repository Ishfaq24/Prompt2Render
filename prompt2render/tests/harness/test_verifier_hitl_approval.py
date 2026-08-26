"""Tier 4, HUMAN_APPROVAL mode: VerifierHitlApprovalPlugin.

Covers the approve/missing-approval split, the gate-dependent status
(fail when gate=True, matching this plugin's own _default_gate; warn when
overridden False), and that it's a no-op producing zero findings for a
project with no rendered stems at all.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.plugins.verifier_hitl_approval import VerifierHitlApprovalPlugin


def _ctx_with_stems(tmp_path: Path, stems: list[str]) -> SceneContext:
    ctx = SceneContext(project_dir=tmp_path)
    for stem in stems:
        ctx.render_artifacts[stem] = RenderArtifact(stem=stem)
    return ctx


def test_default_gate_is_true():
    assert VerifierHitlApprovalPlugin()._default_gate() is True


def test_approved_stem_passes(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text(
        json.dumps({"01": {"status": "accept"}}), encoding="utf-8"
    )
    ctx = _ctx_with_stems(tmp_path, ["01"])

    VerifierHitlApprovalPlugin().run(ctx)

    results = ctx.check_results["verifier_hitl_approval"]
    assert results == [
        {
            "status": "pass",
            "stem": "01",
            "finding_type": "hitl_approval",
            "category": "SEMANTIC",
            "detail": "Human-approved (hitl_feedback.json accept).",
        }
    ]


def test_missing_approval_fails_when_gate_true(tmp_path):
    ctx = _ctx_with_stems(tmp_path, ["01"])

    VerifierHitlApprovalPlugin().run(ctx)

    results = ctx.check_results["verifier_hitl_approval"]
    assert len(results) == 1
    assert results[0]["status"] == "fail"
    assert results[0]["severity"] == "BLOCKING"
    assert results[0]["finding_type"] == "hitl_approval_missing"


def test_missing_approval_warns_when_gate_overridden_false(tmp_path):
    ctx = _ctx_with_stems(tmp_path, ["01"])

    VerifierHitlApprovalPlugin(config={"gate_override": False}).run(ctx)

    results = ctx.check_results["verifier_hitl_approval"]
    assert results[0]["status"] == "warn"
    assert results[0]["severity"] == "WARNING"


def test_reject_status_does_not_count_as_approved(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text(
        json.dumps({"01": {"status": "reject"}}), encoding="utf-8"
    )
    ctx = _ctx_with_stems(tmp_path, ["01"])

    VerifierHitlApprovalPlugin().run(ctx)

    assert ctx.check_results["verifier_hitl_approval"][0]["status"] == "fail"


def test_mixed_stems_only_missing_one_fails(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text(
        json.dumps({"01": {"status": "accept"}}), encoding="utf-8"
    )
    ctx = _ctx_with_stems(tmp_path, ["01", "02"])

    VerifierHitlApprovalPlugin().run(ctx)

    results = {r["stem"]: r["status"] for r in ctx.check_results["verifier_hitl_approval"]}
    assert results == {"01": "pass", "02": "fail"}


def test_no_rendered_stems_produces_no_findings(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    VerifierHitlApprovalPlugin().run(ctx)
    assert ctx.check_results["verifier_hitl_approval"] == []


def test_declares_no_check_results_double_counting():
    plugin = VerifierHitlApprovalPlugin()
    assert plugin.declare_dependencies() == ["render_artifacts"]
    assert plugin.declare_effects() == ["check_results"]
