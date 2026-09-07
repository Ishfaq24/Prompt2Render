"""Tests for procedural Audio Foley synthesis."""

from __future__ import annotations

import wave
from pathlib import Path

from prompt2render.audio_foley import (
    render_foley_track,
    make_whoosh,
    make_pop,
    make_chime,
    make_click,
)


def test_individual_foley_cues():
    whoosh = make_whoosh(duration_s=0.1)
    assert len(whoosh) > 0

    pop = make_pop(duration_s=0.05)
    assert len(pop) > 0

    chime = make_chime(duration_s=0.1)
    assert len(chime) > 0

    click = make_click(duration_s=0.03)
    assert len(click) > 0


def test_render_foley_track(tmp_path: Path):
    out_wav = tmp_path / "foley.wav"
    events = [
        (0.2, "Create"),
        (0.5, "Transform"),
        (0.8, "Highlight"),
        (1.1, "Write"),
    ]
    res = render_foley_track(events, total_duration_s=1.5, output_wav=out_wav)
    assert res.is_file()
    assert res.stat().st_size > 0

    with wave.open(str(res), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 48000
        # 1.5s * 48000 frames = 72000 frames
        assert wf.getnframes() == 72000


def test_extract_foley_events_from_code():
    from prompt2render.audio_foley import extract_foley_events_from_code

    code = """
class Scene01(Scene):
    def construct(self):
        dot = Dot()
        self.play(Create(dot))
        self.play(Indicate(dot))
        self.play(FadeIn(Text("Done")))
"""
    events = extract_foley_events_from_code(code, total_duration_s=4.0)
    assert len(events) == 3
    cues = [e[1] for e in events]
    assert "Create" in cues
    assert "Indicate" in cues
    assert "FadeIn" in cues

