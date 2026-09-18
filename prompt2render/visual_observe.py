"""Deterministic visual grounding for rendered video -- Tier 3 Phases 11-12
(F3, closed-loop visual grounding; motion traces).

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

Phase 11's ``ink_fraction``/``observe_clip`` answer presence only ("is
something on screen"). Phase 12 adds ``frame_delta``/``observe_motion``,
which answer a distinct question: did the screen actually change while a
state's motion op was supposed to be executing? quality_report.py's own
"motion" quality dimension has had zero producers since Phase 10 shipped it
-- this is that producer. Still deterministic CV only (frame differencing),
still no object identity/tracking (true per-object motion trails remain out
of scope -- this only measures aggregate pixel change over a state's
run_time window, not *which* object moved).

Unlike Phase 11's ``observe_clip`` (which embeds its own pass/warn judgment
so its output can be parsed unmodified by ``verifier_spatial``'s existing
text parser), ``observe_motion`` deliberately records raw per-state deltas
only and leaves the warn/pass judgment to ``verifier_motion`` -- there is no
legacy parser to reuse here, so the cleaner "observer observes, verifier
decides" split applies without compromise.

Pure-ish module: no ``SceneContext``, no ``Plugin`` coupling (the harness
wiring lives in ``harness/plugins/observer_visual``), matching the split
``temporal_ir.py`` already established between typed/algorithmic core and
its ``SceneContext``-facing plugin. Unlike that module, real file I/O
(frame extraction, image decode) is inherent to what this one does, so it is
not literally I/O-free -- it reuses ``cfg.duration`` rather than
reimplementing an ffprobe wrapper, the same way ``visuals.py`` already does.
"""

from __future__ import annotations

import re
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

#: A state whose frame-to-frame change over its run_time window falls below
#: this is a candidate "nothing visibly moved" trace. Deliberately small,
#: same reasoning as DEFAULT_MIN_INK_FRACTION -- verifier_motion additionally
#: suppresses this for hold-flagged states, where zero change is correct.
DEFAULT_MIN_MOTION_DELTA = 0.001

#: Seconds trimmed off each end of a state's run_time window before
#: sampling its start/end frames, so the "start" sample doesn't land on the
#: previous state's still-frozen last frame and the "end" sample doesn't
#: land on the next state's first frame.
_RUN_TIME_MARGIN = 0.1


def _load_image(frame_path: Path) -> np.ndarray | None:
    """Load an image array using cv2 if available, or Pillow as fallback."""
    try:
        import cv2
        img = cv2.imread(str(frame_path))
        if img is not None:
            return img
    except Exception:
        pass

    try:
        from PIL import Image
        with Image.open(frame_path) as pil_img:
            return np.array(pil_img.convert("RGB"))
    except Exception:
        return None


def ink_fraction(
    frame_path: Path,
    *,
    tolerance: int = _TOLERANCE,
) -> float | None:
    """Share of one decoded frame that is not background.

    Returns ``None`` (never raises) when neither cv2 nor Pillow is available
    or the frame fails to decode.
    """
    img = _load_image(frame_path)

    if img is None:
        return None

    # A symmetric per-channel distance against a black background is order-independent
    mask = np.zeros(img.shape[:2], dtype=bool)

    for channel, bg in enumerate(_BG_RGB):
        plane = img[:, :, channel]
        diff = np.maximum(plane, bg) - np.minimum(plane, bg)
        mask |= diff > tolerance

    return float(np.count_nonzero(mask)) / mask.size


def frame_delta(
    frame_a: Path,
    frame_b: Path,
    *,
    tolerance: int = _TOLERANCE,
) -> float | None:
    """Share of pixels that changed between two decoded frames.

    Same per-channel-distance arithmetic as ``ink_fraction``, but between two
    frames instead of one frame and a fixed background -- this is what makes
    it a *motion* signal rather than a presence signal.
    """
    img_a = _load_image(frame_a)
    img_b = _load_image(frame_b)

    if img_a is None or img_b is None:
        return None

    if img_a.shape != img_b.shape:
        return None

    mask = np.zeros(img_a.shape[:2], dtype=bool)

    for channel in range(img_a.shape[2]):
        plane_a = img_a[:, :, channel]
        plane_b = img_b[:, :, channel]
        diff = np.maximum(plane_a, plane_b) - np.minimum(plane_a, plane_b)
        mask |= diff > tolerance

    return float(np.count_nonzero(mask)) / mask.size


# Layout collision thresholds
COLLISION_IOU_THRESHOLD = 0.15
COLLISION_IOM_THRESHOLD = 0.30


def detect_frame_spatial_collisions(
    frame_path: Path,
    *,
    state_name: str = "",
    timestamp: float = 0.0,
    tolerance: int = _TOLERANCE,
    iou_threshold: float = COLLISION_IOU_THRESHOLD,
    iom_threshold: float = COLLISION_IOM_THRESHOLD,
) -> list[str]:
    """Inspect rendered frame for geometric overlaps, margin overflow, and caption collisions."""
    try:
        import cv2
    except ImportError:
        return []

    img = cv2.imread(str(frame_path))
    if img is None:
        return []

    h_img, w_img = img.shape[:2]
    if h_img < 100 or w_img < 100:
        return []

    mask = np.zeros((h_img, w_img), dtype=np.uint8)
    for channel, bg in enumerate(_BG_RGB):
        plane = img[:, :, channel]
        diff = np.maximum(plane, bg) - np.minimum(plane, bg)
        mask[diff > tolerance] = 255

    # Find external contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bboxes: list[tuple[int, int, int, int]] = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < 60:  # Ignore tiny noise artifacts
            continue
        x, y, w, h = cv2.boundingRect(c)
        bboxes.append((x, y, w, h))

    warnings: list[str] = []
    tag = f"state '{state_name}' at {timestamp:.2f}s" if state_name else f"at {timestamp:.2f}s"

    # 1. Offframe check (safe margin 12px)
    margin = 12
    for x, y, w, h in bboxes:
        if (x < margin or y < margin or (x + w) > (w_img - margin) or (y + h) > (h_img - margin)) and (w > 20 and h > 20):
            warnings.append(
                f"WARN [offframe] {tag}: element at ({x},{y},{w},{h}) extends past safe frame margins"
            )
            break

    # 2. Pairwise IoU and IoM spatial collision check (outside caption band)
    caption_y_min = int(0.80 * h_img)
    main_boxes = [b for b in bboxes if b[1] + b[3] <= caption_y_min]
    for i in range(len(main_boxes)):
        for j in range(i + 1, len(main_boxes)):
            b1, b2 = main_boxes[i], main_boxes[j]
            xi = max(b1[0], b2[0])
            yi = max(b1[1], b2[1])
            xf = min(b1[0] + b1[2], b2[0] + b2[2])
            yf = min(b1[1] + b1[3], b2[1] + b2[3])
            if xf > xi and yf > yi:
                inter_area = (xf - xi) * (yf - yi)
                area1 = b1[2] * b1[3]
                area2 = b2[2] * b2[3]
                min_area = min(area1, area2)
                union_area = area1 + area2 - inter_area
                iou = inter_area / union_area if union_area > 0 else 0.0
                iom = inter_area / min_area if min_area > 0 else 0.0

                # If one box is an intentional container around another (>90% containment and >2.5x size)
                is_container = (iom > 0.90) and (max(area1, area2) / max(min_area, 1) > 2.5)
                if not is_container:
                    if iou >= iou_threshold or iom >= iom_threshold:
                        warnings.append(
                            f"WARN [overlap] {tag}: spatial overlap detected between elements at "
                            f"({b1[0]},{b1[1]},{b1[2]},{b1[3]}) and ({b2[0]},{b2[1]},{b2[2]},{b2[3]}) "
                            f"(IoU={iou:.2f}, IoM={iom:.2f})"
                        )
                        break
        if warnings and "overlap" in warnings[-1]:
            break

    # 3. Caption collision check (caption band y in [0.80 * h_img, 0.98 * h_img])
    caption_boxes = [b for b in bboxes if b[1] + b[3] > caption_y_min and b[1] < int(0.98 * h_img)]
    if len(caption_boxes) > 1:
        has_vertical_stack = False
        for i in range(len(caption_boxes)):
            for j in range(i + 1, len(caption_boxes)):
                b1, b2 = caption_boxes[i], caption_boxes[j]
                if abs(b1[1] - b2[1]) > 15 or (min(b1[0] + b1[2], b2[0] + b2[2]) - max(b1[0], b2[0]) > 10):
                    has_vertical_stack = True
                    break
            if has_vertical_stack:
                break
        if has_vertical_stack:
            warnings.append(
                f"WARN [caption_collision] {tag}: multiple elements colliding in caption band"
            )
    elif len(caption_boxes) == 1:
        b = caption_boxes[0]
        if b[3] > int(0.08 * h_img):
            warnings.append(
                f"WARN [caption_collision] {tag}: caption height ({b[3]}px) exceeds safe single-line caption band height"
            )

    return warnings


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

                # Do not sample during the entrance animation itself:
                # wait*0.5 ensures we are well into the settled hold
                # period after run_time has finished. If wait is zero
                # (degenerate, but allowed -- see motion_sample_points),
                # fall back to end of run_time minus a small margin so we
                # sample the *final* frame of the animation, not the first.
                if state.wait == 0 and state.run_time > 0:
                    # Sample at run_time end minus 0.05, but ensure we are
                    # not sampling the very first 0.3s of the clip where a
                    # FadeIn/Write entrance is still in progress.
                    alt = elapsed + state.run_time - 0.05
                    if alt > 0.4:
                        timestamp = min(alt, clip_duration - 0.05)
                    else:
                        timestamp = min(offset, clip_duration - 0.05)

                # Suppress sampling before the scene has had time to
                # present its first settled content -- a frame at 0.09s
                # is mid-entrance, not evidence of an empty scene.
                if timestamp < 0.5 and len(points) == 0:
                    # Push the first sample to at least 0.5s when possible,
                    # or skip it if the clip is too short to have a settled
                    # frame (genuinely empty will still be caught by later
                    # samples or fallback).
                    if clip_duration >= 0.6:
                        timestamp = min(0.5, clip_duration - 0.05)
                    else:
                        elapsed += span
                        continue

                if timestamp > 0:
                    points.append((state.name, round(timestamp, 3)))

            elapsed += span

        if points:
            return points

    count = max(1, fallback_count)

    # Fallback: evenly spaced, but never before 0.5s for the first sample
    # to avoid false positives from entrance animation. A genuinely empty
    # scene will still be detected because later samples will also be low.
    raw = [
        (f"sample_{i}", round(clip_duration * (i + 1) / (count + 1), 3))
        for i in range(count)
    ]
    # Ensure first sample is at least 0.5s when clip is long enough
    if raw and raw[0][1] < 0.5 and clip_duration >= 0.8:
        # Shift all samples forward proportionally, keeping last before end
        shift = 0.5 - raw[0][1]
        adjusted = []
        for name, ts in raw:
            new_ts = min(ts + shift, clip_duration - 0.05)
            if new_ts > 0.1:
                adjusted.append((name, round(new_ts, 3)))
        # If adjustment collapses samples (very short clip), keep at least one
        return adjusted if adjusted else raw
    return raw


def motion_sample_points(
    section_timing: "SectionTiming | None",
    clip_duration: float,
) -> list[tuple[str, float, float]]:
    """(state name, run_time start, run_time end) triples worth diffing.

    Only states with a positive ``run_time`` are included -- a state with
    ``run_time == 0`` has no animation-in-progress window to measure motion
    over at all (distinct from ``sample_points``' broader "zero
    run_time + wait" skip, since a state could have ``wait > 0`` alone).

    Unlike ``sample_points``, there is no evenly-spaced fallback: without
    TemporalIR there is no principled way to know where one state's
    animation window ends and the next begins, so this returns ``[]`` and
    the caller degrades to ``status: skip`` -- correct, not a compromise,
    since fabricating a window here would risk measuring across a state
    boundary and misreporting real motion as absent (or vice versa).
    """

    if clip_duration <= 0:
        return []

    if section_timing is None or not section_timing.states:
        return []

    points: list[tuple[str, float, float]] = []
    elapsed = 0.0

    for state in section_timing.states:
        run_time = state.run_time

        if run_time > 2 * _RUN_TIME_MARGIN:
            start = min(elapsed + _RUN_TIME_MARGIN, clip_duration - 0.05)
            end = min(elapsed + run_time - _RUN_TIME_MARGIN, clip_duration - 0.05)

            if end > start >= 0:
                points.append((state.name, round(start, 3), round(end, 3)))

        elapsed += run_time + state.wait

    return points


def observe_motion(
    clip_path: Path,
    section_timing: "SectionTiming | None",
    *,
    scratch_dir: Path,
) -> dict[str, Any]:
    """Sample a rendered clip's per-state motion and report raw deltas.

    Returns ``{"status": "ok"/"skip", "traces": [{"state", "delta",
    "start", "end"}, ...]}``. Deliberately makes no warn/pass judgment --
    see the module docstring for why that is ``verifier_motion``'s job here,
    unlike Phase 11's ``observe_clip``.

    Never raises: every failure mode degrades to ``status: skip``, the same
    posture ``observe_clip`` already established.
    """

    if not clip_path.exists():
        return {"status": "skip", "detail": "Rendered clip not found.", "traces": []}

    try:
        clip_duration = cfg.duration(clip_path)
    except Exception:
        return {
            "status": "skip",
            "detail": "Could not determine clip duration.",
            "traces": [],
        }

    points = motion_sample_points(section_timing, clip_duration)

    if not points:
        return {
            "status": "skip",
            "detail": "No samplable run_time windows for this clip.",
            "traces": [],
        }

    scratch_dir.mkdir(parents=True, exist_ok=True)

    traces: list[dict[str, Any]] = []

    for name, start, end in points:
        frame_a = scratch_dir / f"motion_{name}_start_{start:.3f}.png"
        frame_b = scratch_dir / f"motion_{name}_end_{end:.3f}.png"

        if not extract_frame(clip_path, start, frame_a):
            continue

        if not extract_frame(clip_path, end, frame_b):
            continue

        delta = frame_delta(frame_a, frame_b)

        if delta is None:
            continue

        traces.append(
            {
                "state": name,
                "delta": delta,
                "start": start,
                "end": end,
            }
        )

    if not traces:
        return {
            "status": "skip",
            "detail": (
                "cv2/ffmpeg unavailable, or every sampled frame pair failed "
                "to extract/decode."
            ),
            "traces": [],
        }

    return {"status": "ok", "traces": traces}


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

    # Track per-sample fractions to distinguish intentional entrance
    # animation (low ink only at very early timestamp) from a genuinely
    # empty scene (low ink throughout). A single early low sample that
    # is followed by later high-ink samples is not a layout failure --
    # it is the expected FadeIn/Write settling period.
    samples: list[tuple[str, float, float | None]] = []
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
        samples.append((name, timestamp, fraction))

        if fraction < min_ink_fraction:
            warnings.append(
                f"WARN [visual_absence] state '{name}' at {timestamp:.2f}s: "
                f"{fraction:.4%} of the frame is non-background "
                "(expected visible content)"
            )

        # Detect spatial collisions, off-frame elements, and caption collisions
        collision_warnings = detect_frame_spatial_collisions(
            frame_path,
            state_name=name,
            timestamp=timestamp,
            tolerance=tolerance if "tolerance" in locals() else _TOLERANCE,
        )
        warnings.extend(collision_warnings)

    if measured == 0:
        return _skip(
            "cv2/ffmpeg unavailable, or every sampled frame failed to "
            "extract/decode."
        )

    # Suppress early-sample-only visual_absence warnings when later samples show content:
    has_high_later = any(
        frac is not None and frac >= min_ink_fraction
        for _, ts, frac in samples
        if ts >= 0.5
    )
    if has_high_later and warnings:
        # Keep non-absence warnings (e.g. overlap, caption_collision, offframe) and filter absence
        retained_warnings: list[str] = []
        for w in warnings:
            if "WARN [visual_absence]" in w:
                # Only keep if timestamp >= 0.5s
                m_ts = re.search(r"at (\d+\.\d+)s", w)
                if m_ts and float(m_ts.group(1)) >= 0.5:
                    retained_warnings.append(w)
            else:
                retained_warnings.append(w)
        warnings = retained_warnings

    return {
        "status": "warn" if warnings else "pass",
        "unit": "frames",
        "stills": measured,
        "warnings": warnings,
    }


__all__ = [
    "COLLISION_IOU_THRESHOLD",
    "COLLISION_IOM_THRESHOLD",
    "DEFAULT_FALLBACK_COUNT",
    "DEFAULT_MIN_INK_FRACTION",
    "DEFAULT_MIN_MOTION_DELTA",
    "detect_frame_spatial_collisions",
    "extract_frame",
    "frame_delta",
    "ink_fraction",
    "motion_sample_points",
    "observe_clip",
    "observe_motion",
    "sample_points",
]
