"""Tests for the Phase 2 motion-vocabulary extension of planner_llm's storyboard schema."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import ScenePlanEntry
from prompt2render.harness.plugins.planner_llm import (
    MOTION_OPS,
    _fallback,
    _normalise_motion,
    _normalise_state,
    _validate_sections,
)


def _entry(index: int = 1) -> ScenePlanEntry:
    return ScenePlanEntry(
        index=index,
        stem=f"{index:02d}",
        title="Title",
        anim="brief",
        narration_text="Some narration.",
    )


# ------------------------------------------------------------------ _normalise_motion --

def test_normalise_motion_keeps_well_formed_ops():
    raw = [{"op": "Create", "target": "circle"}]
    assert _normalise_motion(raw) == [{"op": "Create", "target": "circle"}]


def test_normalise_motion_preserves_unknown_op_for_validation_to_catch():
    raw = [{"op": "Spin", "target": "circle"}]
    result = _normalise_motion(raw)
    assert result == [{"op": "Spin", "target": "circle"}]


def test_normalise_motion_preserves_missing_key_for_validation_to_catch():
    raw = [{"op": "Transform", "target": "circle"}]  # missing "into"
    result = _normalise_motion(raw)
    assert result == [{"op": "Transform", "target": "circle"}]


def test_normalise_motion_non_list_becomes_empty_list():
    assert _normalise_motion("not a list") == []
    assert _normalise_motion(None) == []


def test_normalise_motion_non_dict_item_becomes_empty_dict():
    assert _normalise_motion(["not a dict"]) == [{}]


def test_normalise_state_wires_motion_through():
    state = {"name": "s1", "cue": 0, "visual": "x", "motion": [{"op": "Create", "target": "c"}]}
    result = _normalise_state(state, _entry())
    assert result["motion"] == [{"op": "Create", "target": "c"}]


def test_normalise_state_defaults_missing_motion_to_empty_list():
    state = {"name": "s1", "cue": 0, "visual": "x"}
    result = _normalise_state(state, _entry())
    assert result["motion"] == []


# ------------------------------------------------------------------ _validate_sections --

def _section(states):
    return {"index": 1, "title": "T", "claim": "C", "states": states}


def _state(motion):
    return {"name": "s", "cue": 0, "visual": "v", "values": [], "transition": "t", "motion": motion}


def test_validate_sections_accepts_well_formed_motion():
    states = [_state([{"op": "Create", "target": "circle"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert not errors


def test_validate_sections_rejects_non_list_motion():
    states = [_state([]), {"name": "s2", "cue": 0, "visual": "v", "values": [], "transition": "t", "motion": "nope"}]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("motion must be a list" in e for e in errors)


def test_validate_sections_rejects_unknown_op():
    states = [_state([{"op": "Spin", "target": "circle"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("unknown op 'Spin'" in e for e in errors)


def test_validate_sections_rejects_missing_required_key():
    states = [_state([{"op": "Transform", "target": "circle"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("Transform is missing required key(s) ['into']" in e for e in errors)


def test_validate_sections_rejects_non_dict_motion_op():
    states = [_state(["not-a-dict"]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("invalid motion op" in e for e in errors)


def test_validate_sections_rejects_non_identifier_target():
    states = [_state([{"op": "Create", "target": "circle label"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("must be a valid Python identifier" in e for e in errors)


def test_validate_sections_rejects_keyword_target():
    states = [_state([{"op": "Create", "target": "class"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert any("must be a valid Python identifier" in e for e in errors)


def test_validate_sections_accepts_valid_identifier_target():
    states = [_state([{"op": "Create", "target": "circle_label_1"}]), _state([])]
    errors = _validate_sections([_entry()], [_section(states)])
    assert not errors


def test_fallback_includes_stem_matching_normalise_section_schema():
    # Regression: a live e2e run (all Gemini keys rate-limited, storyboard
    # LLM call failed on every section) produced a storyboard.json whose
    # sections had no "stem" key at all -- because _fallback() is used
    # directly as a complete section dict in three places in run() (never
    # passed through _normalise_section), and _fallback() omitted "stem".
    # Every stem-keyed lookup (renderer_manim._storyboard_states_for,
    # verifier_execution._storyboard_motion_by_state) then failed to find
    # a section that was genuinely present, and generation raised
    # "no storyboard entry found" for every section.
    entry = _entry(index=3)
    section = _fallback(entry)
    assert section["stem"] == entry.stem
    assert section["index"] == entry.index


def test_motion_ops_vocabulary_is_the_expected_fixed_set():
    assert set(MOTION_OPS) == {
        "Create", "Write", "FadeIn", "FadeOut", "Transform", "MoveTo", "Highlight",
    }
    assert MOTION_OPS["Transform"] == frozenset({"target", "into"})
    assert MOTION_OPS["MoveTo"] == frozenset({"target", "anchor"})
