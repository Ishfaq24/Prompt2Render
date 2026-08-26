"""Tier 2 Phase 5: TemporalIR -- narration-authoritative timing.

Covers round-trip, hash determinism, total_gap_seconds (real gaps,
back-to-back sentences, dur-only legacy data), compute_state_slots (the
relocated _state_cue_timings, now tested at its real home), and
from_semantic_ir (multi-section, missing alignment for one section degrades
only that section).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.semantic_plan import annotate
from prompt2render.harness.temporal_ir import (
    TEMPORAL_SCHEMA_VERSION,
    SectionTiming,
    StateTiming,
    TemporalIR,
    build_section_timing,
    compute_state_slots,
    from_semantic_ir,
    temporal_ir_from_dict,
    total_gap_seconds,
)


# --------------------------------------------------------- total_gap_seconds

def test_total_gap_seconds_sums_real_gaps():
    sentences = [
        {"start": 0.0, "end": 4.0},
        {"start": 4.5, "end": 9.0},
        {"start": 9.5, "end": 12.0},
    ]
    assert total_gap_seconds(sentences) == 1.0


def test_total_gap_seconds_zero_for_back_to_back_sentences():
    sentences = [{"start": 0.0, "end": 4.0}, {"start": 4.0, "end": 8.0}]
    assert total_gap_seconds(sentences) == 0.0


def test_total_gap_seconds_ignores_overlap_as_negative_gap():
    # An overlap (next starts before current ends) floors to 0, not negative.
    sentences = [{"start": 0.0, "end": 4.0}, {"start": 3.0, "end": 8.0}]
    assert total_gap_seconds(sentences) == 0.0


def test_total_gap_seconds_dur_only_legacy_data_yields_zero():
    # No absolute timestamps -- don't guess a gap, matching narration_span's
    # own philosophy for the same situation.
    sentences = [{"dur": 5.0}, {"dur": 5.0}]
    assert total_gap_seconds(sentences) == 0.0


def test_total_gap_seconds_empty_or_single_sentence():
    assert total_gap_seconds([]) == 0.0
    assert total_gap_seconds(None) == 0.0
    assert total_gap_seconds([{"start": 0.0, "end": 4.0}]) == 0.0


# ------------------------------------------------------- compute_state_slots

def test_compute_state_slots_telescopes_to_total_duration():
    sentences = [{"start": 0.0, "end": 4.0}, {"start": 4.5, "end": 9.0}, {"start": 9.5, "end": 12.0}]
    states = [{"cue": 0}, {"cue": 1}, {"cue": 2}]
    slots = compute_state_slots(states, sentences, duration=12.0)
    assert len(slots) == 3
    total = sum(s["run_time"] + s["wait"] for s in slots)
    assert abs(total - 12.0) < 1e-6


def test_compute_state_slots_empty_states_returns_empty():
    assert compute_state_slots([], [], 10.0) == []


def test_compute_state_slots_no_sentence_data_still_positive():
    slots = compute_state_slots([{"cue": 0}], None, duration=5.0)
    assert slots[0]["run_time"] > 0


# ------------------------------------------------------- build_section_timing

def test_build_section_timing_combines_everything():
    sentences = [{"start": 0.0, "end": 4.0}, {"start": 4.5, "end": 9.0}]
    states = [{"name": "a", "cue": 0}, {"name": "b", "cue": 1}]
    st = build_section_timing(1, "01", states, sentences, duration=9.0)
    assert st.index == 1
    assert st.stem == "01"
    assert st.target_duration == 9.0
    assert st.total_gap_seconds == 0.5
    assert [s.name for s in st.states] == ["a", "b"]


# ------------------------------------------------------------ round-trip/hash

def test_round_trip_preserves_every_field():
    ir = TemporalIR(
        schema_version=TEMPORAL_SCHEMA_VERSION,
        source_semantic_hash="deadbeef",
        sections=[
            SectionTiming(
                index=1,
                stem="01",
                target_duration=9.0,
                total_gap_seconds=0.5,
                states=[StateTiming(name="a", cue=0, run_time=3.0, wait=0.5)],
            )
        ],
    )
    ir.temporal_hash = ir.compute_hash()
    restored = temporal_ir_from_dict(ir.to_dict())
    assert restored == ir
    assert restored.compute_hash() == ir.temporal_hash


def test_hash_changes_when_content_changes():
    base_kwargs = dict(
        schema_version=TEMPORAL_SCHEMA_VERSION,
        source_semantic_hash="deadbeef",
        sections=[
            SectionTiming(
                index=1, stem="01", target_duration=9.0, total_gap_seconds=0.5, states=[]
            )
        ],
    )
    a = TemporalIR(**base_kwargs)
    b = TemporalIR(**{**base_kwargs, "source_semantic_hash": "other"})
    assert a.compute_hash() != b.compute_hash()


# --------------------------------------------------------------- from_semantic_ir

def _semantic_ir_fixture():
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
                ],
            },
            {
                "index": 2,
                "stem": "02",
                "title": "Next",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a square.",
                        "transition": "progressive reveal",
                        "values": [],
                        "motion": [{"op": "Create", "target": "square"}],
                    },
                ],
            },
        ],
    }
    animation_ir = from_storyboard_plan(plan)
    raw = {
        "sections": [
            {
                "index": 1,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [{"phase": "ACTION", "op": "Create", "target": "circle"}],
                    }
                ],
            },
            {
                "index": 2,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [{"phase": "ACTION", "op": "Create", "target": "square"}],
                    }
                ],
            },
        ]
    }
    return annotate(animation_ir, raw)


def test_from_semantic_ir_builds_one_section_timing_per_section():
    semantic_ir = _semantic_ir_fixture()
    sentences_by_stem = {
        "01": [{"start": 0.0, "end": 5.0}],
        "02": [{"start": 0.0, "end": 3.0}],
    }
    ir = from_semantic_ir(semantic_ir, sentences_by_stem)

    assert ir.schema_version == TEMPORAL_SCHEMA_VERSION
    assert ir.source_semantic_hash == semantic_ir.semantic_hash
    assert ir.temporal_hash != ""
    assert len(ir.sections) == 2
    assert ir.sections[0].target_duration == 5.0
    assert ir.sections[1].target_duration == 3.0


def test_from_semantic_ir_missing_alignment_degrades_only_that_section():
    semantic_ir = _semantic_ir_fixture()
    sentences_by_stem = {"01": [{"start": 0.0, "end": 5.0}]}  # "02" absent entirely

    ir = from_semantic_ir(semantic_ir, sentences_by_stem)

    assert ir.sections[0].target_duration == 5.0
    assert ir.sections[1].target_duration == 0.0
    assert ir.sections[1].total_gap_seconds == 0.0
