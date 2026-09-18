"""Tests for _gate_layout in prompt2render/qc.py ensuring Manim clips are audited."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render import qc
from prompt2render.project import Script, Section


def _dummy_script(renderer: str = "manim") -> Script:
    sec1 = Section(index=1, title="Intro", anim="ANIM: Intro", narration="Hello world.")
    sec1.renderer = renderer
    return Script(meta={"title": "Test"}, sections=[sec1])


def test_gate_layout_manim_clean_passes(tmp_path):
    proj = tmp_path
    build_dir = proj / "build" / "manim_finish"
    build_dir.mkdir(parents=True)
    clip = build_dir / "01.mp4"
    clip.write_bytes(b"0" * 2048)

    script = _dummy_script("manim")
    gates = qc.Gates()

    with patch("prompt2render.manim_audit.ManimLayoutAuditor.audit_rendered_frames_3d") as mock_audit:
        mock_audit.return_value = {"ok": True, "findings": [], "frames_sampled": 3}
        qc._gate_layout(gates, proj, script)

    rows = gates.rows
    assert len(rows) == 1
    assert rows[0]["status"] == qc.PASS
    assert rows[0]["gate"] == "layout"
    assert "1 scenes clean" in rows[0]["detail"]


def test_gate_layout_manim_collision_fails(tmp_path):
    proj = tmp_path
    build_dir = proj / "build" / "manim_finish"
    build_dir.mkdir(parents=True)
    clip = build_dir / "01.mp4"
    clip.write_bytes(b"0" * 2048)

    script = _dummy_script("manim")
    gates = qc.Gates()

    with patch("prompt2render.manim_audit.ManimLayoutAuditor.audit_rendered_frames_3d") as mock_audit:
        mock_audit.return_value = {
            "ok": False,
            "findings": ["WARN [caption_collision] elements colliding in caption band"],
            "frames_sampled": 3,
        }
        qc._gate_layout(gates, proj, script)

    rows = gates.rows
    assert len(rows) == 1
    assert rows[0]["status"] == qc.FAIL
    assert rows[0]["gate"] == "layout"
    assert "1 of 1 scene checks fail" in rows[0]["detail"]


def test_gate_layout_no_scenes_skips(tmp_path):
    proj = tmp_path
    sec1 = Section(index=1, title="Intro", anim="ANIM: Intro", narration="Hello world.")
    sec1.renderer = "matplotlib"
    script = Script(meta={"title": "Test"}, sections=[sec1])
    gates = qc.Gates()

    qc._gate_layout(gates, proj, script)
    rows = gates.rows
    assert len(rows) == 1
    assert rows[0]["status"] == qc.SKIP
    assert rows[0]["gate"] == "layout"
