"""Regression test for a dropped-keys bug in VerifierSpatialPlugin.

``_finding_for`` built a ``result`` dict with ``finding_type``,
``mismatch_subtype``, ``audit_level`` and ``recorded_problem`` all set on
it, then returned the untouched ``Finding`` object instead of ``result``.
The caller re-serialized via ``finding.as_check_result()``, silently
dropping all four keys -- routing still worked by accident (the router's
``_DEFAULT_FINDING_TYPE`` fallback), but the typed subtype and raw
SceneKit evidence never reached ``check_results``, so
``SceneQuality``/``quality_report`` bucketed every spatial finding as
``"unspecified"``.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.plugins.verifier_spatial import VerifierSpatialPlugin


def _ctx_with_audit_warning(gate: bool) -> SceneContext:
    ctx = SceneContext()
    ctx.render_artifacts["07"] = RenderArtifact(
        stem="07",
        audit={
            "status": "fail",
            "stills": 1,
            "warnings": ["FAIL [overlap] label overlaps the register"],
        },
    )
    return ctx


def test_finding_type_and_subtype_survive_into_check_results():
    plugin = VerifierSpatialPlugin({"gate_override": True})
    ctx = _ctx_with_audit_warning(gate=True)

    plugin.run(ctx)

    results = ctx.check_results["verifier_spatial"]
    assert len(results) == 1

    result = results[0]
    # These four keys used to be silently dropped by the bug.
    assert result["finding_type"] == "spatial_conflict"
    assert result["mismatch_subtype"] == "overlap"
    assert result["audit_level"] == "FAIL"
    assert result["recorded_problem"] == "FAIL [overlap] label overlaps the register"
    assert result["status"] == "fail"
    assert result["stem"] == "07"


def test_result_is_a_plain_dict_not_a_finding_object():
    plugin = VerifierSpatialPlugin({"gate_override": True})
    ctx = _ctx_with_audit_warning(gate=True)

    plugin.run(ctx)

    result = ctx.check_results["verifier_spatial"][0]
    assert isinstance(result, dict)
