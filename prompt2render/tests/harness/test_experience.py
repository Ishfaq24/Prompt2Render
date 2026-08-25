"""Tier 3 Phase 15: cross-run experience memory.

Covers ExperienceRecord round-tripping, from_repair_records' defensive
conversion, append_experience's append-only (never overwrite) persistence,
load_experience's graceful degradation, and summarize_recurring's
recurring-only filtering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.experience import (
    EXPERIENCE_SCHEMA_VERSION,
    ExperienceRecord,
    append_experience,
    from_repair_records,
    load_experience,
    summarize_recurring,
)


def _record(finding_type="spatial_conflict", mismatch_subtype="overlap", occurrences_hint=""):
    return ExperienceRecord(
        finding_type=finding_type,
        mismatch_subtype=mismatch_subtype,
        routed_to=["generator_code"],
        outcome="attempted",
        cycles_used=1,
        diagnostic_message=f"collision {occurrences_hint}",
        recorded_at="2026-08-25T00:00:00Z",
    )


# --------------------------------------------------------------- round-trip

def test_to_dict_from_dict_round_trip():
    record = _record()
    assert ExperienceRecord.from_dict(record.to_dict()) == record


def test_from_dict_defaults_missing_fields():
    record = ExperienceRecord.from_dict({"finding_type": "x"})
    assert record.finding_type == "x"
    assert record.mismatch_subtype == ""
    assert record.routed_to == []
    assert record.schema_version == EXPERIENCE_SCHEMA_VERSION


# --------------------------------------------------------- from_repair_records

def test_from_repair_records_converts_valid_entries():
    repair_records = [
        {
            "finding_type": "spatial_conflict",
            "mismatch_subtype": "overlap",
            "routed_to": ["generator_code"],
            "outcome": "attempted",
            "cycles_used": 2,
            "diagnostic_message": "collision at (1,2)",
        }
    ]
    records = from_repair_records(repair_records, recorded_at="2026-08-25T00:00:00Z")
    assert len(records) == 1
    assert records[0].finding_type == "spatial_conflict"
    assert records[0].cycles_used == 2
    assert records[0].recorded_at == "2026-08-25T00:00:00Z"


def test_from_repair_records_skips_malformed_entries():
    repair_records = [
        "not a dict",
        {"no_finding_type": True},
        {"finding_type": "", "detail": "empty finding_type"},
        {"finding_type": "spatial_conflict"},
    ]
    records = from_repair_records(repair_records)
    assert len(records) == 1
    assert records[0].finding_type == "spatial_conflict"


def test_from_repair_records_empty_input():
    assert from_repair_records([]) == []


def test_from_repair_records_uses_current_time_when_unset():
    records = from_repair_records([{"finding_type": "x"}])
    assert records[0].recorded_at  # non-empty, some timestamp was generated


# -------------------------------------------------------------- persistence

def test_append_and_load_round_trip(tmp_path):
    records = [_record(), _record(finding_type="motion_absence", mismatch_subtype="motion_absence")]
    path = append_experience(tmp_path, records)

    assert path == tmp_path / "build" / "harness" / "experience_memory.jsonl"
    assert path.exists()

    loaded = load_experience(tmp_path)
    assert loaded == records


def test_append_is_additive_across_calls(tmp_path):
    append_experience(tmp_path, [_record(finding_type="a")])
    append_experience(tmp_path, [_record(finding_type="b")])

    loaded = load_experience(tmp_path)
    assert [r.finding_type for r in loaded] == ["a", "b"]


def test_append_never_overwrites_prior_runs(tmp_path):
    """The entire point of this module -- unlike self_correction_report.json's
    per-run path.write_text overwrite, experience memory must survive
    multiple separate "runs" (separate append_experience calls)."""

    append_experience(tmp_path, [_record()])
    path = tmp_path / "build" / "harness" / "experience_memory.jsonl"
    first_run_content = path.read_text(encoding="utf-8")

    append_experience(tmp_path, [_record(finding_type="second_run_finding")])
    second_run_content = path.read_text(encoding="utf-8")

    assert first_run_content in second_run_content
    assert second_run_content != first_run_content


def test_append_experience_with_no_records_is_noop(tmp_path):
    assert append_experience(tmp_path, []) is None
    assert not (tmp_path / "build" / "harness" / "experience_memory.jsonl").exists()


def test_append_experience_without_project_dir_is_noop():
    assert append_experience(None, [_record()]) is None


def test_load_experience_missing_file_returns_empty(tmp_path):
    assert load_experience(tmp_path) == []


def test_load_experience_without_project_dir_returns_empty():
    assert load_experience(None) == []


def test_load_experience_skips_corrupt_lines(tmp_path):
    path = tmp_path / "build" / "harness" / "experience_memory.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_record().to_dict()) + "\n"
        + "not valid json\n"
        + "\n"  # blank line
        + json.dumps(_record(finding_type="second").to_dict()) + "\n",
        encoding="utf-8",
    )

    loaded = load_experience(tmp_path)
    assert [r.finding_type for r in loaded] == ["spatial_conflict", "second"]


# ------------------------------------------------------------- summarization

def test_summarize_recurring_excludes_one_off_pairs():
    records = [_record(), _record(finding_type="only_once")]
    assert summarize_recurring(records) == []


def test_summarize_recurring_counts_and_sorts_by_frequency():
    records = (
        [_record()] * 3
        + [_record(finding_type="motion_absence", mismatch_subtype="motion_absence")] * 2
    )
    summary = summarize_recurring(records)
    assert summary[0] == {
        "finding_type": "spatial_conflict",
        "mismatch_subtype": "overlap",
        "occurrences": 3,
    }
    assert summary[1]["occurrences"] == 2


def test_summarize_recurring_empty_input():
    assert summarize_recurring([]) == []
