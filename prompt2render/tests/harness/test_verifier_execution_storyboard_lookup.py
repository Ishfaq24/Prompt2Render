"""Tests for verifier_execution's storyboard-motion lookup (stem-with-index-fallback)
and narration-duration target (must agree with renderer_manim's compiler)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import NarrationEntry, SceneContext
from prompt2render.harness.plugins.verifier_execution import (
    _safe_narration_duration,
    _storyboard_motion_by_state,
)


def test_matches_by_stem():
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 1, "stem": "01", "states": [
        {"name": "intro", "motion": [{"op": "Create", "target": "c"}]},
    ]}]}
    result = _storyboard_motion_by_state(ctx, "01")
    assert result == {"intro": [{"op": "Create", "target": "c"}]}


def test_falls_back_to_index_when_stem_missing():
    # Same regression as renderer_manim._storyboard_states_for: planner_llm's
    # deterministic fallback path historically omitted "stem".
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 1, "states": [
        {"name": "intro", "motion": []},
    ]}]}
    result = _storyboard_motion_by_state(ctx, "01", index=1)
    assert result == {"intro": []}


def test_returns_none_when_truly_absent():
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 2, "stem": "02", "states": []}]}
    assert _storyboard_motion_by_state(ctx, "01", index=1) is None


# ------------------------------------------------------------------ _safe_narration_duration --

def test_safe_narration_duration_uses_true_end_not_sum_when_gaps_exist():
    # Regression: a real e2e run showed this function (Phase 1) returning
    # sum(sentence durations) -- which excludes inter-sentence gaps -- while
    # renderer_manim's compiler (after its own Phase 2 fix) correctly
    # targets the true section span. The mismatch made validate_manim_timing
    # reject every scene whose compiled timing was now actually correct.
    # Same real fixture as test_renderer_manim_compiler.py's regression test.
    sentences = [
        {"start": 0.00, "end": 9.13}, {"start": 9.45, "end": 14.46},
        {"start": 14.78, "end": 24.62}, {"start": 24.94, "end": 31.34},
        {"start": 31.66, "end": 40.77}, {"start": 41.09, "end": 43.97},
        {"start": 44.29, "end": 52.12},
    ]
    ctx = SceneContext()
    ctx.narration = {"01": NarrationEntry(stem="01", sentences=sentences)}
    result = _safe_narration_duration(ctx, "01")
    assert abs(result - 52.12) < 1e-6
