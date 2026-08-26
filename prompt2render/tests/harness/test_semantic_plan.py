"""Phase 3: SemanticAnimationIR -- the CONTEXT/ANTICIPATION/ACTION/
CONSEQUENCE/HOLD phase model built on top of AnimationIR.

Covers round-trip, hash determinism, annotate()'s validation rules (missing
ACTION beat, hold-state exemption, unknown phase name, a beat referencing an
identifier absent from the source AnimationIR, incomplete section/state
coverage), and the deterministic default_semantic_plan() fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.semantic_plan import (
    SEMANTIC_SCHEMA_VERSION,
    SemanticPlanValidationError,
    annotate,
    default_semantic_plan,
    semantic_ir_from_dict,
)


def _animation_ir(**overrides):
    plan = {
        "version": "2.0",
        "prompt_sha256": "deadbeef",
        "sections": [
            {
                "index": 1,
                "stem": "01",
                "title": "Intro",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a circle.",
                        "transition": "progressive reveal",
                        "values": [],
                        "motion": [{"op": "Create", "target": "circle"}],
                    },
                    {
                        "name": "explain",
                        "cue": 1,
                        "visual": "Turn it into a square.",
                        "transition": "morph",
                        "values": [],
                        "motion": [
                            {"op": "Transform", "target": "circle", "into": "square"}
                        ],
                    },
                ],
            }
        ],
    }
    plan.update(overrides)
    return from_storyboard_plan(plan)


def _valid_raw():
    return {
        "sections": [
            {
                "index": 1,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [
                            {"phase": "ACTION", "op": "Create", "target": "circle"},
                        ],
                    },
                    {
                        "name": "explain",
                        "hold": False,
                        "beats": [
                            {"phase": "ANTICIPATION", "op": "Circumscribe", "target": "circle"},
                            {
                                "phase": "ACTION",
                                "op": "Transform",
                                "target": "circle",
                                "into": "square",
                            },
                            {"phase": "CONSEQUENCE", "op": "Highlight", "target": "square"},
                        ],
                    },
                ],
            }
        ]
    }


# ------------------------------------------------------------- success -----

def test_valid_plan_annotates_cleanly():
    ir = _animation_ir()
    plan = annotate(ir, _valid_raw())

    assert plan.schema_version == SEMANTIC_SCHEMA_VERSION
    assert plan.source_ir_hash == ir.ir_hash
    assert plan.semantic_hash != ""
    assert len(plan.sections[0].states) == 2
    assert plan.sections[0].states[1].beats[1].phase == "ACTION"


def test_round_trip_preserves_every_field():
    ir = _animation_ir()
    plan = annotate(ir, _valid_raw())
    restored = semantic_ir_from_dict(plan.to_dict())
    assert restored == plan


def test_hash_changes_when_content_changes():
    ir = _animation_ir()
    plan_a = annotate(ir, _valid_raw())
    raw_b = _valid_raw()
    # "explain" already has a separate ACTION beat, so retagging its
    # ANTICIPATION beat doesn't trip the ACTION-beat requirement.
    raw_b["sections"][0]["states"][1]["beats"][0]["phase"] = "CONTEXT"
    plan_b = annotate(ir, raw_b)
    assert plan_a.semantic_hash != plan_b.semantic_hash


# ---------------------------------------------------------------- hold -----

def test_hold_state_is_exempt_from_action_requirement():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"][1] = {
        "name": "explain",
        "hold": True,
        "beats": [],
    }
    plan = annotate(ir, raw)
    assert plan.sections[0].states[1].hold is True
    assert plan.sections[0].states[1].beats == []


def test_non_hold_state_without_action_beat_raises():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"][1]["beats"] = [
        {"phase": "CONTEXT", "op": "Create", "target": "circle"},
    ]
    with pytest.raises(SemanticPlanValidationError, match=r"needs at least one ACTION beat"):
        annotate(ir, raw)


# --------------------------------------------------------- bad phase/op ----

def test_unknown_phase_raises():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"][0]["beats"][0]["phase"] = "CLIMAX"
    with pytest.raises(SemanticPlanValidationError, match=r"unknown phase 'CLIMAX'"):
        annotate(ir, raw)


def test_invalid_op_raises_via_existing_validator():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"][0]["beats"][0] = {
        "phase": "CONTEXT",
        "op": "Spin",
        "target": "circle",
    }
    with pytest.raises(SemanticPlanValidationError, match=r"unknown op 'Spin'"):
        annotate(ir, raw)


def test_beat_referencing_unknown_identifier_raises():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"][0]["beats"][0] = {
        "phase": "CONTEXT",
        "op": "Create",
        "target": "triangle",  # never appears anywhere in the source AnimationIR
    }
    with pytest.raises(SemanticPlanValidationError, match=r"not present in the source"):
        annotate(ir, raw)


# --------------------------------------------------------- completeness ----

def test_missing_section_raises():
    ir = _animation_ir()
    with pytest.raises(SemanticPlanValidationError, match=r"missing from semantic plan"):
        annotate(ir, {"sections": []})


def test_missing_state_raises():
    ir = _animation_ir()
    raw = _valid_raw()
    raw["sections"][0]["states"] = [raw["sections"][0]["states"][0]]
    with pytest.raises(SemanticPlanValidationError, match=r"'explain': missing from semantic plan"):
        annotate(ir, raw)


# -------------------------------------------------------- default fallback -

def test_default_semantic_plan_is_valid_and_tags_everything_action():
    ir = _animation_ir()
    plan = default_semantic_plan(ir)

    for section in plan.sections:
        for state in section.states:
            assert all(beat.phase == "ACTION" for beat in state.beats)


def test_default_semantic_plan_holds_states_with_no_ops():
    plan_dict = {
        "version": "2.0",
        "prompt_sha256": "x",
        "sections": [
            {
                "index": 1,
                "stem": "01",
                "title": "T",
                "states": [
                    {
                        "name": "pause",
                        "cue": 0,
                        "visual": "Nothing new.",
                        "transition": "hold",
                        "values": [],
                        "motion": [],
                    }
                ],
            }
        ],
    }
    ir = from_storyboard_plan(plan_dict)
    plan = default_semantic_plan(ir)
    assert plan.sections[0].states[0].hold is True
