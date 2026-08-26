"""Unit tests for align.py's reconciliation math -- reconcile(), _interpolate(),
snap(), clamp_to_prior(). Pure functions, no ffmpeg/whisper/network required.

This is exactly the math debugged by hand while fixing the VAD-slowdown and
per-section cache bugs this session -- and none of those fixes had a test
guarding against regression until now.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render import align, textseg, voice


def _sentences(text: str) -> list[textseg.Sentence]:
    return textseg.sentences(text)


def _asr_token(word: str, s: float, e: float) -> dict:
    return {"n": textseg.norm_tokens(word)[0] if textseg.norm_tokens(word) else word,
            "s": s, "e": e}


# ------------------------------------------------------------- reconcile ---

def test_reconcile_exact_match_high_confidence():
    """Every ASR token matches the script verbatim -> confidence 1.0, source
    would be "asr" upstream (align() decides that; reconcile() just reports
    conf)."""
    sents = _sentences("The quick brown fox jumps.")
    words = [w.raw for s in sents for w in s.words]
    dur = 3.0
    step = dur / max(len(words), 1)
    asr = [_asr_token(w, i * step, (i + 1) * step) for i, w in enumerate(words)]

    aligned, conf = align.reconcile(sents, asr, dur)
    assert conf == 1.0
    assert len(aligned) == len(sents)
    _assert_monotonic(aligned)


def test_reconcile_no_asr_falls_back_to_spread():
    """No ASR tokens at all -> proportional spread, confidence 0.0 (align()'s
    own _source() then labels this "proportional", the honest worst case)."""
    sents = _sentences("First sentence here. Second sentence follows.")
    aligned, conf = align.reconcile(sents, [], 10.0)
    assert conf == 0.0
    assert len(aligned) == len(sents)
    assert aligned[0]["start"] == 0.0
    _assert_monotonic(aligned)


def test_reconcile_below_floor_falls_back_to_spread():
    """ASR tokens that don't match the script at all (garbage transcription)
    must not be trusted just because they exist -- reconcile() should notice
    the match rate is below CONF_FLOOR and fall back rather than anchor on
    noise."""
    sents = _sentences("The algorithm partitions the array in place.")
    garbage = [_asr_token(w, i * 0.5, i * 0.5 + 0.4)
              for i, w in enumerate(["completely", "unrelated", "hallucinated", "text"])]
    aligned, conf = align.reconcile(sents, garbage, 5.0)
    assert conf < align.CONF_FLOOR
    _assert_monotonic(aligned)


def _assert_monotonic(sents: list[dict]) -> None:
    """The invariant the whole pipeline is built on: segment[i].start <=
    segment[i].end, and segment[i].end <= segment[i+1].start."""
    for s in sents:
        assert s["start"] <= s["end"], s
        for w in s["words"]:
            assert w["s"] <= w["e"], w
    for a, b in zip(sents, sents[1:]):
        assert a["end"] <= b["start"] + 1e-9, (a, b)


# ---------------------------------------------------------- _interpolate ---

def test_interpolate_no_anchors_spreads_by_syllables():
    gt = ["a", "elephant", "go"]                 # short, long, short
    times = align._interpolate(gt, {}, dur=10.0)
    assert len(times) == 3
    assert times[0] < times[1] < times[2] or times[0] <= times[1] <= times[2]
    assert all(0.0 <= t <= 10.0 for t in times)


def test_interpolate_strictly_monotonic_even_with_duplicate_anchors():
    """Two anchors landing at (nearly) the same instant must still produce
    strictly increasing times -- this is what MIN_WORD's floor exists for."""
    gt = ["one", "two", "three", "four"]
    anchors = {0: 1.0, 1: 1.0, 3: 1.0}            # pathological: no progress
    times = align._interpolate(gt, anchors, dur=5.0)
    for a, b in zip(times, times[1:]):
        assert b > a, times


def test_interpolate_respects_known_anchor_positions():
    gt = ["a", "b", "c", "d", "e"]
    anchors = {0: 0.0, 4: 8.0}
    times = align._interpolate(gt, anchors, dur=10.0)
    assert times[0] == 0.0
    assert times[4] == 8.0
    for a, b in zip(times, times[1:]):
        assert b >= a


# --------------------------------------------------------------- snap() ---

def test_snap_pulls_boundary_onto_nearby_silence():
    sents = [{"start": 1.10, "end": 2.0, "words": [{"w": "x", "s": 1.10, "e": 1.5}]}]
    gaps = [(0.5, 1.00)]                          # silence ends at 1.00s
    moved = align.snap(sents, gaps)
    assert moved == 1
    assert sents[0]["start"] == 1.00
    assert sents[0]["words"][0]["s"] == 1.00


def test_snap_leaves_boundary_alone_when_no_silence_nearby():
    sents = [{"start": 5.0, "end": 6.0, "words": []}]
    gaps = [(0.5, 1.00)]                          # far outside SNAP_WINDOW
    moved = align.snap(sents, gaps)
    assert moved == 0
    assert sents[0]["start"] == 5.0


def test_snap_never_lets_end_pass_next_start():
    sents = [
        {"start": 0.0, "end": 2.05, "words": []},
        {"start": 2.0, "end": 4.0, "words": []},
    ]
    align.snap(sents, [])
    assert sents[0]["end"] <= sents[1]["start"]


# ------------------------------------------------------- clamp_to_prior ---

def test_clamp_to_prior_pins_exact_synthesis_boundaries():
    sents = [{"start": 0.9, "end": 3.3,
             "words": [{"w": "hi", "s": 0.9, "e": 1.2}, {"w": "there", "s": 1.3, "e": 3.3}]}]
    prior = [voice.Cue(i=0, text="hi there", start=1.0, end=3.0)]
    out = align.clamp_to_prior(sents, prior)
    assert out[0]["start"] == 1.0
    assert out[0]["end"] == 3.0
    # word times are clamped inside the exact boundary too
    assert out[0]["words"][0]["s"] == 1.0
    assert out[0]["words"][-1]["e"] == 3.0
    for w in out[0]["words"]:
        assert 1.0 <= w["s"] <= w["e"] <= 3.0


def test_clamp_to_prior_noop_on_length_mismatch():
    """A prior list that doesn't match section count is a signal something
    upstream is inconsistent -- clamp_to_prior must not guess, just pass
    through unchanged."""
    sents = [{"start": 0.0, "end": 1.0, "words": []},
             {"start": 1.0, "end": 2.0, "words": []}]
    prior = [voice.Cue(i=0, text="only one", start=0.5, end=1.5)]
    out = align.clamp_to_prior(sents, prior)
    assert out == sents
