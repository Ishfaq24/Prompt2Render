"""Unified multi-verifier quality report -- Tier 3 Phases 10 and 13.

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

Tier 3 Phase 13 ("reproducible weighted quality scoring") replaces Phase
10's placeholder formula (the fraction of dimensions with zero blocking
findings) with a graduated one: each dimension gets its own ``score`` in
[0, 1] from its actual blocking/warning counts (:func:`_dimension_score`),
and ``overall_score`` is a weighted average of those
(:data:`DEFAULT_DIMENSION_WEIGHTS`, all six equal by default -- SS16 states
no priority order between them, and there is no evidence in this repo yet to
justify weighting one content dimension over another; the mechanism is the
point, not a specific set of numbers). "Reproducible" means a persisted
report is self-describing: ``scoring_version`` and the ``weights`` actually
used are embedded in every report (and therefore folded into
``report_hash``), so a report is interpretable on its own even after this
formula changes again later, and two reports are only directly comparable
when their ``scoring_version`` matches. On the two cases Phase 10's own
tests already covered (a clean run; a single all-blocking dimension with no
other findings), this formula's output is numerically identical to the old
placeholder -- it is a strict refinement, not a behavior change for those
cases.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .scene_quality import classify

#: Quality report schema version.
QUALITY_REPORT_SCHEMA_VERSION = "1.0"

#: Tier 3 Phase 13: the scoring *formula*'s own version, independent of the
#: report schema -- bump this when the formula/weights change in a way that
#: would make an old and a new report's overall_score not directly
#: comparable, even if the schema shape itself is unchanged.
SCORING_VERSION = "1.0"

#: Cost of one finding at this severity, before normalizing by how many
#: findings the dimension actually produced. An all-blocking dimension
#: scores 0.0; an all-warning dimension scores 0.5.
BLOCKING_PENALTY = 1.0
WARNING_PENALTY = 0.5

#: Every dimension the target architecture names (SS16). "motion" had no
#: verifier at all before Tier 3 Phase 12 ("motion traces") added
#: verifier_motion; a dimension with no producer still reports zero
#: findings here rather than being silently absent from the report, which is
#: exactly what made that gap visible in the first place.
DIMENSIONS = (
    "semantic",
    "temporal",
    "spatial",
    "motion",
    "continuity",
    "pedagogical",
)

#: Tier 3 Phase 13: relative importance of each dimension in overall_score.
#: Equal by default -- see the module docstring for why. Callers with actual
#: evidence for a different priority order pass their own table to
#: build_quality_report/write_quality_report rather than editing this
#: default; a dimension omitted from a custom table is treated as
#: weight 0 (excluded from the average, not zeroed-and-averaged-in).
DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    dimension: 1.0 for dimension in DIMENSIONS
}

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
    # Bug fix: this was the one deterministic verifier with real geometric
    # detection (caption collision, crowding, out-of-bounds, title
    # collision -- see verifier_layout's own LAYOUT_BLOCKING_KINDS) and it
    # was absent here entirely. verifier_spatial only re-surfaces the
    # renderer's own audit record and is inert on the Manim path (no
    # audit is ever set there without observer_visual); verifier_layout is
    # the actual layout critic. Its omission meant the strongest layout
    # gate contributed nothing to overall_score even when it hard-gated
    # the run. Mapped to the same "spatial" dimension as verifier_spatial
    # -- both describe on-frame geometry, and quality_report's dimensions
    # are content-quality buckets, not one-verifier-per-bucket.
    "verifier_layout": "spatial",
    # Tier 3 Phase 12: the first real producer of the "motion" dimension --
    # it was declared in Phase 10 with zero producers until now.
    "verifier_motion": "motion",
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
    #: Tier 3 Phase 13: this dimension's own [0, 1] score. Set by
    #: build_quality_report after counting is complete -- see
    #: _dimension_score for the formula. 1.0 until then (the same "no
    #: evidence, no penalty" default the formula itself uses for an
    #: untouched dimension).
    score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "total": self.total,
            "blocking": self.blocking,
            "warning": self.warning,
            "passed": self.passed,
            "verifiers": list(self.verifiers),
            "score": self.score,
        }


@dataclass
class QualityReport:
    schema_version: str
    dimensions: dict[str, DimensionSummary]
    overall_score: float
    blocking_dimensions: list[str]
    unmapped_verifiers: list[str]
    #: Tier 3 Phase 13: the formula version and the weights actually used to
    #: compute overall_score, embedded so the report is self-describing --
    #: see the module docstring's "reproducible" paragraph.
    scoring_version: str = SCORING_VERSION
    weights: dict[str, float] = field(default_factory=dict)
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
            "scoring_version": self.scoring_version,
            "weights": dict(self.weights),
            "report_hash": self.report_hash,
        }

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("report_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Classification delegates to scene_quality.classify so this report and the
# repair controller's accept/reject decision can never disagree about what
# counts as a blocking finding.
#
# The previous predicates here required BOTH `status` and `severity`, which
# silently matched none of the many hand-written verifier dicts that omit
# `severity` (verifier_spatial's skip/warn/pass records, verifier_motion's
# skip/pass, verifier_temporal's skips, verifier_storyboard throughout).
# Those inflated `total` while contributing to no bucket, diluting every
# dimension score. Severity is now inferred from status when absent.

def _is_blocking(finding: Any) -> bool:
    return classify(finding) == "blocking"


def _is_warning(finding: Any) -> bool:
    return classify(finding) == "warning"


def _is_pass(finding: Any) -> bool:
    return classify(finding) == "pass"


def _dimension_score(summary: DimensionSummary) -> float:
    """One dimension's own [0, 1] score.

    A dimension with no findings at all is clean (1.0) -- absence of
    evidence is not evidence of failure, the same principle Phase 10's
    original placeholder already established for blocking_dimensions.
    Otherwise: 1.0 minus a findings-weighted penalty (BLOCKING_PENALTY per
    blocking finding, WARNING_PENALTY per warning), normalized by this
    dimension's own total finding count -- so a heavily-scrutinized
    dimension with one blocking finding among fifty passes isn't punished
    as hard as one with a single blocking finding and nothing else.
    """

    if summary.total == 0:
        return 1.0

    penalty = (
        summary.blocking * BLOCKING_PENALTY
        + summary.warning * WARNING_PENALTY
    ) / summary.total

    return max(0.0, min(1.0, 1.0 - penalty))


def _overall_score(
    dimensions: dict[str, DimensionSummary],
    weights: dict[str, float],
) -> float:
    """Weighted average of every dimension's own score.

    A dimension with weight <= 0 (including one simply absent from a custom
    ``weights`` table) is excluded from the average entirely, not zeroed and
    averaged in -- "don't count this dimension" and "this dimension scored
    zero" are different statements. No weighted dimensions at all is treated
    as a clean run (1.0), matching the empty-input convention the rest of
    this module already uses.
    """

    weighted_sum = 0.0
    total_weight = 0.0

    for name, summary in dimensions.items():
        weight = weights.get(name, 0.0)

        if weight <= 0:
            continue

        weighted_sum += weight * _dimension_score(summary)
        total_weight += weight

    return weighted_sum / total_weight if total_weight > 0 else 1.0


def build_quality_report(
    check_results: dict[str, list[dict[str, Any]]],
    *,
    weights: dict[str, float] | None = None,
) -> QualityReport:
    """Aggregate every verifier's ``check_results`` entry into one report,
    grouped by quality dimension. Pure function -- no ``SceneContext``, no
    file I/O (see :func:`write_quality_report` for the persisted form).

    ``weights`` overrides :data:`DEFAULT_DIMENSION_WEIGHTS` for this call
    only -- see the module docstring for why the default is equal weights.
    """

    weights = dict(weights) if weights is not None else dict(DEFAULT_DIMENSION_WEIGHTS)

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

    for summary in dimensions.values():
        summary.score = _dimension_score(summary)

    overall_score = _overall_score(dimensions, weights)

    report = QualityReport(
        schema_version=QUALITY_REPORT_SCHEMA_VERSION,
        dimensions=dimensions,
        overall_score=overall_score,
        blocking_dimensions=blocking_dimensions,
        unmapped_verifiers=sorted(set(unmapped)),
        scoring_version=SCORING_VERSION,
        weights=weights,
    )
    report.report_hash = report.compute_hash()

    return report


def write_quality_report(
    check_results: dict[str, list[dict[str, Any]]],
    project_dir: Path | None,
    *,
    weights: dict[str, float] | None = None,
) -> Path | None:
    """Persist ``build/harness/quality_report.json``. Never raises -- a bug
    in report generation must not mask the real success/failure of a
    harness run; returns ``None`` on any failure or when ``project_dir`` is
    unset."""

    if project_dir is None:
        return None

    try:
        report = build_quality_report(check_results, weights=weights)
        path = Path(project_dir) / "build" / "harness" / "quality_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
    except Exception:
        return None
