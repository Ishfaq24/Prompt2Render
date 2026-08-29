"""Run metrics -- a pure aggregation over evidence the harness already
produces, written to ``build/harness/metrics.json``.

Deliberately not a new instrumentation surface. Every number here is
derived from data structures that already exist:

* :class:`~prompt2render.harness.repair_controller.RepairDecisionRecord`
  (the repair controller's own decision log) for every repair-related
  count.
* ``log.jsonl``'s already-recorded ``duration_s`` per plugin invocation
  (:class:`~prompt2render.harness.logging_.StructuredLogger`) for
  per-plugin latency.

Matches the precedent already set by ``quality_report.write_quality_report``
and ``experience.append_experience``: a pure aggregation function, called
directly by ``cmd_harness`` after a run, that never raises -- a bug in
metrics computation must not be the reason a build's real result is lost.

Explicitly NOT covered here: token/LLM-call accounting. ``logging_``'s
``token_usage`` field has existed since before this module and no call site
has ever populated it (a pre-existing gap, not something this module hides
or duplicates) -- adding that instrumentation means threading usage data
out of ``llm.py`` through every plugin that calls it, which is a
meaningfully larger, riskier change than a pure aggregation over data that
already exists. Left as documented future work rather than half-wired here.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

METRICS_SCHEMA_VERSION = "1.0"

#: Decisions counted as "the repair changed something and it stuck".
_SUCCESS_DECISIONS = {"accepted"}

#: Decisions where a candidate was opened, evaluated, and then discarded --
#: as opposed to NOT_ROUTABLE/REPAIR_BUDGET_EXHAUSTED, where no candidate
#: was ever produced.
_ROLLBACK_DECISIONS = {
    "regression_rejected",
    "verifier_failed",
    "target_defect_unresolved",
    "repair_errored",
    "no_progress",
    "repair_oscillation",
}


@dataclass
class RepairMetrics:
    """Counts derived from one run's repair decision log."""

    repair_attempts: int = 0
    successful_repairs: int = 0
    rejected_repairs: int = 0
    rollback_count: int = 0
    regression_count: int = 0
    no_progress_count: int = 0
    oscillation_count: int = 0
    not_routable_count: int = 0
    budget_exhausted_count: int = 0
    #: Mean number of repair cycles per scene that was repaired at least
    #: once. A scene never routed to repair does not appear in the
    #: denominator -- this measures how hard the scenes that DID need
    #: repair were to fix, not how many scenes existed.
    average_revisions: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_repair_metrics(decisions: "list[Any]") -> RepairMetrics:
    """Pure aggregation over ``RepairController.decisions``.

    Accepts ``RepairDecisionRecord`` instances or their ``.to_dict()``
    dicts, matching ``experience.from_decision_records``'s tolerance --
    a caller reading decisions back from ``repair_log.jsonl`` can reuse
    this without re-inflating dataclasses first.
    """

    metrics = RepairMetrics()
    attempts_per_stem: dict[str, int] = defaultdict(int)

    for entry in decisions:
        data = entry.to_dict() if hasattr(entry, "to_dict") else entry

        if not isinstance(data, dict):
            continue

        metrics.repair_attempts += 1

        decision = str(data.get("decision", ""))
        stem = str(data.get("stem", ""))

        if stem:
            attempts_per_stem[stem] += 1

        if decision in _SUCCESS_DECISIONS:
            metrics.successful_repairs += 1
        else:
            metrics.rejected_repairs += 1

        if decision in _ROLLBACK_DECISIONS:
            metrics.rollback_count += 1

        if decision == "regression_rejected":
            metrics.regression_count += 1
        elif decision == "no_progress":
            metrics.no_progress_count += 1
        elif decision == "repair_oscillation":
            metrics.oscillation_count += 1
        elif decision == "not_routable":
            metrics.not_routable_count += 1
        elif decision == "repair_budget_exhausted":
            metrics.budget_exhausted_count += 1

    if attempts_per_stem:
        metrics.average_revisions = sum(attempts_per_stem.values()) / len(attempts_per_stem)

    return metrics


def build_stage_latency(log_path: Path | None) -> dict[str, float]:
    """Total seconds spent in each plugin, from ``log.jsonl``'s own
    already-recorded ``duration_s`` -- no new timing instrumentation.

    Never raises: a missing or corrupt log degrades to an empty mapping.
    """

    if log_path is None:
        return {}

    path = Path(log_path)

    if not path.exists():
        return {}

    totals: dict[str, float] = defaultdict(float)

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if record.get("event") != "plugin.invocation":
                    continue

                plugin = record.get("plugin")
                duration = record.get("duration_s")

                if plugin and isinstance(duration, (int, float)):
                    totals[str(plugin)] += float(duration)
    except OSError:
        return {}

    return dict(totals)


def write_metrics_report(
    project_dir: Path | None,
    decisions: "list[Any]",
    *,
    log_path: Path | None = None,
) -> Path | None:
    """Write ``build/harness/metrics.json``. Never raises.

    Returns the path written, or ``None`` if ``project_dir`` is unset or
    the write failed -- callers (``cmd_harness``) treat both the same way
    ``write_quality_report`` already does: log the intent, ignore the
    return value on the happy path.
    """

    if project_dir is None:
        return None

    try:
        path = Path(project_dir) / "build" / "harness" / "metrics.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Model fallback telemetry (Phase 17): a model switch is never
        # silent. Best-effort read of the shared llm rotation records.
        try:
            from .. import llm as _llm

            fallbacks = list(_llm.fallback_records())
        except Exception:
            fallbacks = []

        payload = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "repair": build_repair_metrics(decisions).to_dict(),
            "stage_latency_seconds": build_stage_latency(log_path),
            "model_fallbacks": {
                "count": len(fallbacks),
                "records": fallbacks,
            },
        }

        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return path
    except Exception:
        return None


__all__ = [
    "METRICS_SCHEMA_VERSION",
    "RepairMetrics",
    "build_repair_metrics",
    "build_stage_latency",
    "write_metrics_report",
]
