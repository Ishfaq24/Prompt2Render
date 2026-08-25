"""Tier 2 Phase 6: construction DSL -- validate_and_parse + compile_construction.

Covers every object kind's required/optional props, Repeat unrolling
(count, generated ids, auto-VGroup), each PositionSpec kind, rejection
cases, and a round-trip-style test compiling a plan shaped like the real
generated scene shown mid-session (title + caption + a 4-element repeated
array + an arrow).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.construction_ir import (
    CONSTRUCTION_SCHEMA_VERSION,
    ConstructionValidationError,
    compile_construction,
    validate_and_parse,
)


def _assert_valid_python(code: str) -> None:
    ast.parse("class X:\n" + "\n".join("    " + line for line in code.splitlines()))


# ---------------------------------------------------------------- object kinds

def test_text_requires_content():
    plan = validate_and_parse({"nodes": [{"id": "t", "kind": "Text", "props": {"content": "hi"}}]})
    assert plan.nodes[0].props["content"] == "hi"


def test_text_missing_content_raises():
    with pytest.raises(ConstructionValidationError, match=r"missing required key"):
        validate_and_parse({"nodes": [{"id": "t", "kind": "Text", "props": {}}]})


def test_rectangle_requires_width_and_height():
    plan = validate_and_parse(
        {"nodes": [{"id": "r", "kind": "Rectangle", "props": {"width": 2, "height": 1}}]}
    )
    assert plan.nodes[0].props == {"width": 2, "height": 1}


def test_circle_and_square_take_no_required_props():
    plan = validate_and_parse(
        {
            "nodes": [
                {"id": "c", "kind": "Circle", "props": {"radius": 1.0}},
                {"id": "s", "kind": "Square", "props": {}},
            ]
        }
    )
    assert len(plan.nodes) == 2


def test_arrow_requires_start_and_end_ref():
    plan = validate_and_parse(
        {
            "nodes": [
                {"id": "a", "kind": "Circle", "props": {}},
                {"id": "b", "kind": "Circle", "props": {}},
                {"id": "arr", "kind": "Arrow", "refs": {"start_ref": "a", "end_ref": "b"}},
            ]
        }
    )
    assert plan.nodes[2].refs == {"start_ref": "a", "end_ref": "b"}


def test_arrow_missing_ref_raises():
    with pytest.raises(ConstructionValidationError, match=r"missing required key"):
        validate_and_parse(
            {
                "nodes": [
                    {"id": "a", "kind": "Circle", "props": {}},
                    {"id": "arr", "kind": "Arrow", "refs": {"start_ref": "a"}},
                ]
            }
        )


def test_arrow_ref_to_undefined_id_raises():
    with pytest.raises(ConstructionValidationError, match=r"undefined id"):
        validate_and_parse(
            {
                "nodes": [
                    {"id": "a", "kind": "Circle", "props": {}},
                    {
                        "id": "arr",
                        "kind": "Arrow",
                        "refs": {"start_ref": "a", "end_ref": "ghost"},
                    },
                ]
            }
        )


def test_unknown_kind_raises():
    with pytest.raises(ConstructionValidationError, match=r"unknown kind"):
        validate_and_parse({"nodes": [{"id": "x", "kind": "Nonagon", "props": {}}]})


def test_unrecognized_prop_key_raises():
    with pytest.raises(ConstructionValidationError, match=r"unrecognized prop key"):
        validate_and_parse(
            {"nodes": [{"id": "c", "kind": "Circle", "props": {"opacity": 0.5}}]}
        )


def test_unknown_color_raises():
    with pytest.raises(ConstructionValidationError, match=r"unknown color"):
        validate_and_parse(
            {"nodes": [{"id": "c", "kind": "Circle", "props": {"color": "TURQUOISE"}}]}
        )


def test_wrong_prop_type_raises():
    with pytest.raises(ConstructionValidationError, match=r"must be of type"):
        validate_and_parse(
            {"nodes": [{"id": "c", "kind": "Circle", "props": {"radius": "big"}}]}
        )


def test_non_identifier_id_raises():
    with pytest.raises(ConstructionValidationError, match=r"valid Python identifier"):
        validate_and_parse({"nodes": [{"id": "not valid", "kind": "Circle", "props": {}}]})


def test_duplicate_id_raises():
    with pytest.raises(ConstructionValidationError, match=r"already defined"):
        validate_and_parse(
            {
                "nodes": [
                    {"id": "c", "kind": "Circle", "props": {}},
                    {"id": "c", "kind": "Square", "props": {}},
                ]
            }
        )


# ------------------------------------------------------------------- VGroup

def test_vgroup_requires_nonempty_children():
    with pytest.raises(ConstructionValidationError, match=r"non-empty list"):
        validate_and_parse({"nodes": [{"id": "g", "kind": "VGroup", "children": []}]})


def test_vgroup_forward_reference_raises():
    with pytest.raises(ConstructionValidationError, match=r"undefined id"):
        validate_and_parse(
            {"nodes": [{"id": "g", "kind": "VGroup", "children": ["not_yet_defined"]}]}
        )


def test_vgroup_compiles_with_arrange():
    plan = validate_and_parse(
        {
            "nodes": [
                {"id": "a", "kind": "Circle", "props": {}},
                {"id": "b", "kind": "Square", "props": {}},
                {
                    "id": "g",
                    "kind": "VGroup",
                    "children": ["a", "b"],
                    "arrange_direction": "DOWN",
                    "arrange_buff": 0.2,
                },
            ]
        }
    )
    code = compile_construction(plan)
    assert "self.g = VGroup(self.a, self.b).arrange(DOWN, buff=0.2)" in code
    _assert_valid_python(code)


# --------------------------------------------------------------- PositionSpec

def test_to_edge_position():
    plan = validate_and_parse(
        {
            "nodes": [
                {
                    "id": "t",
                    "kind": "Circle",
                    "props": {},
                    "position": {"kind": "to_edge", "direction": "UP", "buff": 0.1},
                }
            ]
        }
    )
    code = compile_construction(plan)
    assert ".to_edge(UP, buff=0.1)" in code


def test_next_to_position_requires_known_ref():
    with pytest.raises(ConstructionValidationError, match=r"undefined id"):
        validate_and_parse(
            {
                "nodes": [
                    {
                        "id": "t",
                        "kind": "Circle",
                        "props": {},
                        "position": {"kind": "next_to", "direction": "RIGHT", "ref": "ghost"},
                    }
                ]
            }
        )


def test_next_to_position_compiles():
    plan = validate_and_parse(
        {
            "nodes": [
                {"id": "a", "kind": "Circle", "props": {}},
                {
                    "id": "b",
                    "kind": "Square",
                    "props": {},
                    "position": {"kind": "next_to", "direction": "RIGHT", "ref": "a", "buff": 0.3},
                },
            ]
        }
    )
    code = compile_construction(plan)
    assert "self.b.animate" not in code
    assert ".next_to(self.a, RIGHT, buff=0.3)" in code


def test_band_positions_match_hardcoded_conventions():
    plan = validate_and_parse(
        {
            "nodes": [
                {"id": "t", "kind": "Text", "props": {"content": "x"}, "position": {"kind": "band", "band": "TITLE"}},
                {"id": "c", "kind": "Text", "props": {"content": "y"}, "position": {"kind": "band", "band": "CAPTION"}},
                {"id": "z", "kind": "Circle", "props": {}, "position": {"kind": "band", "band": "CENTER"}},
            ]
        }
    )
    code = compile_construction(plan)
    assert ".to_edge(UP, buff=0.35)" in code
    assert ".move_to(DOWN * 3.15)" in code
    assert ".move_to(ORIGIN)" in code


def test_unknown_band_raises():
    with pytest.raises(ConstructionValidationError, match=r"band must be one of"):
        validate_and_parse(
            {"nodes": [{"id": "t", "kind": "Circle", "props": {}, "position": {"kind": "band", "band": "SIDEBAR"}}]}
        )


# ---------------------------------------------------------------------- Repeat

def test_repeat_unrolls_count_instances_and_groups_them():
    plan = validate_and_parse(
        {
            "repeats": [
                {"id": "array", "count": 3, "kind": "Square", "props": {"side_length": 0.9}}
            ]
        }
    )
    code = compile_construction(plan)
    assert "self.array_0 = Square(side_length=0.9)" in code
    assert "self.array_1 = Square(side_length=0.9)" in code
    assert "self.array_2 = Square(side_length=0.9)" in code
    assert "self.array = VGroup(self.array_0, self.array_1, self.array_2)" in code
    _assert_valid_python(code)


def test_repeat_count_must_be_positive():
    with pytest.raises(ConstructionValidationError, match=r"positive integer"):
        validate_and_parse({"repeats": [{"id": "array", "count": 0, "kind": "Square", "props": {}}]})


def test_repeat_count_rejects_bool():
    with pytest.raises(ConstructionValidationError, match=r"positive integer"):
        validate_and_parse({"repeats": [{"id": "array", "count": True, "kind": "Square", "props": {}}]})


def test_node_may_reference_a_repeat_group_id():
    plan = validate_and_parse(
        {
            "repeats": [{"id": "array", "count": 2, "kind": "Square", "props": {}}],
            "nodes": [
                {
                    "id": "arrow",
                    "kind": "Arrow",
                    "refs": {"start_ref": "array", "end_ref": "array"},
                }
            ],
        }
    )
    code = compile_construction(plan)
    assert "self.arrow = Arrow(self.array.get_center(), self.array.get_center())" in code


# ------------------------------------------------------ real-evidence shape

def test_compiles_a_plan_shaped_like_the_real_evidence_file():
    """Mirrors the real generated scene shown mid-session: a title, a
    caption, a 4-element repeated array, and an arrow indicating access."""

    raw = {
        "repeats": [
            {
                "id": "array",
                "count": 4,
                "kind": "Square",
                "props": {"side_length": 0.9, "color": "BLUE"},
                "arrange_direction": "RIGHT",
                "arrange_buff": 0.1,
                "position": {"kind": "band", "band": "CENTER"},
            }
        ],
        "nodes": [
            {
                "id": "title",
                "kind": "Text",
                "props": {"content": "The Problem with Contiguous Arrays", "font_size": 40},
                "position": {"kind": "band", "band": "TITLE"},
            },
            {
                "id": "caption",
                "kind": "Text",
                "props": {"content": "How do we store data...", "font_size": 24},
                "position": {"kind": "band", "band": "CAPTION"},
            },
            {
                "id": "access_arrow",
                "kind": "Arrow",
                "refs": {"start_ref": "array", "end_ref": "array"},
            },
        ],
    }

    plan = validate_and_parse(raw)
    assert plan.schema_version == CONSTRUCTION_SCHEMA_VERSION

    code = compile_construction(plan)
    _assert_valid_python(code)

    assert "self.array_0 = Square(color=BLUE, side_length=0.9)" in code
    assert "self.array = VGroup(self.array_0, self.array_1, self.array_2, self.array_3)" in code
    assert "self.title = Text('The Problem with Contiguous Arrays', font_size=40)" in code
    assert "self.caption = Text('How do we store data...', font_size=24)" in code
    assert "self.access_arrow = Arrow(self.array.get_center(), self.array.get_center())" in code
