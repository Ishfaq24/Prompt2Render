"""Unified multi-verifier quality report -- Tier 3 Phase 10.

Tier 3 (docs/ARCHITECTURE_AUDIT.md SS17, Phases 10-15) opens with "unified
multi-verifier" — named once, with no elaboration or F-number anywhere else
in the repo (same situation Phase 3/6 in Tier 2 were in). Given concrete
meaning here: today, `harness/plugins/*` has 9 independent verifiers (SS6's
table), each writing its own `context.check_results[plugin.name]` entry,
each gated in isolation, with no shared view of "how good is this video
overall." This module is that shared view -- a read-only aggregation over
already-produced ``check_results``, classified into the target
architecture's own quality dimensions (SS16: "semantic | temporal |
spatial | motion | continuity | pedagogical").

Deliberately scoped to aggregation only, per explicit user direction:
- Does **not** touch any of the 9 existing verifier plugins or their gates.
- Does **not** attempt a final scoring formula -- `overall_score` here is a
  clearly-provisional placeholder (fraction of dimensions with zero
  blocking findings). Tier 3 Phase 13 ("reproducible weighted quality
  scoring") is where that gets designed properly.
- Is **not** a DAG-tracked plugin. ``check_results`` is the one
  ``MERGEABLE_EFFECTS`` field multiple plugins write to concurrently
  (``loader.py``), and the topological sort only guarantees "runs after
  the *first* producer", not "runs after *every* producer" -- there is no
  dependency-declaration that correctly expresses "after all verifiers."
  Instead, matching the existing precedent of
  ``logging_.write_self_correction_report`` (called directly by the CLI
  after a harness run, not wired as a plugin), this module's
  ``write_quality_report`` is called directly after ``HarnessRunner.run()``
  completes (success or ``GateFailure``), when ``context.check_results`` is
  known-complete.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Quality report schema version.
QUALITY_REPORT_SCHEMA_VERSION = "1.0"

#: Every dimension the target architecture names (SS16), even ones no
#: current verifier covers -- "motion" has no verifier at all today (a
#: real, documented gap; Tier 3 Phase 12 "motion traces" is presumably
#: where that gets filled in), so it always reports zero findings rather
#: than being silently absent from the report.
DIMENSIONS = (
    "semantic",
    "temporal",
    "spatial",
    "motion",
    "continuity",
    "pedagogical",
)

#: Verifier plugin name -> quality dimension. Verifiers whose job is build/
#: structural correctness rather than content quality (verifier_storyboard,
#: verifier_execution, the two final_qc variants) are intentionally left
#: unmapped -- they show up in ``unmapped_verifiers``, not force-fit into a
#: content dimension that doesn't really describe them.
VERIFIER_DIMENSIONS: dict[str, str] = {
    "verifier_pedagogy": "pedagogical",
    "verifier_semantic": "semantic",
    "verifier_temporal": "temporal",
    "verifier_spatial": "spatial",
    # k.array length changes between adjacent scenes is fundamentally a
    # continuity check (does the data structure's visible state persist
    # correctly across the cut), not a spatial or semantic one.
    "verifier_lifecycle": "continuity",
    # Caption drift over the final video is a timing-alignment concern,
    # same family as verifier_temporal's narration-duration check.
    "verifier_audio": "temporal",
}


@dataclass
class DimensionSummary:
    dimension: str
    total: int = 0
    blocking: int = 0
    warning: int = 0
    passed: int = 0
    verifiers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "total": self.total,
            "blocking": self.blocking,
            "warning": self.warning,
            "passed": self.passed,
            "verifiers": list(self.verifiers),
        }


@dataclass
class QualityReport:
    schema_version: str
    dimensions: dict[str, DimensionSummary]
    overall_score: float
    blocking_dimensions: list[str]
    unmapped_verifiers: list[str]
    report_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dimensions": {
                name: summary.to_dict() for name, summary in self.dimensions.items()
            },
            "overall_score": self.overall_score,
            "blocking_dimensions": list(self.blocking_dimensions),
            "unmapped_verifiers": list(self.unmapped_verifiers),
            "report_hash": self.report_hash,
        }

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("report_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_blocking(finding: Any) -> bool:
    return (
        isinstance(finding, dict)
        and str(finding.get("status", "")).lower() == "fail"
        and str(finding.get("severity", "")) == "BLOCKING"
    )


def _is_warning(finding: Any) -> bool:
    return (
        isinstance(finding, dict)
        and str(finding.get("status", "")).lower() in ("fail", "warn")
        and str(finding.get("severity", "")) == "WARNING"
    )


def _is_pass(finding: Any) -> bool:
    return isinstance(finding, dict) and str(finding.get("status", "")).lower() == "pass"


def build_quality_report(
    check_results: dict[str, list[dict[str, Any]]],
) -> QualityReport:
    """Aggregate every verifier's ``check_results`` entry into one report,
    grouped by quality dimension. Pure function -- no ``SceneContext``, no
    file I/O (see :func:`write_quality_report` for the persisted form).
    """

    dimensions: dict[str, DimensionSummary] = {
        dimension: DimensionSummary(dimension=dimension) for dimension in DIMENSIONS
    }
    unmapped: list[str] = []

    for plugin_name, findings in (check_results or {}).items():
        dimension = VERIFIER_DIMENSIONS.get(plugin_name)

        if dimension is None:
            if isinstance(findings, list) and findings:
                unmapped.append(plugin_name)
            continue

        summary = dimensions[dimension]

        if plugin_name not in summary.verifiers:
            summary.verifiers.append(plugin_name)

        for finding in findings or []:
            summary.total += 1

            if _is_blocking(finding):
                summary.blocking += 1
            elif _is_warning(finding):
                summary.warning += 1
            elif _is_pass(finding):
                summary.passed += 1

    blocking_dimensions = sorted(
        name for name, summary in dimensions.items() if summary.blocking > 0
    )

    # Provisional formula (Tier 3 Phase 13 designs the real one): the
    # fraction of dimensions with zero blocking findings. A dimension no
    # verifier touched this run counts as clean (nothing to report is not
    # the same as failing), not as a penalty.
    clean = sum(1 for summary in dimensions.values() if summary.blocking == 0)
    overall_score = clean / len(dimensions) if dimensions else 1.0

    report = QualityReport(
        schema_version=QUALITY_REPORT_SCHEMA_VERSION,
        dimensions=dimensions,
        overall_score=overall_score,
        blocking_dimensions=blocking_dimensions,
        unmapped_verifiers=sorted(set(unmapped)),
    )
    report.report_hash = report.compute_hash()

    return report


def write_quality_report(
    check_results: dict[str, list[dict[str, Any]]],
    project_dir: Path | None,
) -> Path | None:
    """Persist ``build/harness/quality_report.json``. Never raises -- a bug
    in report generation must not mask the real success/failure of a
    harness run; returns ``None`` on any failure or when ``project_dir`` is
    unset."""

    if project_dir is None:
        return None

    try:
        report = build_quality_report(check_results)
        path = Path(project_dir) / "build" / "harness" / "quality_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
    except Exception:
        return None
