"""Deterministic per-scene quality evidence and comparison.

This is the measuring instrument the repair controller uses to answer the
only question that matters when deciding whether to keep an LLM's repair:

    is the candidate scene at least as good as the one we already accepted?

Design constraints, in order of importance:

1. **Built only from evidence the pipeline already produces.** No invented
   visual scoring, no new LLM calls, no new heuristics about what "good"
   looks like. Everything here is derived from existing ``check_results``
   entries and from numbers the observers already recorded on
   ``RenderArtifact``.

2. **Deterministic.** Same inputs, same verdict, every time. The comparison
   is a documented lexicographic ordering, not a weighted score with tuned
   magic numbers -- a research system needs its accept/reject decisions to
   be explainable and reproducible, not merely plausible.

3. **Conservative under uncertainty.** When the evidence cannot show the
   candidate is at least as good, the verdict is ``INSUFFICIENT_EVIDENCE``
   and the caller preserves the already-accepted scene. Preferring the
   known-acceptable artifact over an unproven replacement is the whole
   point; "the verifier that complained now passes" is not evidence that
   nothing else broke.

Known limitation, recorded honestly: the pipeline computes far richer
numeric signal than it exports. ``scenekit.audit`` measures overlap areas
in px², element counts and ink fraction; ``visual_observe.observe_clip``
measures per-frame ink fraction -- and all of it is formatted into prose
strings and discarded. Only two verifiers export machine-readable numbers
(``verifier_temporal``'s pass path, and ``verifier_pedagogy``'s score),
plus the per-state ``delta`` floats that survive on
``RenderArtifact.motion``. This module uses exactly what is available and
deliberately does not re-plumb those other call sites; widening the
evidence surface is worthwhile but is a separate change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .context import SceneContext
from .lineage import is_scene_stem


class Verdict(str, Enum):
    """Result of comparing a candidate scene against the accepted one."""

    BETTER = "better"
    EQUAL = "equal"
    WORSE = "worse"

    #: The evidence cannot establish that the candidate is at least as good.
    #: Treated by the acceptance rule as *not* acceptable.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def classify(finding: Any) -> str:
    """Bucket one finding into ``blocking``/``warning``/``pass``/``skip``.

    Severity is *inferred from status* when the dict omits it. This matters:
    many verifiers hand-write plain dicts with no ``severity`` key at all
    (verifier_spatial's skip/warn/pass records, verifier_motion's skip/pass,
    verifier_temporal's skips, verifier_storyboard throughout). The report
    layer's stricter predicates require both keys and silently match none of
    those, which would make a candidate look artificially clean here.
    Status is the one field every producer sets.
    """

    if not isinstance(finding, dict):
        return "skip"

    status = str(finding.get("status", "")).strip().lower()
    severity = str(finding.get("severity", "")).strip().upper()

    if status == "pass":
        return "pass"

    if status == "skip":
        return "skip"

    if status == "warn":
        return "warning"

    if status == "fail":
        # An explicit WARNING severity downgrades a "fail" status -- that
        # combination is how advisory verifiers report a real problem
        # without claiming it should block.
        return "warning" if severity == "WARNING" else "blocking"

    # Anything else (including the router's historical "resolved"/
    # "open_defect" rewrites) carries no usable verdict.
    return "skip"


def _scene_findings(
    context: SceneContext,
    stem: str,
) -> list[dict[str, Any]]:
    """Every finding recorded against one scene, across all verifiers."""

    target = str(stem)
    found: list[dict[str, Any]] = []

    for results in context.check_results.values():
        if not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue

            owner = result.get("stem") or result.get("scene_id")

            if is_scene_stem(owner) and str(owner) == target:
                found.append(result)

    return found


def _motion_min_delta(
    context: SceneContext,
    stem: str,
) -> float | None:
    """Smallest observed per-state frame delta, or ``None``.

    Recovered from ``RenderArtifact.motion`` rather than from findings --
    verifier_motion formats the float into its message and drops it, but
    ``observe_motion`` preserves the raw value on the artifact. Higher is
    better (more of the frame actually changed while a motion op ran).
    """

    artifact = context.render_artifacts.get(str(stem))
    record = getattr(artifact, "motion", None)

    if not isinstance(record, dict) or record.get("status") != "ok":
        return None

    deltas = [
        float(trace["delta"])
        for trace in (record.get("traces") or [])
        if isinstance(trace, dict)
        and isinstance(trace.get("delta"), (int, float))
    ]

    return min(deltas) if deltas else None


@dataclass
class SceneQuality:
    """Deterministic quality evidence for one scene at one revision."""

    stem: str
    revision: int = 0

    blocking: int = 0
    warnings: int = 0
    passes: int = 0
    skips: int = 0

    #: ``{finding_type: count}`` restricted to blocking findings -- this is
    #: what detects "the repair fixed X but introduced Y".
    blocking_types: dict[str, int] = field(default_factory=dict)

    #: All finding types seen, for the decision log.
    finding_types: dict[str, int] = field(default_factory=dict)

    #: Per-category blocking counts for dimension-specific scoring.
    #: Keys are uppercased categories: STRUCTURAL, LAYOUT, SEMANTIC, PEDAGOGY, TEMPORAL, SPATIAL etc.
    category_blocking: dict[str, int] = field(default_factory=dict)

    #: Per-category warning counts.
    category_warnings: dict[str, int] = field(default_factory=dict)

    #: |actual - target| seconds from verifier_temporal's pass path.
    #: Lower is better. ``None`` when unavailable.
    temporal_difference: float | None = None

    #: Smallest per-state motion delta. Higher is better. ``None`` when
    #: unavailable.
    motion_min_delta: float | None = None

    @property
    def layout_score(self) -> int:
        """Layout dimension: higher is better. 100 minus weighted blocking."""
        return max(0, 100 - self.category_blocking.get("LAYOUT", 0) * 20 - self.category_warnings.get("LAYOUT", 0) * 5)

    @property
    def semantic_score(self) -> int:
        return max(0, 100 - self.category_blocking.get("SEMANTIC", 0) * 20 - self.category_warnings.get("SEMANTIC", 0) * 5)

    @property
    def structural_score(self) -> int:
        return max(0, 100 - self.category_blocking.get("STRUCTURAL", 0) * 20)

    @property
    def pedagogical_score(self) -> int:
        return max(0, 100 - self.category_blocking.get("PEDAGOGY", 0) * 20)

    @property
    def temporal_score(self) -> int:
        return max(0, 100 - self.category_blocking.get("TEMPORAL", 0) * 20)

    @property
    def has_evidence(self) -> bool:
        """Whether any verifier actually reported on this scene."""

        return (
            self.blocking + self.warnings + self.passes + self.skips
        ) > 0

    @property
    def total(self) -> int:
        return self.blocking + self.warnings + self.passes + self.skips

    def to_dict(self) -> dict[str, Any]:
        return {
            "stem": self.stem,
            "revision": self.revision,
            "blocking": self.blocking,
            "warnings": self.warnings,
            "passes": self.passes,
            "skips": self.skips,
            "blocking_types": dict(self.blocking_types),
            "finding_types": dict(self.finding_types),
            "category_blocking": dict(self.category_blocking),
            "category_warnings": dict(self.category_warnings),
            "structural_score": self.structural_score,
            "layout_score": self.layout_score,
            "semantic_score": self.semantic_score,
            "pedagogical_score": self.pedagogical_score,
            "temporal_score": self.temporal_score,
            "temporal_difference": self.temporal_difference,
            "motion_min_delta": self.motion_min_delta,
        }

    @staticmethod
    def collect(
        context: SceneContext,
        stem: str,
    ) -> "SceneQuality":
        """Gather all currently-recorded evidence for one scene."""

        from .lineage import current_revision

        quality = SceneQuality(
            stem=str(stem),
            revision=current_revision(context, stem),
        )

        for finding in _scene_findings(context, stem):
            bucket = classify(finding)

            finding_type = str(
                finding.get("finding_type", "")
            ).strip() or "unspecified"

            # Dimension-specific category for scoring
            raw_cat = str(finding.get("category") or finding.get("Category") or "").strip().upper()
            # Normalize legacy SPATIAL -> LAYOUT for scoring (same geometric dimension)
            if raw_cat == "SPATIAL":
                raw_cat = "LAYOUT"
            if raw_cat == "PEDAGOGICAL":
                raw_cat = "PEDAGOGY"

            quality.finding_types[finding_type] = (
                quality.finding_types.get(finding_type, 0) + 1
            )

            if bucket == "blocking":
                quality.blocking += 1
                quality.blocking_types[finding_type] = (
                    quality.blocking_types.get(finding_type, 0) + 1
                )
                if raw_cat:
                    quality.category_blocking[raw_cat] = quality.category_blocking.get(raw_cat, 0) + 1
            elif bucket == "warning":
                quality.warnings += 1
                if raw_cat:
                    quality.category_warnings[raw_cat] = quality.category_warnings.get(raw_cat, 0) + 1
            elif bucket == "pass":
                quality.passes += 1
            else:
                quality.skips += 1

            # verifier_temporal is the only verifier exporting a
            # machine-readable timing delta, and only on its pass path.
            difference = finding.get("difference")

            if isinstance(difference, (int, float)):
                value = abs(float(difference))

                if (
                    quality.temporal_difference is None
                    or value < quality.temporal_difference
                ):
                    quality.temporal_difference = value

        quality.motion_min_delta = _motion_min_delta(context, stem)

        return quality


@dataclass
class Comparison:
    """A fully-explained verdict, suitable for the decision log."""

    verdict: Verdict
    reason: str
    accepted: dict[str, Any]
    candidate: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "accepted": self.accepted,
            "candidate": self.candidate,
        }


#: Numeric tie-breaks are only trusted beyond this much difference --
#: below it the two scenes are treated as indistinguishable rather than
#: letting float noise decide whether an LLM rewrite is kept.
NUMERIC_EPSILON = 1e-3


def compare(
    accepted: SceneQuality,
    candidate: SceneQuality,
) -> Comparison:
    """Compare two scene revisions deterministically.

    Lexicographic, most-decisive first:

    1. **Blocking findings** -- fewer wins. A blocking finding is a real
       defect; no amount of improvement elsewhere compensates.
    2. **Warnings** -- fewer wins.
    3. **Skips** -- fewer wins. A skip means a verifier could not form an
       opinion, so more skips is strictly less assurance.
    4. **Numeric tie-breaks**, only when the counts are identical:
       tighter narration timing, then more observed motion.
    5. Otherwise the two are ``EQUAL``.

    ``INSUFFICIENT_EVIDENCE`` is returned when the candidate produced no
    findings at all -- an unverified scene is never treated as an
    improvement on a verified one, regardless of how the counts compare.
    """

    payload_accepted = accepted.to_dict()
    payload_candidate = candidate.to_dict()

    def result(verdict: Verdict, reason: str) -> Comparison:
        return Comparison(
            verdict=verdict,
            reason=reason,
            accepted=payload_accepted,
            candidate=payload_candidate,
        )

    if not candidate.has_evidence:
        return result(
            Verdict.INSUFFICIENT_EVIDENCE,
            "candidate produced no verifier findings; cannot establish it "
            "is at least as good as the accepted scene",
        )

    if not accepted.has_evidence:
        # Nothing to lose by comparison, but nothing proven either. Only
        # accept when the candidate is itself clean.
        if candidate.blocking == 0:
            return result(
                Verdict.BETTER,
                "no prior evidence for the accepted scene; candidate has "
                "no blocking findings",
            )

        return result(
            Verdict.WORSE,
            f"no prior evidence for the accepted scene and the candidate "
            f"has {candidate.blocking} blocking finding(s)",
        )

    # 1. Blocking findings.
    if candidate.blocking != accepted.blocking:
        better = candidate.blocking < accepted.blocking

        return result(
            Verdict.BETTER if better else Verdict.WORSE,
            f"blocking findings {accepted.blocking} -> {candidate.blocking}",
        )

    # 2. Warnings.
    if candidate.warnings != accepted.warnings:
        better = candidate.warnings < accepted.warnings

        return result(
            Verdict.BETTER if better else Verdict.WORSE,
            f"warnings {accepted.warnings} -> {candidate.warnings} "
            f"(blocking unchanged at {accepted.blocking})",
        )

    # 3. Skips -- less verification coverage is less assurance.
    if candidate.skips != accepted.skips:
        better = candidate.skips < accepted.skips

        return result(
            Verdict.BETTER if better else Verdict.WORSE,
            f"unverifiable (skip) findings {accepted.skips} -> "
            f"{candidate.skips}",
        )

    # 4. Numeric tie-breaks.
    if (
        accepted.temporal_difference is not None
        and candidate.temporal_difference is not None
    ):
        delta = candidate.temporal_difference - accepted.temporal_difference

        if abs(delta) > NUMERIC_EPSILON:
            return result(
                Verdict.BETTER if delta < 0 else Verdict.WORSE,
                f"narration timing difference "
                f"{accepted.temporal_difference:.3f}s -> "
                f"{candidate.temporal_difference:.3f}s",
            )

    if (
        accepted.motion_min_delta is not None
        and candidate.motion_min_delta is not None
    ):
        delta = candidate.motion_min_delta - accepted.motion_min_delta

        if abs(delta) > NUMERIC_EPSILON:
            return result(
                Verdict.BETTER if delta > 0 else Verdict.WORSE,
                f"minimum observed motion "
                f"{accepted.motion_min_delta:.4f} -> "
                f"{candidate.motion_min_delta:.4f}",
            )

    return result(
        Verdict.EQUAL,
        f"indistinguishable on available evidence "
        f"({accepted.blocking} blocking, {accepted.warnings} warning, "
        f"{accepted.skips} skip)",
    )


def new_blocking_types(
    accepted: SceneQuality,
    candidate: SceneQuality,
) -> dict[str, int]:
    """Blocking finding types the candidate introduced.

    This is the check that stops a repair from trading one defect for
    another -- fixing a layout collision by breaking animation continuity
    leaves the blocking *count* unchanged while making the scene worse in a
    way a pure count cannot see.
    """

    introduced: dict[str, int] = {}

    for finding_type, count in candidate.blocking_types.items():
        before = accepted.blocking_types.get(finding_type, 0)

        if count > before:
            introduced[finding_type] = count - before

    return introduced


def _resolved_blocking_types(
    accepted: SceneQuality,
    candidate: SceneQuality,
) -> tuple[str, ...]:
    """Blocking finding types present in the baseline but gone (or reduced)
    in the candidate -- the counterpart to :func:`new_blocking_types`."""

    resolved = [
        finding_type
        for finding_type, count in accepted.blocking_types.items()
        if candidate.blocking_types.get(finding_type, 0) < count
    ]

    return tuple(sorted(resolved))


def _unchanged_blocking_types(
    accepted: SceneQuality,
    candidate: SceneQuality,
) -> tuple[str, ...]:
    """Blocking finding types present in both baseline and candidate at the
    same or a higher count -- present before, still present after."""

    unchanged = [
        finding_type
        for finding_type, count in accepted.blocking_types.items()
        if count > 0 and candidate.blocking_types.get(finding_type, 0) >= count
    ]

    return tuple(sorted(unchanged))


@dataclass(frozen=True)
class FindingDiff:
    """The explainable difference between a baseline and a candidate.

    This is what the brief's "why was the candidate accepted or rejected"
    actually needs -- ``new_blocking_types``/``compare`` already produce a
    verdict, but not the plain-English "what got fixed, what got broken,
    what didn't move" a decision log reader (human or research script)
    wants without re-deriving it from two ``blocking_types`` dicts by hand.
    """

    resolved: tuple[str, ...]
    introduced: tuple[str, ...]
    unchanged: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "resolved": list(self.resolved),
            "introduced": list(self.introduced),
            "unchanged": list(self.unchanged),
        }


def diff_findings(
    accepted: SceneQuality,
    candidate: SceneQuality,
) -> FindingDiff:
    """Classify every blocking finding type as resolved/introduced/unchanged.

    Restricted to blocking types deliberately -- warnings and passes churn
    too much run-to-run (a verifier flipping ``skip``<->``pass`` on
    unrelated evidence availability is not a "finding" in the sense the
    brief means) to be useful signal in a decision log.
    """

    introduced = tuple(sorted(new_blocking_types(accepted, candidate)))

    return FindingDiff(
        resolved=_resolved_blocking_types(accepted, candidate),
        introduced=introduced,
        unchanged=_unchanged_blocking_types(accepted, candidate),
    )


__all__ = [
    "NUMERIC_EPSILON",
    "Comparison",
    "FindingDiff",
    "SceneQuality",
    "Verdict",
    "classify",
    "compare",
    "diff_findings",
    "new_blocking_types",
]
