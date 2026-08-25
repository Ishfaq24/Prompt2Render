"""Deterministic visual grounding for rendered video -- Tier 3 Phase 11 (F3).

The audit's own framing (docs/ARCHITECTURE_AUDIT.md SS16-17): "today the
system can only answer 'did the Python execute?'. Answering 'did the
animation teach what was intended?' requires... observation of what actually
rendered" -- and "deterministic CV first, VLM only for semantic judgments".
This module is the CV-first half only; no LLM/VLM call anywhere in it.

It answers exactly one question per sampled frame: is there real rendered
content where the plan says something should be on screen? That is the
video-frame analogue of ``scenekit.ink_fraction()``, which already answers
the identical question for matplotlib stills by inspecting drawn artists
directly. A rendered Manim clip has no such in-memory artist model at verify
time -- only pixels -- so this module measures the same "share of the frame
that is not background" quantity via cv2 on an extracted frame instead.

Deliberately NOT object identity or motion tracking (a future phase's job,
named separately in the audit as "motion traces") -- a low ink-fraction
reading is reported as a finding for a human or the repair loop to interpret,
never resolved here.

Pure-ish module: no ``SceneContext``, no ``Plugin`` coupling (the harness
wiring lives in ``harness/plugins/observer_visual``), matching the split
``temporal_ir.py`` already established between typed/algorithmic core and
its ``SceneContext``-facing plugin. Unlike that module, real file I/O
(frame extraction, image decode) is inherent to what this one does, so it is
not literally I/O-free -- it reuses ``cfg.duration`` rather than
reimplementing an ffprobe wrapper, the same way ``visuals.py`` already does.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from . import cfg

if TYPE_CHECKING:
    from .harness.temporal_ir import SectionTiming


#: Manim's default scene background (pure black). No ``manim.cfg`` and no
#: ``background_color=`` appear anywhere in this repo (confirmed by search),
#: so the default is authoritative here the same way scenekit.py's own
#: ``BG = "#0d1117"`` is authoritative for the matplotlib stills path.
_BG_RGB = (0, 0, 0)

#: Per-channel distance from background before a pixel counts as "content".
#: Matches scenekit.ink_fraction()'s own threshold exactly (diff > 8),
#: chosen there to tolerate anti-aliasing without being fooled by it.
_TOLERANCE = 8

#: A frame whose ink_fraction() falls below this is reported as a warning.
#: Deliberately small: this phase's job is presence, not composition
#: quality, and a false positive here would be misleading to a repair loop.
DEFAULT_MIN_INK_FRACTION = 0.002

#: How many evenly-spaced samples to take when no TemporalIR is available
#: for a stem (temporal_ir is advisory -- see planner_temporal.py -- so this
#: fallback must never be a hard-failure mode).
DEFAULT_FALLBACK_COUNT = 5


def ink_fraction(
    frame_path: Path,
    *,
    tolerance: int = _TOLERANCE,
) -> float | None:
    """Share of one decoded frame that is not background.

    Returns ``None`` (never raises) when cv2 is unavailable or the frame
    fails to decode -- both are legitimate "cannot observe" outcomes that a
    caller degrades to ``status: skip`` for, not pipeline failures.
    """

    try:
        import cv2
    except ImportError:
        return None

    img = cv2.imread(str(frame_path))

    if img is None:
        return None

    # cv2 decodes BGR; a symmetric per-channel distance against a black
    # background is order-independent, so no channel reorder is needed.
    mask = np.zeros(img.shape[:2], dtype=bool)

    for channel, bg in enumerate(_BG_RGB):
        plane = img[:, :, channel]
        diff = np.maximum(plane, bg) - np.minimum(plane, bg)
        mask |= diff > tolerance

    return float(np.count_nonzero(mask)) / mask.size


def extract_frame(
    clip_path: Path,
    timestamp: float,
    out_path: Path,
) -> bool:
    """Extract one frame at ``timestamp`` via ffmpeg, tolerating failure.

    Same technique ``visuals.manim_scene`` already uses for its single
    final-frame preview -- extended here to an arbitrary timestamp via
    input-side ``-ss`` seeking.
    """

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{max(timestamp, 0.0):.3f}",
                "-i", str(clip_path),
                "-frames:v", "1", str(out_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False

    return out_path.exists()


def sample_points(
    section_timing: "SectionTiming | None",
    clip_duration: float,
    *,
    fallback_count: int = DEFAULT_FALLBACK_COUNT,
) -> list[tuple[str, float]]:
    """Timestamps worth sampling, paired with the state name each belongs to.

    When ``section_timing`` is available, one sample per non-degenerate
    state is taken midway through that state's ``wait`` window -- after its
    ``run_time`` animation has finished, before the next state's animation
    begins -- so the frame reflects the fully-settled state rather than a
    mid-transition one. States with zero ``run_time + wait`` (legitimately
    degenerate -- Manim itself rejects ``self.wait(0)``) produce no sample.

    Falls back to evenly-spaced samples across the clip when TemporalIR is
    unavailable for this stem, matching Phase 4/6's "never a new
    hard-failure mode" fallback discipline rather than skipping observation
    entirely.
    """

    if clip_duration <= 0:
        return []

    if section_timing is not None and section_timing.states:
        points: list[tuple[str, float]] = []
        elapsed = 0.0

        for state in section_timing.states:
            span = state.run_time + state.wait

            if span > 0:
                offset = elapsed + state.run_time + state.wait * 0.5
                timestamp = min(offset, clip_duration - 0.05)

                if timestamp > 0:
                    points.append((state.name, round(timestamp, 3)))

            elapsed += span

        if points:
            return points

    count = max(1, fallback_count)

    return [
        (f"sample_{i}", round(clip_duration * (i + 1) / (count + 1), 3))
        for i in range(count)
    ]


def observe_clip(
    clip_path: Path,
    section_timing: "SectionTiming | None",
    *,
    scratch_dir: Path,
    min_ink_fraction: float = DEFAULT_MIN_INK_FRACTION,
    fallback_count: int = DEFAULT_FALLBACK_COUNT,
) -> dict[str, Any]:
    """Sample a rendered clip and report deterministic content-presence.

    Returns a record shaped exactly like the stills path's existing
    SceneKit audit record (``status``/``warnings``/``stills``), with
    ``unit: "frames"`` added so a consumer formatting a message can tell the
    two apart. Warning strings are pre-formatted as
    ``"WARN [visual_absence] ..."`` -- the same
    ``LEVEL [kind] message`` shape ``verifier_spatial._RECORDED`` already
    parses -- so this record slots into ``RenderArtifact.audit`` and
    ``verifier_spatial`` needs no changes to consume it.

    Never raises: every failure mode (missing clip, unprobeable duration, no
    cv2, undecodable frames) degrades to ``status: skip``, the same
    "absence of evidence is not evidence of failure" posture
    ``verifier_spatial`` already applies when ``RenderArtifact.audit`` is
    ``None``.
    """

    def _skip(detail: str) -> dict[str, Any]:
        return {
            "status": "skip",
            "unit": "frames",
            "stills": 0,
            "warnings": [],
            "detail": detail,
        }

    if not clip_path.exists():
        return _skip("Rendered clip not found.")

    try:
        clip_duration = cfg.duration(clip_path)
    except Exception:
        return _skip("Could not determine clip duration.")

    points = sample_points(
        section_timing,
        clip_duration,
        fallback_count=fallback_count,
    )

    if not points:
        return _skip("No samplable timestamps for this clip.")

    scratch_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    measured = 0

    for name, timestamp in points:
        frame_path = scratch_dir / f"frame_{name}_{timestamp:.3f}.png"

        if not extract_frame(clip_path, timestamp, frame_path):
            continue

        fraction = ink_fraction(frame_path)

        if fraction is None:
            continue

        measured += 1

        if fraction < min_ink_fraction:
            warnings.append(
                f"WARN [visual_absence] state '{name}' at {timestamp:.2f}s: "
                f"{fraction:.4%} of the frame is non-background "
                "(expected visible content)"
            )

    if measured == 0:
        return _skip(
            "cv2/ffmpeg unavailable, or every sampled frame failed to "
            "extract/decode."
        )

    return {
        "status": "warn" if warnings else "pass",
        "unit": "frames",
        "stills": measured,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_FALLBACK_COUNT",
    "DEFAULT_MIN_INK_FRACTION",
    "extract_frame",
    "ink_fraction",
    "observe_clip",
    "sample_points",
]
