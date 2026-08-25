"""Tier 3 Phase 10: unified multi-verifier quality report.

Covers build_quality_report's dimension classification, blocking/warning/
pass counting, the provisional overall_score formula, unmapped-verifier
visibility, and write_quality_report's persistence/graceful-failure
behavior.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.quality_report import (
    DIMENSIONS,
    QUALITY_REPORT_SCHEMA_VERSION,
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

def test_overall_score_is_one_when_nothing_blocks():
    report = build_quality_report({"verifier_semantic": [{"status": "pass"}]})
    assert report.overall_score == 1.0


def test_overall_score_degrades_per_blocking_dimension():
    report = build_quality_report(
        {"verifier_temporal": [{"status": "fail", "severity": "BLOCKING"}]}
    )
    # 5 of 6 dimensions clean.
    assert abs(report.overall_score - (5 / 6)) < 1e-9


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
