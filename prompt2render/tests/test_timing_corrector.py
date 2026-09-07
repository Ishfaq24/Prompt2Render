"""Tests for the deterministic Manim timing corrector."""
from __future__ import annotations

from prompt2render import timing_corrector


def test_timing_corrector_caps_excessive_waits():
    code = """
from manim import *

class Scene01(Scene):
    def construct(self):
        # cue: 0
        self.play(Create(Square()))
        self.wait(8.5)
        # cue: 1
        self.play(FadeIn(Circle()))
        self.wait(0.5)
"""
    timeline = [
        {"start": 0.0, "end": 3.0, "text": "First sentence."},
        {"start": 3.0, "end": 6.0, "text": "Second sentence."},
    ]
    corrected = timing_corrector.correct_manim_timing(code, timeline, total_duration=6.0)
    assert "self.wait(8.5)" not in corrected
    assert "self.wait(2.0)" in corrected
    assert "self.wait(0.5)" in corrected


def test_timing_corrector_handles_empty_or_zero_duration():
    assert timing_corrector.correct_manim_timing("", [], 0.0) == ""
    assert timing_corrector.correct_manim_timing("self.wait(1.0)", [], 0.0) == "self.wait(1.0)"
