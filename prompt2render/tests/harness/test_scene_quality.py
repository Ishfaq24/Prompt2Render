"""Deterministic per-scene quality evidence and comparison.

This is the measuring instrument behind the repair acceptance rule, so the
ordering it implements is tested exhaustively: a mistake here means either
silently accepting a downgraded scene or rejecting every legitimate repair.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness import lineage
from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.scene_quality import (
    SceneQuality,
    Verdict,
    classify,
    compare,
    new_blocking_types,
)


# --------------------------------------------------------------- classify

def test_classify_infers_blocking_from_status_without_severity():
    """The key hardening: most verifiers hand-write dicts with no severity."""
    assert classify({"status": "fail"}) == "blocking"


def test_classify_explicit_warning_severity_downgrades_a_fail():
    assert classify({"status": "fail", "severity": "WARNING"}) == "warning"


def test_classify_buckets():
    assert classify({"status": "fail", "severity": "BLOCKING"}) == "blocking"
    assert classify({"status": "warn"}) == "warning"
    assert classify({"status": "pass"}) == "pass"
    assert classify({"status": "skip"}) == "skip"


def test_classify_unknown_status_is_skip():
    # Covers the router's historical "resolved"/"open_defect" rewrites --
    # neither carries a usable verdict.
    assert classify({"status": "resolved"}) == "skip"
    assert classify({"status": "open_defect"}) == "skip"
    assert classify("not a dict") == "skip"


# ---------------------------------------------------------------- collect

def _ctx_with_findings(stem: str, findings: list[dict]) -> SceneContext:
    ctx = SceneContext()
    ctx.scene_versions[stem] = 2
    ctx.check_results["verifier_x"] = findings
    return ctx


def test_collect_counts_by_bucket():
    ctx = _ctx_with_findings(
        "03",
        [
            {"status": "fail", "stem": "03", "finding_type": "spatial_conflict"},
            {"status": "warn", "stem": "03", "finding_type": "motion_absence"},
            {"status": "pass", "stem": "03", "finding_type": "temporal_match"},
            {"status": "skip", "stem": "03", "finding_type": "motion_trace_unavailable"},
        ],
    )
    q = SceneQuality.collect(ctx, "03")

    assert (q.blocking, q.warnings, q.passes, q.skips) == (1, 1, 1, 1)
    assert q.revision == 2
    assert q.blocking_types == {"spatial_conflict": 1}
    assert q.has_evidence is True
    assert q.total == 4


def test_collect_ignores_other_scenes_and_whole_video_findings():
    ctx = _ctx_with_findings(
        "03",
        [
            {"status": "fail", "stem": "07", "finding_type": "other_scene"},
            {"status": "fail", "finding_type": "no_stem_at_all"},
            {"status": "fail", "stem": "__all__", "finding_type": "global"},
            {"status": "fail", "stem": "03", "finding_type": "mine"},
        ],
    )
    q = SceneQuality.collect(ctx, "03")

    assert q.blocking == 1
    assert q.blocking_types == {"mine": 1}


def test_collect_has_no_evidence_when_scene_unreported():
    ctx = SceneContext()
    assert SceneQuality.collect(ctx, "03").has_evidence is False


def test_collect_recovers_temporal_difference():
    ctx = _ctx_with_findings(
        "03",
        [{"status": "pass", "stem": "03", "difference": -0.42}],
    )
    # Absolute value: direction of drift doesn't matter, magnitude does.
    assert SceneQuality.collect(ctx, "03").temporal_difference == 0.42


def test_collect_recovers_motion_delta_from_artifact_not_findings():
    """verifier_motion formats delta into prose and drops it; the raw float
    survives on RenderArtifact.motion, which is where we read it."""
    ctx = _ctx_with_findings("03", [{"status": "pass", "stem": "03"}])
    artifact = RenderArtifact(stem="03")
    artifact.motion = {
        "status": "ok",
        "traces": [
            {"state": "a", "delta": 0.30},
            {"state": "b", "delta": 0.05},
        ],
    }
    ctx.render_artifacts["03"] = artifact

    assert SceneQuality.collect(ctx, "03").motion_min_delta == 0.05


def test_collect_motion_delta_none_when_trace_unavailable():
    ctx = _ctx_with_findings("03", [{"status": "pass", "stem": "03"}])
    artifact = RenderArtifact(stem="03")
    artifact.motion = {"status": "skip", "traces": []}
    ctx.render_artifacts["03"] = artifact

    assert SceneQuality.collect(ctx, "03").motion_min_delta is None


# ---------------------------------------------------------------- compare

def _q(stem="03", **kw) -> SceneQuality:
    return SceneQuality(stem=stem, **kw)


def test_fewer_blocking_is_better():
    got = compare(_q(blocking=2, passes=1), _q(blocking=0, passes=3))
    assert got.verdict is Verdict.BETTER
    assert "blocking findings 2 -> 0" in got.reason


def test_more_blocking_is_worse():
    assert compare(
        _q(blocking=0, passes=3), _q(blocking=1, passes=2)
    ).verdict is Verdict.WORSE


def test_blocking_dominates_a_warning_improvement():
    """No amount of warning cleanup compensates for a new blocking defect."""
    got = compare(
        _q(blocking=0, warnings=9, passes=1),
        _q(blocking=1, warnings=0, passes=1),
    )
    assert got.verdict is Verdict.WORSE


def test_warnings_break_a_blocking_tie():
    better = compare(_q(blocking=1, warnings=4, passes=1), _q(blocking=1, warnings=1, passes=1))
    worse = compare(_q(blocking=1, warnings=1, passes=1), _q(blocking=1, warnings=4, passes=1))
    assert better.verdict is Verdict.BETTER
    assert worse.verdict is Verdict.WORSE


def test_more_skips_is_worse_because_it_is_less_assurance():
    got = compare(
        _q(blocking=0, warnings=0, passes=4, skips=0),
        _q(blocking=0, warnings=0, passes=1, skips=3),
    )
    assert got.verdict is Verdict.WORSE
    assert "skip" in got.reason


def test_tighter_temporal_timing_breaks_a_count_tie():
    got = compare(
        _q(passes=2, temporal_difference=0.90),
        _q(passes=2, temporal_difference=0.10),
    )
    assert got.verdict is Verdict.BETTER
    assert "narration timing" in got.reason


def test_more_motion_breaks_a_count_tie():
    got = compare(
        _q(passes=2, motion_min_delta=0.002),
        _q(passes=2, motion_min_delta=0.400),
    )
    assert got.verdict is Verdict.BETTER
    assert "motion" in got.reason


def test_numeric_noise_below_epsilon_does_not_decide():
    got = compare(
        _q(passes=2, temporal_difference=0.5000),
        _q(passes=2, temporal_difference=0.5001),
    )
    assert got.verdict is Verdict.EQUAL


def test_identical_evidence_is_equal():
    got = compare(_q(blocking=1, warnings=2, passes=3), _q(blocking=1, warnings=2, passes=3))
    assert got.verdict is Verdict.EQUAL


def test_candidate_without_any_findings_is_insufficient_evidence():
    """An unverified candidate is never an improvement on a verified scene,
    however the counts happen to compare."""
    got = compare(_q(blocking=5, passes=1), _q())
    assert got.verdict is Verdict.INSUFFICIENT_EVIDENCE


def test_no_prior_evidence_accepts_only_a_clean_candidate():
    assert compare(_q(), _q(passes=3)).verdict is Verdict.BETTER
    assert compare(_q(), _q(blocking=1, passes=1)).verdict is Verdict.WORSE


def test_comparison_is_serializable_for_the_decision_log():
    payload = compare(_q(blocking=1), _q(blocking=0, passes=1)).to_dict()
    assert payload["verdict"] == "better"
    assert payload["reason"]
    assert payload["accepted"]["blocking"] == 1
    assert payload["candidate"]["blocking"] == 0


# ------------------------------------------------------ new_blocking_types

def test_detects_a_swapped_defect_at_constant_blocking_count():
    """The case a pure count cannot see: same number of blocking findings,
    but the repair traded a layout collision for a continuity break."""
    accepted = _q(blocking=1, blocking_types={"spatial_conflict": 1})
    candidate = _q(blocking=1, blocking_types={"lifecycle_violation": 1})

    assert new_blocking_types(accepted, candidate) == {"lifecycle_violation": 1}
    # ...and the count-based comparison alone would have called it EQUAL.
    assert compare(accepted, candidate).verdict is Verdict.EQUAL


def test_no_new_types_when_candidate_only_removes():
    accepted = _q(blocking=2, blocking_types={"spatial_conflict": 2})
    candidate = _q(blocking=1, blocking_types={"spatial_conflict": 1})
    assert new_blocking_types(accepted, candidate) == {}


def test_counts_an_increase_of_an_existing_type():
    accepted = _q(blocking=1, blocking_types={"spatial_conflict": 1})
    candidate = _q(blocking=3, blocking_types={"spatial_conflict": 3})
    assert new_blocking_types(accepted, candidate) == {"spatial_conflict": 2}


# ------------------------------------------------- integration with lineage

def test_collect_reflects_current_revision():
    ctx = SceneContext()
    ctx.check_results["v"] = [{"status": "pass", "stem": "03"}]
    lineage.ensure_tracked(ctx, "03")
    assert SceneQuality.collect(ctx, "03").revision == 1
    lineage.bump(ctx, "03")
    assert SceneQuality.collect(ctx, "03").revision == 2
