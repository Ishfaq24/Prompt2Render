"""Tier 2 Phase 8-9: VerifierManimFinalQcPlugin -- a deliberately minimal
Manim-mode final QC (out/final.mp4 exists with video+audio streams), not
full parity with the stills pipeline's stills-coupled qc.check().

ffprobe is mocked directly (same pattern test_manim_temporal_verifier.py
already uses for VerifierTemporalPlugin's own ffprobe wrapper).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import SceneContext
from prompt2render.harness.plugins.renderer_manim import VerifierManimFinalQcPlugin


def test_missing_final_video_fails():
    ctx = SceneContext(project_dir=Path("/nonexistent/project"))
    VerifierManimFinalQcPlugin().run(ctx)

    findings = ctx.check_results["verifier_manim_final_qc"]
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert findings[0]["finding_type"] == "final_qc_failure"
    assert "was not produced" in findings[0]["detail"]


def test_missing_audio_stream_fails(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "final.mp4").write_bytes(b"0" * 10)

    ctx = SceneContext(project_dir=tmp_path)

    with patch("subprocess.run") as mock_run:
        result = MagicMock()
        result.stdout = "video\n"  # no audio stream reported
        mock_run.return_value = result

        VerifierManimFinalQcPlugin().run(ctx)

    findings = ctx.check_results["verifier_manim_final_qc"]
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert "audio" in findings[0]["detail"]


def test_video_and_audio_present_passes(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "final.mp4").write_bytes(b"0" * 10)

    ctx = SceneContext(project_dir=tmp_path)

    with patch("subprocess.run") as mock_run:
        result = MagicMock()
        result.stdout = "video\naudio\n"
        mock_run.return_value = result

        VerifierManimFinalQcPlugin().run(ctx)

    findings = ctx.check_results["verifier_manim_final_qc"]
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"


def test_gate_is_hard_by_default():
    assert VerifierManimFinalQcPlugin()._default_gate() is True
