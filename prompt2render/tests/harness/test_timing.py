"""Tests for the shared narration-timing definitions.

Regression context: three call sites independently computed "how long is
this section?" and disagreed. Two summed per-sentence durations (which drops
every inter-sentence silence) while one used the last sentence's end. Because
renderer_manim's prompt asserts "the total animation duration MUST equal
{duration}", the sum form was instructing every generated Manim scene to
finish early by exactly the accumulated silence -- measured at 13.50s across
342.08s (3.9%) on a real 6-section project.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.timing import (
    narration_span,
    narration_speech_total,
    sentence_duration,
)


# Real alignment data from `History and Definition of Pi` section 01:
# sum(dur) = 60.95, true end = 64.21 -- a 3.26s shortfall.
_REAL_SECTION = [
    {"start": 0.00, "end": 9.13},
    {"start": 9.45, "end": 14.46},
    {"start": 14.78, "end": 24.62},
    {"start": 24.94, "end": 31.34},
    {"start": 31.66, "end": 40.77},
    {"start": 41.09, "end": 43.97},
    {"start": 44.29, "end": 52.12},
]


# ------------------------------------------------------------ sentence_duration --

def test_sentence_duration_prefers_explicit_dur():
    assert sentence_duration({"dur": 2.5}) == 2.5


def test_sentence_duration_falls_back_to_end_minus_start():
    assert sentence_duration({"start": 1.0, "end": 3.5}) == 2.5


def test_sentence_duration_rejects_unusable_input():
    assert sentence_duration("not a dict") is None
    assert sentence_duration({}) == 0.0          # start/end both default to 0
    assert sentence_duration({"dur": "abc"}) is None
    assert sentence_duration({"dur": float("nan")}) is None
    assert sentence_duration({"dur": -1.0}) is None


# ---------------------------------------------------------------- narration_span --

def test_span_includes_inter_sentence_silence():
    span = narration_span(_REAL_SECTION)
    speech = narration_speech_total(_REAL_SECTION)

    assert abs(span - 52.12) < 1e-6
    # The gap is the whole point of this module existing.
    assert span > speech
    assert abs((span - speech) - 1.92) < 0.01


def test_span_and_speech_total_differ_by_exactly_the_gaps():
    gaps = sum(
        b["start"] - a["end"]
        for a, b in zip(_REAL_SECTION, _REAL_SECTION[1:])
    )
    span = narration_span(_REAL_SECTION)
    speech = narration_speech_total(_REAL_SECTION)
    assert abs((span - speech) - gaps) < 1e-6


def test_span_falls_back_to_sum_for_legacy_dur_only_data():
    # The historical align format carried no absolute timestamps. A sum is
    # then the best available estimate -- and verifier_temporal's existing
    # test fixture relies on exactly this path.
    legacy = [{"dur": 5.0}, {"dur": 5.0}]
    assert narration_span(legacy) == 10.0


def test_span_is_robust_to_a_single_out_of_order_sentence():
    # Alignment is normally monotonic, but one out-of-order entry must not
    # silently shorten the section.
    jumbled = [
        {"start": 0.0, "end": 10.0},
        {"start": 10.5, "end": 20.0},
        {"start": 5.0, "end": 6.0},
    ]
    assert narration_span(jumbled) == 20.0


def test_span_of_empty_is_zero():
    assert narration_span([]) == 0.0
    assert narration_speech_total([]) == 0.0


def test_span_ignores_non_dict_entries():
    assert narration_span([{"start": 0.0, "end": 4.0}, "junk", None]) == 4.0


# ------------------------------------------------------- cross-call-site agreement --

def test_all_three_call_sites_agree_on_span():
    """The regression this module exists to prevent: renderer_manim,
    verifier_temporal and verifier_execution must return the same number."""
    from prompt2render.harness.context import NarrationEntry, SceneContext
    from prompt2render.harness.plugins.verifier_execution import (
        _safe_narration_duration,
    )

    ctx = SceneContext()
    ctx.narration = {"01": NarrationEntry(stem="01", sentences=_REAL_SECTION)}

    expected = narration_span(_REAL_SECTION)

    assert abs(_safe_narration_duration(ctx, "01") - expected) < 1e-6
    assert abs(expected - 52.12) < 1e-6
