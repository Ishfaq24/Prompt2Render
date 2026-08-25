"""Tier 3 Phase 11 (F3): deterministic visual grounding.

``ink_fraction`` is tested against real cv2/numpy arithmetic (both are real
project dependencies, not mocked) since it is the arithmetic this whole
phase's evidence rests on. ``extract_frame``/``observe_clip`` mock the
ffmpeg subprocess call and the frame-analysis functions respectively, the
same "don't invoke a real ffmpeg in a unit test" discipline
test_finish_manim.py already established.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import prompt2render.visual_observe as vo
from prompt2render.harness.temporal_ir import SectionTiming, StateTiming


cv2 = pytest.importorskip("cv2")


def _write_frame(path: Path, color: tuple[int, int, int], size: int = 40) -> None:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:, :] = color
    cv2.imwrite(str(path), img)


def test_ink_fraction_pure_black_is_zero(tmp_path):
    frame = tmp_path / "black.png"
    _write_frame(frame, (0, 0, 0))

    assert vo.ink_fraction(frame) == 0.0


def test_ink_fraction_solid_content_is_one(tmp_path):
    frame = tmp_path / "white.png"
    _write_frame(frame, (255, 255, 255))

    assert vo.ink_fraction(frame) == 1.0


def test_ink_fraction_partial_content(tmp_path):
    frame = tmp_path / "half.png"
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    img[:5, :] = (255, 255, 255)
    cv2.imwrite(str(frame), img)

    assert vo.ink_fraction(frame) == pytest.approx(0.5)


def test_ink_fraction_missing_file_returns_none(tmp_path):
    assert vo.ink_fraction(tmp_path / "missing.png") is None


def test_sample_points_uses_settled_window_midpoint():
    timing = SectionTiming(
        index=1,
        stem="01",
        target_duration=10.0,
        total_gap_seconds=0.0,
        states=[
            StateTiming(name="s1", cue=0, run_time=2.0, wait=1.0),
            StateTiming(name="s2", cue=1, run_time=3.0, wait=1.0),
        ],
    )

    points = vo.sample_points(timing, clip_duration=10.0)

    assert points == [
        ("s1", 2.5),   # 2.0 (run_time) + 1.0*0.5 (half of wait)
        ("s2", 6.5),   # elapsed=3.0 -> 3.0+3.0+0.5
    ]


def test_sample_points_skips_degenerate_zero_length_states():
    timing = SectionTiming(
        index=1,
        stem="01",
        target_duration=5.0,
        total_gap_seconds=0.0,
        states=[
            StateTiming(name="zero", cue=0, run_time=0.0, wait=0.0),
            StateTiming(name="real", cue=1, run_time=1.0, wait=1.0),
        ],
    )

    points = vo.sample_points(timing, clip_duration=5.0)

    assert [name for name, _ in points] == ["real"]


def test_sample_points_falls_back_to_even_spacing_without_temporal_ir():
    points = vo.sample_points(None, clip_duration=10.0, fallback_count=3)

    assert [name for name, _ in points] == ["sample_0", "sample_1", "sample_2"]
    timestamps = [t for _, t in points]
    assert timestamps == sorted(timestamps)
    assert all(0 < t < 10.0 for t in timestamps)


def test_sample_points_empty_clip_duration_returns_nothing():
    assert vo.sample_points(None, clip_duration=0.0) == []


def test_extract_frame_success(tmp_path, monkeypatch):
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"fake png")
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr(vo.subprocess, "run", _fake_run)

    out = tmp_path / "frame.png"
    assert vo.extract_frame(tmp_path / "clip.mp4", 3.5, out) is True
    assert out.exists()
    assert "3.500" in calls[0]


def test_extract_frame_ffmpeg_failure_returns_false(tmp_path, monkeypatch):
    import subprocess as sp

    def _raise(cmd, **kwargs):
        raise sp.CalledProcessError(1, cmd)

    monkeypatch.setattr(vo.subprocess, "run", _raise)

    out = tmp_path / "frame.png"
    assert vo.extract_frame(tmp_path / "clip.mp4", 1.0, out) is False


def test_observe_clip_missing_clip_skips(tmp_path):
    record = vo.observe_clip(
        tmp_path / "nope.mp4",
        None,
        scratch_dir=tmp_path / "scratch",
    )

    assert record["status"] == "skip"
    assert record["unit"] == "frames"
    assert record["warnings"] == []


def test_observe_clip_reports_warn_for_low_ink(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0" * 64)

    monkeypatch.setattr(vo.cfg, "duration", lambda path: 4.0)
    monkeypatch.setattr(
        vo,
        "extract_frame",
        lambda clip_path, ts, out_path: out_path.write_bytes(b"x") or True,
    )
    # First sample is "empty" (below threshold), second has real content.
    fractions = iter([0.0001, 0.5])
    monkeypatch.setattr(vo, "ink_fraction", lambda path, **kw: next(fractions))

    record = vo.observe_clip(
        clip,
        None,
        scratch_dir=tmp_path / "scratch",
        fallback_count=2,
    )

    assert record["status"] == "warn"
    assert record["stills"] == 2
    assert len(record["warnings"]) == 1
    assert record["warnings"][0].startswith("WARN [visual_absence]")


def test_observe_clip_all_present_is_pass(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0" * 64)

    monkeypatch.setattr(vo.cfg, "duration", lambda path: 4.0)
    monkeypatch.setattr(
        vo,
        "extract_frame",
        lambda clip_path, ts, out_path: out_path.write_bytes(b"x") or True,
    )
    monkeypatch.setattr(vo, "ink_fraction", lambda path, **kw: 0.5)

    record = vo.observe_clip(
        clip,
        None,
        scratch_dir=tmp_path / "scratch",
        fallback_count=2,
    )

    assert record["status"] == "pass"
    assert record["warnings"] == []


def test_observe_clip_unprobeable_duration_skips(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0" * 64)

    def _raise(path):
        raise RuntimeError("ffprobe failed")

    monkeypatch.setattr(vo.cfg, "duration", _raise)

    record = vo.observe_clip(clip, None, scratch_dir=tmp_path / "scratch")

    assert record["status"] == "skip"
