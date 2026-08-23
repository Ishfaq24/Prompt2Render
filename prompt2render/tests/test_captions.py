"""Unit tests for captions.py's card-splitting/timing math -- _cards(),
_constrain(), _ts(), _ass_ts(). Pure functions, no project/audio required.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompt2render import captions, cfg


def _words(text: str, start: float, wps: float = 5.0) -> list[dict]:
    """Evenly-timed words at `wps` words/second, back to back."""
    out, t = [], start
    for w in text.split():
        dur = 1 / wps
        out.append({"w": w, "s": round(t, 3), "e": round(t + dur, 3)})
        t += dur
    return out


# ------------------------------------------------------------------ _ts ---

def test_ts_srt_format():
    assert captions._ts(0.0) == "00:00:00,000"
    assert captions._ts(65.5) == "00:01:05,500"
    assert captions._ts(3661.001) == "01:01:01,001"


def test_ts_clamps_negative_to_zero():
    assert captions._ts(-1.0) == "00:00:00,000"


def test_ass_ts_format():
    assert captions._ass_ts(0.0) == "0:00:00.00"
    assert captions._ass_ts(65.5) == "0:01:05.50"


# --------------------------------------------------------------- _cards ---

def test_cards_single_short_sentence_is_one_card():
    words = _words("a short sentence that fits fine", 0.0)
    cards = captions._cards(words, cfg.CAPTION_LINE, cfg.CAPTION_LINES)
    assert len(cards) == 1
    assert cards[0] == words


def test_cards_empty_words_returns_empty():
    assert captions._cards([], cfg.CAPTION_LINE, cfg.CAPTION_LINES) == []


def test_cards_covers_every_word_exactly_once():
    """Whatever the split, no word may be dropped or duplicated -- this is
    the caption-drift equivalent of align's monotonicity invariant."""
    long_text = " ".join(f"word{i}" for i in range(40))
    words = _words(long_text, 0.0)
    cards = captions._cards(words, cfg.CAPTION_LINE, cfg.CAPTION_LINES)
    flattened = [w for c in cards for w in c]
    assert flattened == words


def test_cards_prefers_the_biggest_gap_as_a_break_point():
    """A long pause is where a speaker actually took a breath -- the split
    should land there instead of the plain fit-boundary, when a real gap
    exists among the last few feasible break points."""
    text = ("the quick brown fox jumps over the lazy dog and then runs away "
            "quickly before anyone can react to what just happened here today")
    words = _words(text, 0.0, wps=8.0)
    # With no gaps at all, this sentence's fit-boundary break naturally lands
    # after word 14 ("before") -- confirmed below. Insert one large pause
    # right after word 11 ("runs"), inside the last-few-candidates window the
    # gap search actually considers, and the break should move there instead.
    baseline = captions._cards(_words(text, 0.0, wps=8.0),
                               cfg.CAPTION_LINE, cfg.CAPTION_LINES)
    assert baseline[0][-1]["w"] == "before"

    for w in words[12:]:
        w["s"] += 2.0
        w["e"] += 2.0
    cards = captions._cards(words, cfg.CAPTION_LINE, cfg.CAPTION_LINES)
    assert len(cards) >= 2
    assert cards[0][-1]["w"] == "runs"


# ----------------------------------------------------------- _constrain ---

def _card(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end}


def test_constrain_extends_a_too_short_card_to_minimum_duration():
    cards = [_card("hi", 0.0, 0.05)]               # far under CAPTION_MIN_S
    out = captions._constrain(cards)
    assert out[0]["end"] - out[0]["start"] >= cfg.CAPTION_MIN_S


def test_constrain_caps_a_too_long_card_at_maximum_duration():
    cards = [_card("x", 0.0, cfg.CAPTION_MAX_S + 10)]
    out = captions._constrain(cards)
    assert out[0]["end"] - out[0]["start"] == cfg.CAPTION_MAX_S


def test_constrain_never_lets_two_cards_touch():
    cards = [_card("a", 0.0, 1.0), _card("b", 1.0, 2.0)]
    out = captions._constrain(cards)
    assert out[1]["start"] - out[0]["end"] >= captions.MIN_GAP - 1e-9


def test_constrain_extending_a_short_card_respects_the_next_cards_start():
    """Extending card 0 to meet CAPTION_MIN_S must never push it into (or
    past) card 1 -- the ceiling is the next card's start minus MIN_GAP."""
    cards = [_card("short", 0.0, 0.1), _card("next", 0.3, 1.0)]
    out = captions._constrain(cards)
    assert out[0]["end"] <= out[1]["start"] - captions.MIN_GAP + 1e-9


def test_cards_for_uses_exact_sample_offsets_to_prevent_drift(monkeypatch):
    """Verify cards_for computes section offsets from exact sample counts, not rounded floats.
    
    Floating point addition of rounded `start` values in audio_map.json accumulates 
    significant drift over a long video (e.g. 13 seconds over an 8-minute video).
    """
    class MockScript:
        class MockSection:
            def __init__(self, stem):
                self.stem = stem
        sections = [MockSection("01"), MockSection("02")]

    def mock_audio_map(proj):
        return {
            "sample_rate": 24000,
            "sections": {
                # A rounded float start time that has lost precision
                "01": {"start": 0.0, "samples": 24000 * 60}, # exactly 60 seconds
                # The float start here is deliberately wrong/rounded to simulate drift
                "02": {"start": 59.991, "samples": 24000 * 60}, 
            }
        }
    
    def mock_align_load(proj, stem):
        return {
            "sentences": [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 1.0,
                    "words": [{"w": "Hello", "s": 0.0, "e": 0.5}, {"w": "world", "s": 0.5, "e": 1.0}]
                }
            ]
        }
        
    monkeypatch.setattr(captions.voice, "audio_map", mock_audio_map)
    monkeypatch.setattr(captions.align, "load", mock_align_load)
    
    cards = captions.cards_for(Path("dummy"), MockScript())
    
    # The first section starts at 0.0
    assert cards[0]["start"] == 0.0
    
    # The second section should start exactly at 60.0 (24000 * 60 / 24000),
    # NOT at the rounded/drifted 59.991 from the audio_map "start" field.
    assert cards[1]["start"] == 60.0
