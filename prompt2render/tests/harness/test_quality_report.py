"""Tier 3 Phases 10 and 13: unified multi-verifier quality report.

Covers build_quality_report's dimension classification, blocking/warning/
pass counting, unmapped-verifier visibility, write_quality_report's
persistence/graceful-failure behavior, and (Phase 13) the graduated
per-dimension score, the weighted overall_score, weight overrides, and the
embedded scoring_version/weights that make a report self-describing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.quality_report import (
    DEFAULT_DIMENSION_WEIGHTS,
    DIMENSIONS,
    QUALITY_REPORT_SCHEMA_VERSION,
    SCORING_VERSION,
    build_quality_report,
    write_quality_report,
)


# ------------------------------------------------------- dimension mapping

def test_known_verifier_maps_to_its_dimension():
    report = build_quality_report({"verifier_semantic": [{"status": "pass"}]})
    assert report.dimensions["semantic"].total == 1
    assert report.dimensions["semantic"].verifiers == ["verifier_semantic"]


def test_lifecycle_maps_to_continuity_not_spatial():
    report = build_quality_report({"verifier_lifecycle": [{"status": "pass"}]})
    assert report.dimensions["continuity"].total == 1
    assert report.dimensions["spatial"].total == 0


def test_audio_maps_to_temporal():
    report = build_quality_report({"verifier_audio": [{"status": "pass"}]})
    assert report.dimensions["temporal"].total == 1


def test_all_six_target_architecture_dimensions_always_present():
    report = build_quality_report({})
    assert set(report.dimensions) == set(DIMENSIONS)
    assert len(DIMENSIONS) == 6


def test_unmapped_verifier_with_findings_is_visible_not_dropped():
    report = build_quality_report(
        {"verifier_execution": [{"status": "fail", "severity": "BLOCKING"}]}
    )
    assert "verifier_execution" in report.unmapped_verifiers
    assert all(s.total == 0 for s in report.dimensions.values())


def test_unmapped_verifier_with_no_findings_is_not_listed():
    report = build_quality_report({"verifier_execution": []})
    assert report.unmapped_verifiers == []


# ------------------------------------------------------------- counting ---

def test_blocking_warning_pass_counted_separately():
    report = build_quality_report(
        {
            "verifier_semantic": [
                {"status": "fail", "severity": "BLOCKING"},
                {"status": "warn", "severity": "WARNING"},
                {"status": "pass"},
            ]
        }
    )
    summary = report.dimensions["semantic"]
    assert summary.total == 3
    assert summary.blocking == 1
    assert summary.warning == 1
    assert summary.passed == 1


def test_blocking_dimensions_lists_only_dimensions_with_a_blocker():
    report = build_quality_report(
        {
            "verifier_semantic": [{"status": "pass"}],
            "verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}],
        }
    )
    assert report.blocking_dimensions == ["temporal"]


# --------------------------------------------------------- overall_score --
#
# Tier 3 Phase 13 replaced the placeholder (fraction of dimensions with zero
# blocking findings) with a graduated, weighted formula -- these two cases
# are the ones where the new formula is numerically identical to the old
# one (see quality_report.py's module docstring), so they still hold
# unchanged; new tests below exercise genuinely graduated behavior.

def test_overall_score_is_one_when_nothing_blocks():
    report = build_quality_report({"verifier_semantic": [{"status": "pass"}]})
    assert report.overall_score == 1.0


def test_overall_score_degrades_per_blocking_dimension():
    report = build_quality_report(
        {"verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}]}
    )
    # 5 of 6 dimensions clean.
    assert abs(report.overall_score - (5 / 6)) < 1e-9


# ------------------------------------------------- Phase 13: dimension score

def test_dimension_score_is_one_with_no_findings():
    report = build_quality_report({})
    assert all(s.score == 1.0 for s in report.dimensions.values())


def test_dimension_score_all_blocking_is_zero():
    report = build_quality_report(
        {"verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}]}
    )
    assert report.dimensions["temporal"].score == 0.0


def test_dimension_score_all_warning_is_half():
    report = build_quality_report(
        {"verifier_lifecycle": [{"status": "warn", "severity": "WARNING"}]}
    )
    assert report.dimensions["continuity"].score == 0.5


def test_dimension_score_is_graduated_not_binary():
    # One blocking finding among many passes should be penalized less than
    # one blocking finding alone -- this is exactly what the old binary
    # placeholder could not express.
    report = build_quality_report(
        {
            "verifier_semantic": [
                {"status": "fail", "severity": "BLOCKING"},
                {"status": "pass"},
                {"status": "pass"},
                {"status": "pass"},
            ]
        }
    )
    score = report.dimensions["semantic"].score
    assert 0.0 < score < 1.0
    assert score == pytest.approx(1.0 - 1 / 4)


# ---------------------------------------------------- Phase 13: weighting

def test_default_weights_are_equal_across_all_dimensions():
    assert len(set(DEFAULT_DIMENSION_WEIGHTS.values())) == 1
    assert set(DEFAULT_DIMENSION_WEIGHTS) == set(DIMENSIONS)


def test_custom_weights_change_overall_score():
    check_results = {
        "verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}],
        "verifier_semantic": [{"status": "pass"}],
    }

    equal = build_quality_report(check_results)
    # Zero-weight everything except the dimension that's actually failing --
    # overall_score should collapse to exactly that dimension's own score.
    only_temporal = build_quality_report(
        check_results,
        weights={"temporal": 1.0},
    )

    assert only_temporal.overall_score == 0.0
    assert only_temporal.overall_score != equal.overall_score


def test_weight_omitted_from_custom_table_is_excluded_not_zeroed():
    # A dimension missing from a custom weights table must not count as a
    # zero score dragging the average down -- it must be excluded outright.
    report = build_quality_report(
        {"verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}]},
        weights={"semantic": 1.0},  # temporal (the failing one) excluded
    )
    assert report.overall_score == 1.0  # only "semantic" counted, and it's clean


def test_no_positively_weighted_dimensions_defaults_to_clean():
    report = build_quality_report({}, weights={})
    assert report.overall_score == 1.0


# -------------------------------------------------- Phase 13: reproducibility

def test_scoring_version_and_weights_embedded_in_report():
    report = build_quality_report({})
    assert report.scoring_version == SCORING_VERSION
    assert report.weights == DEFAULT_DIMENSION_WEIGHTS


def test_custom_weights_are_embedded_verbatim():
    report = build_quality_report({}, weights={"semantic": 2.0})
    assert report.weights == {"semantic": 2.0}


def test_hash_changes_when_weights_change():
    a = build_quality_report({"verifier_semantic": [{"status": "pass"}]})
    b = build_quality_report(
        {"verifier_semantic": [{"status": "pass"}]},
        weights={"semantic": 2.0},
    )
    assert a.report_hash != b.report_hash


def test_two_verifiers_sharing_a_dimension_both_contribute():
    # Not a real pairing today, but the aggregation must not assume
    # one-verifier-per-dimension.
    report = build_quality_report(
        {
            "verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}],
            "verifier_audio": [{"status": "pass"}],
        }
    )
    summary = report.dimensions["temporal"]
    assert summary.total == 2
    assert sorted(summary.verifiers) == ["verifier_audio", "verifier_temporal"]


# ------------------------------------------------------------ hash/schema -

def test_schema_version_and_hash_present():
    report = build_quality_report({})
    assert report.schema_version == QUALITY_REPORT_SCHEMA_VERSION
    assert report.report_hash != ""
    assert report.compute_hash() == report.report_hash


def test_hash_changes_with_content():
    a = build_quality_report({"verifier_semantic": [{"status": "pass"}]})
    b = build_quality_report(
        {"verifier_semantic": [{"status": "fail", "severity": "BLOCKING"}]}
    )
    assert a.report_hash != b.report_hash


# ------------------------------------------------------------- persistence

def test_write_quality_report_persists_json(tmp_path):
    path = write_quality_report({"verifier_semantic": [{"status": "pass"}]}, tmp_path)
    assert path == tmp_path / "build" / "harness" / "quality_report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == QUALITY_REPORT_SCHEMA_VERSION


def test_write_quality_report_returns_none_without_project_dir():
    assert write_quality_report({}, None) is None


def test_write_quality_report_never_raises_on_bad_input():
    # A malformed check_results shape must degrade to None, not crash the
    # caller -- this is called right after a harness run (success or
    # GateFailure) and must never mask the real outcome.
    result = write_quality_report("not a dict", "/definitely/not/a/real/path")  # type: ignore[arg-type]
    assert result is None


def test_verifier_layout_is_mapped_to_spatial_dimension():
    # Bug fix: verifier_layout -- the real deterministic layout critic --
    # was entirely absent from VERIFIER_DIMENSIONS, so its findings never
    # moved overall_score even when it hard-gated a run.
    from prompt2render.harness.quality_report import VERIFIER_DIMENSIONS

    assert VERIFIER_DIMENSIONS["verifier_layout"] == "spatial"


def test_verifier_layout_findings_contribute_to_spatial_dimension():
    check_results = {
        "verifier_layout": [
            {"stem": "07", "status": "fail", "severity": "BLOCKING", "finding_type": "layout_violation"}
        ],
    }

    report = build_quality_report(check_results)

    assert report.dimensions["spatial"].total == 1
    assert report.dimensions["spatial"].blocking == 1
    assert "verifier_layout" in report.dimensions["spatial"].verifiers
    assert "verifier_layout" not in report.unmapped_verifiers
