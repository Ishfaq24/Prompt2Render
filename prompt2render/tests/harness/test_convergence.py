"""No-progress / oscillation detection tests (brief CASE G and CASE H).

Pure unit tests over ConvergenceTracker -- no repair controller, no
SceneContext, no LLM, no render.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.convergence import (
    CandidateSignature,
    ConvergenceTracker,
    StopReason,
)


def _sig(code: str, findings: list[str]) -> CandidateSignature:
    return CandidateSignature.of(code, findings)


def test_first_candidate_is_never_a_stop_reason():
    tracker = ConvergenceTracker()
    reason = tracker.record("07", _sig("v1", ["layout_violation"]))
    assert reason is StopReason.NONE


def test_case_g_repeated_identical_finding_signature_is_no_progress():
    tracker = ConvergenceTracker()
    tracker.record("07", _sig("v1", ["caption_collision"]))

    # revision 2: source differs, but the same defect is still present --
    # e.g. "caption y = -3.2 -> FAIL" repeated at the next revision.
    reason = tracker.record("07", _sig("v2", ["caption_collision"]))

    assert reason is StopReason.NO_PROGRESS


def test_case_h_oscillation_a_b_a():
    tracker = ConvergenceTracker()
    tracker.record("07", _sig("v1", ["layout_violation"]))
    tracker.record("07", _sig("v2", ["semantic_mismatch"]))

    # Back to the same finding signature as v1, having passed through a
    # distinct v2 in between -- this must be OSCILLATION, not NO_PROGRESS
    # (NO_PROGRESS only compares against the immediately preceding cycle).
    reason = tracker.record("07", _sig("v3", ["layout_violation"]))

    assert reason is StopReason.REPAIR_OSCILLATION


def test_identical_source_reproposed_is_flagged_even_with_different_findings():
    tracker = ConvergenceTracker()
    tracker.record("07", _sig("same-source", ["a"]))

    # Same exact candidate source text proposed again -- caught even before
    # comparing findings, and even if (implausibly) findings differ this
    # run because of an unrelated evidence-availability flip.
    reason = tracker.record("07", _sig("same-source", ["b"]))

    assert reason is StopReason.IDENTICAL_CANDIDATE


def test_genuine_progress_is_not_flagged():
    tracker = ConvergenceTracker()
    tracker.record("07", _sig("v1", ["layout_violation", "semantic_mismatch"]))
    reason = tracker.record("07", _sig("v2", ["semantic_mismatch"]))

    assert reason is StopReason.NONE


def test_scenes_are_tracked_independently():
    tracker = ConvergenceTracker()
    tracker.record("01", _sig("v1", ["a"]))

    # A different scene's first candidate must not be contaminated by
    # another scene's history.
    reason = tracker.record("02", _sig("v1", ["a"]))

    assert reason is StopReason.NONE


def test_reset_clears_one_scene_only():
    tracker = ConvergenceTracker()
    tracker.record("01", _sig("v1", ["a"]))
    tracker.record("02", _sig("v1", ["a"]))

    tracker.reset("01")

    assert tracker.record("01", _sig("v2", ["a"])) is StopReason.NONE
    # "02" still has its identical-signature history.
    assert tracker.record("02", _sig("v2", ["a"])) is StopReason.NO_PROGRESS


def test_signature_of_is_deterministic():
    a = CandidateSignature.of("code", ["x", "y"])
    b = CandidateSignature.of("code", ["y", "x"])
    assert a == b  # order of finding types must not matter
