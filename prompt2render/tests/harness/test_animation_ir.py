"""AnimationIR -- typed, versioned, hashed IR built from storyboard_plan.

Phase 1 of the Tier 1 migration (docs/ARCHITECTURE_AUDIT.md SS17). These tests
exercise the pure conversion/serialization functions in
``harness.animation_ir`` against both hand-built fixtures (edge cases:
MIN/MAX state counts, empty motion, multi-op states, invalid ops) and, where
available, real ``storyboard.json`` files already recorded on disk under
``projects/*/build/harness/`` -- proving the converter handles actual
production output, not just a fixture shaped the way I expect it to be.
"""
from __future__ import annotations

import copy
import glob
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.animation_ir import (
    IR_SCHEMA_VERSION,
    AnimationIR,
    MotionOpIR,
    SectionIR,
    StateIR,
    from_storyboard_plan,
    ir_from_dict,
)


def _storyboard_plan(**overrides) -> dict:
    base = {
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
                        "visual": "Highlight it.",
                        "transition": "preserve established state",
                        "values": [1, 2],
                        "motion": [{"op": "Highlight", "target": "circle"}],
                    },
                ],
            }
        ],
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------- round-trip --

def test_round_trip_preserves_every_field():
    ir = from_storyboard_plan(_storyboard_plan())
    restored = ir_from_dict(ir.to_dict())
    assert restored == ir


def test_round_trip_preserves_empty_motion_and_values():
    plan = _storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = []
    plan["sections"][0]["states"][0]["values"] = []
    ir = from_storyboard_plan(plan)
    restored = ir_from_dict(ir.to_dict())
    assert restored.sections[0].states[0].ops == []
    assert restored.sections[0].states[0].values == []
    assert restored == ir


def test_state_missing_motion_key_defaults_to_empty_ops():
    # Deterministic-fallback sections have historically omitted "motion"
    # entirely rather than including it as an empty list.
    plan = _storyboard_plan()
    del plan["sections"][0]["states"][0]["motion"]
    ir = from_storyboard_plan(plan)
    assert ir.sections[0].states[0].ops == []


def test_section_missing_stem_defaults_to_empty_string():
    plan = _storyboard_plan()
    del plan["sections"][0]["stem"]
    ir = from_storyboard_plan(plan)
    assert ir.sections[0].stem == ""
    assert ir.sections[0].index == 1


# ------------------------------------------------------------- hashing -----

def test_hash_is_deterministic_across_independent_builds():
    plan = _storyboard_plan()
    ir_a = from_storyboard_plan(copy.deepcopy(plan))
    ir_b = from_storyboard_plan(copy.deepcopy(plan))
    assert ir_a.ir_hash == ir_b.ir_hash
    assert ir_a.ir_hash != ""


def test_hash_changes_when_content_changes():
    plan = _storyboard_plan()
    ir_a = from_storyboard_plan(copy.deepcopy(plan))
    plan["sections"][0]["states"][0]["visual"] = "Show a square instead."
    ir_b = from_storyboard_plan(plan)
    assert ir_a.ir_hash != ir_b.ir_hash


def test_hash_is_stable_under_to_dict_from_dict_round_trip():
    ir = from_storyboard_plan(_storyboard_plan())
    restored = ir_from_dict(ir.to_dict())
    assert restored.compute_hash() == ir.ir_hash


# ---------------------------------------------------------- schema/version --

def test_schema_version_is_stamped():
    ir = from_storyboard_plan(_storyboard_plan())
    assert ir.schema_version == IR_SCHEMA_VERSION


def test_provenance_fields_carry_over_from_storyboard():
    ir = from_storyboard_plan(_storyboard_plan())
    assert ir.source_storyboard_version == "2.0"
    assert ir.source_hash == "deadbeef"


# --------------------------------------------------- MIN/MAX state bounds --

def test_two_state_section_converts_cleanly():
    plan = _storyboard_plan()
    assert len(plan["sections"][0]["states"]) == 2
    ir = from_storyboard_plan(plan)
    assert len(ir.sections[0].states) == 2


def test_six_state_section_converts_cleanly():
    plan = _storyboard_plan()
    template = plan["sections"][0]["states"][1]
    plan["sections"][0]["states"] = [
        {**copy.deepcopy(template), "name": f"state_{i}", "cue": i}
        for i in range(6)
    ]
    ir = from_storyboard_plan(plan)
    assert len(ir.sections[0].states) == 6


def test_multi_op_state_preserves_op_order():
    plan = _storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [
        {"op": "Create", "target": "a"},
        {"op": "Create", "target": "b"},
        {"op": "Transform", "target": "a", "into": "b"},
    ]
    ir = from_storyboard_plan(plan)
    ops = ir.sections[0].states[0].ops
    assert [op.op for op in ops] == ["Create", "Create", "Transform"]
    assert ops[2].params == {"target": "a", "into": "b"}


# ----------------------------------------------------------- validation ----

def test_unknown_op_raises_with_section_and_state_context():
    plan = _storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [{"op": "Spin", "target": "x"}]
    with pytest.raises(ValueError, match=r"Section 1, state 0:.*unknown op 'Spin'"):
        from_storyboard_plan(plan)


def test_missing_required_param_raises():
    plan = _storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [{"op": "Transform", "target": "x"}]
    with pytest.raises(ValueError, match=r"missing required key"):
        from_storyboard_plan(plan)


def test_non_identifier_target_raises():
    plan = _storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [
        {"op": "Create", "target": "not a valid identifier"}
    ]
    with pytest.raises(ValueError, match=r"must be a valid Python identifier"):
        from_storyboard_plan(plan)


def test_non_list_sections_raises():
    with pytest.raises(ValueError, match=r"sections must be a list"):
        from_storyboard_plan({"sections": "nope"})


def test_non_list_states_raises_with_section_context():
    plan = _storyboard_plan()
    plan["sections"][0]["states"] = "nope"
    with pytest.raises(ValueError, match=r"Section 1: states must be a list"):
        from_storyboard_plan(plan)


# ------------------------------------------------ smoke test: real output --

def test_converts_every_recorded_storyboard_json_on_disk():
    repo_root = Path(__file__).resolve().parents[3]
    candidates = glob.glob(
        str(repo_root / "projects" / "*" / "build" / "harness" / "storyboard.json")
    )

    if not candidates:
        pytest.skip("no recorded storyboard.json found under projects/*/build/harness/")

    for candidate in candidates:
        plan = json.loads(Path(candidate).read_text(encoding="utf-8"))
        ir = from_storyboard_plan(plan)
        assert ir.ir_hash != ""
        assert len(ir.sections) == len(plan.get("sections", []))
