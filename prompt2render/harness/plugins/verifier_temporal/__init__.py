"""Deterministic temporal verifier for rendered Manim scenes.

This verifier compares the actual duration of each generated Manim MP4 with
the duration represented by the aligned narration.

It is intentionally independent of an LLM:

    aligned narration
        ↓
    target duration
        ↓
    rendered Manim MP4
        ↓
    ffprobe duration
        ↓
    temporal finding

A mismatch is routed as ``temporal_mismatch`` so the repair router can feed
precise timing diagnostics back into the scene generator.

Important:
* It verifies the rendered artifact, not source-code estimates.
* It does not assume that every render is Manim.
* Missing render artifacts are reported as ``skip`` rather than silently
  treated as PASS.
* FFprobe failures are reported as verifier failures rather than ignored.
* Target duration is derived only from the existing alignment artifact.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin
from ...temporal_ir import total_gap_seconds
from ...timing import narration_span, sentence_duration
from .... import align, cfg


DEFAULT_TOLERANCE_SECONDS = 1.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(
    value: Any,
    default: float,
) -> float:
    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default

    if not math.isfinite(result):
        return default

    return result


def _ffprobe_duration(
    clip_path: Path,
) -> float:
    """Return the raw container duration reported by FFprobe."""

    if shutil.which(
        "ffprobe"
    ) is None:
        raise RuntimeError(
            "ffprobe is not available on PATH."
        )

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    value = result.stdout.strip()

    if not value:
        raise RuntimeError(
            "ffprobe returned an empty duration."
        )

    duration = float(
        value
    )

    if not math.isfinite(
        duration
    ) or duration < 0:
        raise RuntimeError(
            f"ffprobe returned invalid duration: {value!r}"
        )

    return duration


def _target_duration(
    context: SceneContext,
    stem: str,
) -> float:
    """Calculate target duration from the authoritative alignment artifact."""

    data = align.load(
        context.project_dir,
        stem,
    )

    sentences = data.get(
        "sentences",
        [],
    )

    if not isinstance(
        sentences,
        list,
    ):
        raise ValueError(
            "alignment 'sentences' is not a list."
        )

    for index, sentence in enumerate(
        sentences
    ):
        if not isinstance(
            sentence,
            dict,
        ):
            raise ValueError(
                f"alignment sentence {index} is not an object."
            )

        # Both align formats (new start/end, old dur) are handled by
        # harness/timing.py. A sentence that yields neither is malformed.
        if sentence_duration(sentence) is None:
            raise ValueError(
                f"alignment sentence {index} has no usable "
                f"'dur'/'end'."
            )

    # The rendered clip must cover inter-sentence silence too, so the
    # target is the section's wall-clock SPAN, not the sum of speech
    # durations. Summing understated the target by the accumulated
    # silence and disagreed with verifier_execution, which already used
    # the span. See harness/timing.py.
    total = narration_span(
        sentences
    )

    if total <= 0:
        raise ValueError(
            "alignment target duration is zero."
        )

    return total


def _finding(
    *,
    stem: str,
    message: str,
    severity: Severity,
    finding_type: str,
    subtype: str | None = None,
) -> dict[str, Any]:
    finding = Finding(
        finding_id=next_finding_id(
            "time"
        ),
        scene_id=stem,
        category=Category.TEMPORAL,
        severity=severity,
        message=message,
    ).as_check_result()

    finding["finding_type"] = (
        finding_type
    )

    if subtype:
        finding["mismatch_subtype"] = (
            subtype
        )

    return finding


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class VerifierTemporalPlugin(Plugin):
    """Verify rendered Manim duration against aligned narration duration."""

    name = "verifier_temporal"

    def declare_dependencies(self) -> list[str]:
        return [
            "render_artifacts",
            "code_artifacts",
            "scene_plan",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        findings: list[
            dict[str, Any]
        ] = []

        tolerance = _safe_float(
            self.config.get(
                "tolerance_seconds",
                DEFAULT_TOLERANCE_SECONDS,
            ),
            DEFAULT_TOLERANCE_SECONDS,
        )

        tolerance = max(
            0.0,
            tolerance,
        )

        gate = self.is_gate()

        # Prefer the configured/rendered artifact location if available.
        # The fallback path retains compatibility with the existing Manim
        # renderer layout.
        for entry in context.scene_plan:

            artifact = (
                context.render_artifacts.get(
                    entry.stem
                )
            )

            clip_path = None

            if artifact is not None:
                candidate = getattr(
                    artifact,
                    "clip",
                    None,
                )

                if candidate:
                    candidate = Path(
                        candidate
                    )

                    if candidate.exists():
                        clip_path = candidate

            if clip_path is None:
                candidate = (
                    context.project_dir
                    / "build"
                    / "manim"
                    / "videos"
                    / f"scene_{entry.stem}"
                    / "1080p30"
                    / f"Scene{entry.stem}.mp4"
                )

                if candidate.exists():
                    clip_path = candidate

            # ----------------------------------------------------------
            # No Manim clip
            # ----------------------------------------------------------

            if clip_path is None:
                findings.append(
                    {
                        "status": "skip",
                        "stem": entry.stem,
                        "finding_type": (
                            "temporal_verification_unavailable"
                        ),
                        "category": (
                            Category.TEMPORAL.value
                        ),
                        "detail": (
                            "No rendered Manim MP4 was found "
                            "for this scene."
                        ),
                    }
                )

                continue

            # ----------------------------------------------------------
            # Target narration duration
            # ----------------------------------------------------------

            try:
                target_duration = _target_duration(
                    context,
                    entry.stem,
                )

            except Exception as exc:
                findings.append(
                    {
                        "status": "skip",
                        "stem": entry.stem,
                        "finding_type": (
                            "temporal_target_unavailable"
                        ),
                        "category": (
                            Category.TEMPORAL.value
                        ),
                        "detail": (
                            "Could not derive narration "
                            f"duration: {exc}"
                        ),
                    }
                )

                continue

            # ----------------------------------------------------------
            # Actual rendered duration
            # ----------------------------------------------------------

            try:
                actual_duration = _ffprobe_duration(
                    clip_path
                )

            except Exception as exc:
                cfg.warn(
                    f"Failed to measure duration of "
                    f"{clip_path}: {exc}"
                )

                findings.append(
                    _finding(
                        stem=entry.stem,
                        severity=(
                            Severity.BLOCKING
                            if gate
                            else Severity.WARNING
                        ),
                        finding_type=(
                            "temporal_measurement_failure"
                        ),
                        message=(
                            "Temporal verification could not measure "
                            f"the rendered clip: {exc}"
                        ),
                    )
                )

                continue

            # ----------------------------------------------------------
            # Compare
            # ----------------------------------------------------------

            diff = (
                actual_duration
                - target_duration
            )

            absolute_diff = abs(
                diff
            )

            code_artifact = context.code_artifacts.get(entry.stem)
            # --- Precise cue-sync check when they are necessary ---
            # When the narration has >1 sentence and there are real gaps
            # between sentences, the generated code MUST contain self.wait()
            # calls whose total approximates the sum of inter-sentence gaps.
            # This is the per-cue "when they are necessary" rule — a single-
            # sentence section needs no extra waits, but a multi-sentence
            # section with pauses does.
            has_waits = False
            sum_waits = 0.0
            waits: list[float] = []
            if code_artifact and code_artifact.path and code_artifact.path.exists():
                try:
                    import re as _re
                    code_txt = code_artifact.path.read_text(encoding="utf-8")
                    has_waits = "self.wait" in code_txt
                    for m in _re.finditer(r"self\.wait\s*\(\s*([0-9]*\.?[0-9]+)", code_txt):
                        try:
                            v = float(m.group(1))
                            if 0 <= v < 100:
                                waits.append(v)
                        except Exception:
                            continue
                    sum_waits = sum(waits) if waits else 0.0
                except Exception:
                    has_waits = False
                    sum_waits = 0.0

            # Compute inter-sentence gap sum from authoritative alignment.
            # Single source of truth (Tier 2 Phase 5, harness/temporal_ir.py)
            # -- this used to be a second, independent inline computation of
            # exactly the "where are the narration timing boundaries"
            # quantity renderer_manim's motion compiler also derives, the
            # same class of drift Phase 0.5 (F7) fixed once already for
            # plain section duration.
            gap_sum = 0.0
            num_sentences = 0
            try:
                data = align.load(context.project_dir, entry.stem)
                sents = data.get("sentences", []) if isinstance(data, dict) else []
                if isinstance(sents, list):
                    num_sentences = len(sents)
                    gap_sum = total_gap_seconds(sents)
            except Exception:
                num_sentences = 0

            # When there are multiple sentences with real pauses, require waits
            if num_sentences > 1 and gap_sum > 0.35:
                if not has_waits:
                    findings.append(
                        _finding(
                            stem=entry.stem,
                            severity=Severity.BLOCKING if gate else Severity.WARNING,
                            finding_type="temporal_mismatch",
                            subtype="missing_cues",
                            message=(
                                "Animation timing mismatch: "
                                f"This section has {num_sentences} sentences with {gap_sum:.2f}s of inter-sentence gaps, "
                                "but the generated code contains no self.wait() calls. "
                                "You MUST use self.wait(gap) between sentence animations so each visual starts exactly "
                                "at its narration cue (see CUE MAP). Do NOT play animations back-to-back."
                            ),
                        )
                    )
                    continue
                # Allow 40% tolerance on gap sum — LLM may distribute waits slightly differently
                if sum_waits + 0.15 < gap_sum * 0.6:
                    findings.append(
                        _finding(
                            stem=entry.stem,
                            severity=Severity.BLOCKING if gate else Severity.WARNING,
                            finding_type="temporal_mismatch",
                            subtype="missing_cues",
                            message=(
                                "Animation cue-sync mismatch: "
                                f"narration gaps sum to {gap_sum:.2f}s but code waits sum to {sum_waits:.2f}s "
                                f"(waits found: {waits}). Adjust self.wait() values to match the CUE MAP gaps "
                                f"so each animation starts at its exact narration timestamp. Gap sum should be within ~40% of {gap_sum:.2f}s."
                            ),
                        )
                    )
                    continue
            elif not has_waits and target_duration > 3.0 and num_sentences > 1 and gap_sum <= 0.35:
                # No gaps but multi-sentence: requiring at least one wait is too strict if sentences are back-to-back.
                # Only warn if there are no waits AND total duration still mismatches (handled below).
                pass
            elif not has_waits and target_duration > 3.0 and num_sentences <= 1:
                # Single-sentence sections legitimately need no cues.
                pass

            if absolute_diff > tolerance:

                direction = (
                    "too long"
                    if diff > 0
                    else "too short"
                )

                message = (
                    "Animation timing mismatch: "
                    f"narration requires {target_duration:.2f}s, "
                    f"but the rendered animation is "
                    f"{actual_duration:.2f}s "
                    f"({absolute_diff:.2f}s {direction}). "
                    "Adjust self.play(run_time=...) and/or "
                    "self.wait(...) so the rendered scene duration "
                    f"matches the narration target within "
                    f"{tolerance:.2f}s."
                )

                findings.append(
                    _finding(
                        stem=entry.stem,
                        severity=(
                            Severity.BLOCKING
                            if gate
                            else Severity.WARNING
                        ),
                        finding_type=(
                            "temporal_mismatch"
                        ),
                        subtype=(
                            "too_long"
                            if diff > 0
                            else "too_short"
                        ),
                        message=message,
                    )
                )

            else:
                findings.append(
                    {
                        "status": "pass",
                        "stem": entry.stem,
                        "finding_type": (
                            "temporal_match"
                        ),
                        "category": (
                            Category.TEMPORAL.value
                        ),
                        "severity": (
                            Severity.INFO.value
                        ),
                        "detail": (
                            f"Animation duration "
                            f"{actual_duration:.2f}s matches "
                            f"target {target_duration:.2f}s "
                            f"within ±{tolerance:.2f}s."
                        ),
                        "actual_duration": (
                            actual_duration
                        ),
                        "target_duration": (
                            target_duration
                        ),
                        "difference": diff,
                    }
                )

        context.check_results[
            self.name
        ] = findings

        return context

    def _default_gate(self) -> bool:
        """Temporal mismatch is a hard gate by default."""

        return True