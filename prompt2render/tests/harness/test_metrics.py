"""Run metrics (P2-1): pure aggregation over RepairController.decisions
and log.jsonl's already-recorded duration_s. No new instrumentation, no
LLM, no render.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.metrics import (
    RepairMetrics,
    build_repair_metrics,
    build_stage_latency,
    write_metrics_report,
)


def _decision(stem: str, decision: str) -> dict:
    return {"stem": stem, "decision": decision}


def test_empty_decisions_yields_zeroed_metrics():
    metrics = build_repair_metrics([])
    assert metrics == RepairMetrics()


def test_counts_accepted_and_rejected():
    metrics = build_repair_metrics([
        _decision("01", "accepted"),
        _decision("02", "regression_rejected"),
        _decision("03", "target_defect_unresolved"),
    ])

    assert metrics.repair_attempts == 3
    assert metrics.successful_repairs == 1
    assert metrics.rejected_repairs == 2
    assert metrics.regression_count == 1


def test_no_progress_and_oscillation_counted_separately():
    metrics = build_repair_metrics([
        _decision("01", "no_progress"),
        _decision("01", "repair_oscillation"),
    ])

    assert metrics.no_progress_count == 1
    assert metrics.oscillation_count == 1
    # Both are rollback-shaped decisions (a candidate was opened and
    # discarded), so both count toward rollback_count too.
    assert metrics.rollback_count == 2


def test_not_routable_and_budget_exhausted_are_not_rollbacks():
    # No candidate was ever opened for either -- rollback_count must not
    # count them.
    metrics = build_repair_metrics([
        _decision("01", "not_routable"),
        _decision("02", "repair_budget_exhausted"),
    ])

    assert metrics.not_routable_count == 1
    assert metrics.budget_exhausted_count == 1
    assert metrics.rollback_count == 0


def test_average_revisions_is_per_repaired_scene():
    metrics = build_repair_metrics([
        _decision("01", "regression_rejected"),
        _decision("01", "accepted"),
        _decision("02", "accepted"),
    ])

    # scene 01 took 2 attempts, scene 02 took 1 -- mean is 1.5.
    assert metrics.average_revisions == 1.5


def test_accepts_dataclass_instances_via_to_dict():
    from prompt2render.harness.repair_controller import Decision, RepairDecisionRecord

    record = RepairDecisionRecord(cycle_id=1, stem="01", trigger_finding_type="x",
                                   source_plugin="y", decision=Decision.ACCEPTED.value)
    metrics = build_repair_metrics([record])
    assert metrics.successful_repairs == 1


def test_build_stage_latency_sums_duration_by_plugin(tmp_path):
    log_path = tmp_path / "log.jsonl"
    log_path.write_text(
        "\n".join([
            json.dumps({"event": "plugin.invocation", "plugin": "verifier_layout", "duration_s": 0.5}),
            json.dumps({"event": "plugin.invocation", "plugin": "verifier_layout", "duration_s": 0.25}),
            json.dumps({"event": "plugin.invocation", "plugin": "renderer_stills", "duration_s": 2.0}),
            json.dumps({"event": "runner.info", "message": "not an invocation"}),
        ]),
        encoding="utf-8",
    )

    latency = build_stage_latency(log_path)
    assert latency["verifier_layout"] == 0.75
    assert latency["renderer_stills"] == 2.0
    assert "runner.info" not in latency


def test_build_stage_latency_missing_file_returns_empty(tmp_path):
    assert build_stage_latency(tmp_path / "does_not_exist.jsonl") == {}


def test_build_stage_latency_none_path_returns_empty():
    assert build_stage_latency(None) == {}


def test_write_metrics_report_writes_valid_json(tmp_path):
    log_path = tmp_path / "build" / "harness" / "log.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps({"event": "plugin.invocation", "plugin": "generator_code", "duration_s": 1.0}) + "\n",
        encoding="utf-8",
    )

    path = write_metrics_report(
        tmp_path, [_decision("01", "accepted")], log_path=log_path,
    )

    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["repair"]["successful_repairs"] == 1
    assert data["stage_latency_seconds"]["generator_code"] == 1.0


def test_write_metrics_report_none_project_dir_returns_none():
    assert write_metrics_report(None, []) is None


def test_write_metrics_report_never_raises_on_bad_decisions(tmp_path):
    # A malformed entry must not crash report generation.
    path = write_metrics_report(tmp_path, ["not a dict", 123, None])
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["repair"]["repair_attempts"] == 0
