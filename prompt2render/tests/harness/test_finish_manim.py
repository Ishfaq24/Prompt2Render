"""Tier 2 Phase 8-9: finish.finish_manim -- a Manim-aware final-assembly
path that reuses finish()'s renderer-agnostic building blocks (_concat,
_check_master_audio, _mux_final, captions.write_srt, _chapters) without
depending on timeline.load()'s stills-specific per-frame clip plan at all.

No real ffmpeg/ffprobe invoked -- cfg.run/need/duration are mocked
directly (finish.py imports `cfg` at module level: `from . import ...,
cfg, ...`, so patching prompt2render.cfg's attributes affects finish.py's
calls too, same shared module object).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import prompt2render.cfg as cfg_module
import prompt2render.finish as finish_module
from prompt2render.project import Script, Section


def _fake_run(cmd, **kwargs):
    """Stand in for a real ffmpeg invocation: create a plausible output
    file at the command's last argument (both _concat and _mux_final put
    their destination path there)."""

    dst = Path(cmd[-1])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"0" * 4096)

    result = MagicMock()
    result.returncode = 0
    return result


@pytest.fixture(autouse=True)
def _mock_ffmpeg_toolchain(monkeypatch):
    monkeypatch.setattr(cfg_module, "need", lambda *binaries: None)
    monkeypatch.setattr(cfg_module, "run", _fake_run)
    monkeypatch.setattr(cfg_module, "duration", lambda path: 12.0)
    monkeypatch.setattr(cfg_module, "say", lambda msg: None)
    monkeypatch.setattr(cfg_module, "warn", lambda msg: None)


def _script(tmp_path) -> Script:
    return Script(
        meta={"title": "T"},
        sections=[
            Section(index=1, title="Intro", narration="Hello."),
            Section(index=2, title="Next", narration="World."),
        ],
    )


def _prep_project(tmp_path):
    """Real alignment/voice artifacts finish_manim's helpers need:
    build/master.m4a (checked directly) and whatever voice.audio_map/
    captions.write_srt need on disk -- kept minimal, matching only what
    the mocked toolchain actually reads."""

    (tmp_path / "build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "build" / "master.m4a").write_bytes(b"0" * 4096)


def _section_clips(tmp_path) -> dict[str, Path]:
    clips = {}
    for stem in ("01", "02"):
        clip_dir = tmp_path / "build" / "manim" / "videos" / f"scene_{stem}" / "1080p30"
        clip_dir.mkdir(parents=True, exist_ok=True)
        clip = clip_dir / f"Scene{stem}.mp4"
        clip.write_bytes(b"0" * 4096)
        clips[stem] = clip
    return clips


def test_missing_clip_for_a_section_exits(tmp_path, monkeypatch):
    _prep_project(tmp_path)
    script = _script(tmp_path)
    clips = _section_clips(tmp_path)
    del clips["02"]  # section 02 has no rendered clip

    with pytest.raises(SystemExit, match="no rendered clip for section 02"):
        finish_module.finish_manim(tmp_path, script, clips)


def test_missing_master_audio_fails_closed(tmp_path):
    # No build/master.m4a written -- _prep_project skipped deliberately.
    (tmp_path / "build").mkdir(parents=True, exist_ok=True)
    script = _script(tmp_path)
    clips = _section_clips(tmp_path)

    with pytest.raises(SystemExit, match="no build/master.m4a"):
        finish_module.finish_manim(tmp_path, script, clips)


def test_stages_clips_and_concats_without_the_stills_per_frame_stage(tmp_path, monkeypatch):
    _prep_project(tmp_path)
    script = _script(tmp_path)
    clips = _section_clips(tmp_path)

    monkeypatch.setattr(
        finish_module.captions,
        "write_srt",
        lambda proj, script, dst: _touch_srt(dst),
    )
    monkeypatch.setattr(
        finish_module.voice,
        "audio_map",
        lambda proj: {
            "sections": {
                "01": {"start": 0.0, "dur": 5.0},
                "02": {"start": 5.0, "dur": 5.0},
            }
        },
    )

    final = finish_module.finish_manim(tmp_path, script, clips)

    assert final == tmp_path / "out" / "final.mp4"
    assert final.exists()
    # Each section's clip was staged into a flat directory before concat --
    # _concat's ffmpeg concat demuxer needs all inputs in one cwd.
    staged = tmp_path / "build" / "manim_finish"
    assert (staged / "01.mp4").exists()
    assert (staged / "02.mp4").exists()


def _touch_srt(dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello.\n", encoding="utf-8")
    return dst
