"""Structured resolved/introduced/unchanged finding diff.

``new_blocking_types`` already stops a repair from trading one defect for
another, but only reports the *introduced* half -- a decision log reader
cannot see what was actually fixed without re-deriving it from two
``blocking_types`` dicts by hand. ``diff_findings`` closes that gap.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.scene_quality import SceneQuality, diff_findings


def _quality(blocking_types: dict[str, int]) -> SceneQuality:
    return SceneQuality(
        stem="07",
        blocking=sum(blocking_types.values()),
        blocking_types=dict(blocking_types),
    )


def test_case_a_clean_to_clean_is_all_empty():
    accepted = _quality({})
    candidate = _quality({})

    diff = diff_findings(accepted, candidate)

    assert diff.resolved == ()
    assert diff.introduced == ()
    assert diff.unchanged == ()


def test_case_b_layout_fixed_semantic_introduced():
    # The brief's CASE B: repair fixes layout, introduces semantic.
    accepted = _quality({"layout_violation": 1})
    candidate = _quality({"semantic_mismatch": 1})

    diff = diff_findings(accepted, candidate)

    assert diff.resolved == ("layout_violation",)
    assert diff.introduced == ("semantic_mismatch",)
    assert diff.unchanged == ()


def test_unchanged_defect_is_neither_resolved_nor_introduced():
    accepted = _quality({"semantic_mismatch": 1})
    candidate = _quality({"semantic_mismatch": 1})

    diff = diff_findings(accepted, candidate)

    assert diff.resolved == ()
    assert diff.introduced == ()
    assert diff.unchanged == ("semantic_mismatch",)


def test_partial_resolution_of_a_repeated_type_still_counts_as_resolved():
    # Count dropped 2 -> 1: strictly better on this type, so it is
    # "resolved" even though one instance remains -- the type is not
    # simultaneously unchanged.
    accepted = _quality({"layout_violation": 2})
    candidate = _quality({"layout_violation": 1})

    diff = diff_findings(accepted, candidate)

    assert diff.resolved == ("layout_violation",)
    assert diff.unchanged == ()


def test_to_dict_is_json_shaped():
    diff = diff_findings(_quality({"a": 1}), _quality({}))
    assert diff.to_dict() == {"resolved": ["a"], "introduced": [], "unchanged": []}


def test_multiple_types_sorted_deterministically():
    accepted = _quality({"z_type": 1, "a_type": 1})
    candidate = _quality({})

    diff = diff_findings(accepted, candidate)

    assert diff.resolved == ("a_type", "z_type")
