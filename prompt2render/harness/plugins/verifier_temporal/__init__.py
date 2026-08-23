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

    durations: list[float] = []

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

        if "dur" not in sentence:
            raise ValueError(
                f"alignment sentence {index} has no 'dur'."
            )

        duration = float(
            sentence["dur"]
        )

        if not math.isfinite(
            duration
        ) or duration < 0:
            raise ValueError(
                f"alignment sentence {index} has invalid "
                f"duration: {sentence['dur']!r}"
            )

        durations.append(
            duration
        )

    if not durations:
        raise ValueError(
            "alignment contains no sentence durations."
        )

    total = sum(
        durations
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