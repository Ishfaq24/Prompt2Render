"""Structured visual memory and revision-to-revision visual diff.

Phase 12/13 of the upgrade: the next regeneration must receive structured
information about the previous accepted visual state -- not merely a
preview image -- and a candidate that unexpectedly moves the world while
fixing a local error must be flagged as a likely regression.

The signal here is deliberately structural, never pixel-perfect: animation
and re-encoding legitimately differ between revisions. What is stable and
meaningful:

* the frame/state inventory (manifest entries on the stills path, clip +
  preview presence on the Manim path),
* the layout audit's warning inventory,
* the zone/safe-area contract both backends share (``layout_zones``).

``visual_diff()`` compares two states and reports conservative regression
flags; the repair controller consults them only for LOCAL/REGIONAL repairs,
where broad visual churn is by definition unwanted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import SceneContext
from .layout_zones import (
    SCENEKIT_SAFE_X,
    SCENEKIT_SAFE_Y,
    SCENEKIT_ZONES,
    manim_zones,
)

VISUAL_STATE_SCHEMA_VERSION = "1.0"

#: A candidate losing this fraction of its frames/states is suspect.
FRAME_LOSS_THRESHOLD = 0.3

#: Growth in audit warnings tolerated before flagging a regression.
WARNING_GROWTH_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _stills_state(render_dir: Path) -> dict[str, Any] | None:
    """Visual state from a stills render directory (manifest + audit)."""

    manifest = _read_json(render_dir / "manifest.json")

    if not isinstance(manifest, list):
        return None

    audit = _read_json(render_dir / "audit.json") or {}

    names = [
        str(entry.get("name", "")).strip()
        for entry in manifest
        if isinstance(entry, dict)
    ]

    warnings = [
        str(w) for w in (audit.get("warnings") or []) if str(w).strip()
    ]

    return {
        "backend": "stills",
        "frame_count": len(manifest),
        "state_names": sorted({n for n in names if n}),
        "audit_warnings": len(warnings),
        "audit_warning_samples": warnings[:8],
    }


def _manim_state(
    context: SceneContext,
    stem: str,
) -> dict[str, Any]:
    """Visual state for the Manim path: clip/preview + zone contract."""

    state: dict[str, Any] = {
        "backend": "manim",
        "frame_count": 1,
        "state_names": [],
        "audit_warnings": 0,
        "audit_warning_samples": [],
    }

    render = (context.render_artifacts or {}).get(str(stem))

    if render is not None:
        clip = None

        if hasattr(render, "clip_path"):
            try:
                clip = render.clip_path()
            except Exception:
                clip = None

        if clip is None:
            clip = getattr(render, "clip", None)

        state["has_clip"] = bool(clip is not None and Path(clip).exists())

    try:
        from .preview import canonical_preview_path, preview_path_for
        from . import workspace as _ws

        if _ws.is_candidate_open(context, stem):
            preview = preview_path_for(context, stem)
        else:
            preview = canonical_preview_path(
                getattr(context, "project_dir", None), stem
            )

        state["has_preview"] = bool(preview.exists() and preview.stat().st_size > 0)
    except Exception:
        state["has_preview"] = False

    return state


def collect_visual_state(context: SceneContext, stem: str) -> dict[str, Any]:
    """Structured visual state for one scene at its CURRENT artifacts.

    Reads whatever the active backend's render produced; zones come from
    the shared ``layout_zones`` contract so the generator and this module
    can never disagree about where the caption lives.
    """

    state: dict[str, Any] = {
        "schema_version": VISUAL_STATE_SCHEMA_VERSION,
        "scene_id": str(stem),
        "zones": {name: list(bounds) for name, bounds in SCENEKIT_ZONES.items()},
        "safe_area": {
            "x": list(SCENEKIT_SAFE_X),
            "y": list(SCENEKIT_SAFE_Y),
        },
        "manim_zones": {
            name: list(bounds) for name, bounds in manim_zones().items()
        },
    }

    render = (context.render_artifacts or {}).get(str(stem))
    outdir = getattr(render, "outdir", None) if render is not None else None

    stills_state = None

    if outdir is not None:
        stills_state = _stills_state(Path(outdir))

    if stills_state is not None:
        state.update(stills_state)
    else:
        state.update(_manim_state(context, stem))

    return state


# ---------------------------------------------------------------------------
# Persistence (next to the other per-revision artifacts)
# ---------------------------------------------------------------------------

def write_visual_state(
    project_dir: Path | None,
    stem: str,
    revision: int,
    state: dict[str, Any],
) -> Path | None:
    """Persist ``visual_state.json`` for one revision. Never raises."""

    if project_dir is None:
        return None

    try:
        from .evidence import revision_dir

        path = revision_dir(project_dir, stem, revision) / "visual_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def load_visual_state(
    project_dir: Path | None,
    stem: str,
    revision: int,
) -> dict[str, Any] | None:
    """Load a persisted visual state. Never raises."""

    if project_dir is None:
        return None

    try:
        from .evidence import revision_dir

        path = revision_dir(project_dir, stem, revision) / "visual_state.json"

        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))

        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Diff (Phase 13)
# ---------------------------------------------------------------------------

def visual_diff(
    parent: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    """Conservative structural comparison between two revisions.

    No pixel equality: animation and encoding legitimately differ. Flags
    only movement that a LOCAL/REGIONAL repair cannot legitimately cause --
    vanishing states, large frame loss, or a sudden growth in layout
    warnings.
    """

    result: dict[str, Any] = {
        "comparable": False,
        "flags": [],
        "frame_count_delta": 0,
        "removed_states": [],
        "added_states": [],
        "warning_delta": 0,
        "regression_suspected": False,
    }

    if not isinstance(parent, dict) or not isinstance(candidate, dict):
        return result

    result["comparable"] = True

    parent_frames = int(parent.get("frame_count", 0) or 0)
    candidate_frames = int(candidate.get("frame_count", 0) or 0)
    result["frame_count_delta"] = candidate_frames - parent_frames

    if (
        parent_frames > 0
        and candidate_frames < parent_frames
        and (parent_frames - candidate_frames) / parent_frames > FRAME_LOSS_THRESHOLD
    ):
        result["flags"].append(
            f"frame/state inventory shrank {parent_frames} -> {candidate_frames}"
        )

    parent_states = set(parent.get("state_names") or [])
    candidate_states = set(candidate.get("state_names") or [])

    result["removed_states"] = sorted(parent_states - candidate_states)
    result["added_states"] = sorted(candidate_states - parent_states)

    if result["removed_states"]:
        result["flags"].append(
            "previously rendered states disappeared: "
            + ", ".join(result["removed_states"][:6])
        )

    parent_warnings = int(parent.get("audit_warnings", 0) or 0)
    candidate_warnings = int(candidate.get("audit_warnings", 0) or 0)
    result["warning_delta"] = candidate_warnings - parent_warnings

    if result["warning_delta"] >= WARNING_GROWTH_THRESHOLD:
        result["flags"].append(
            f"layout audit warnings grew {parent_warnings} -> {candidate_warnings}"
        )

    # A clip/preview that existed before and is gone now is structural loss.
    if parent.get("has_clip") and candidate.get("has_clip") is False:
        result["flags"].append("rendered clip lost")

    if parent.get("has_preview") and candidate.get("has_preview") is False:
        result["flags"].append("preview lost")

    result["regression_suspected"] = bool(result["flags"])

    return result


__all__ = [
    "FRAME_LOSS_THRESHOLD",
    "VISUAL_STATE_SCHEMA_VERSION",
    "WARNING_GROWTH_THRESHOLD",
    "collect_visual_state",
    "load_visual_state",
    "visual_diff",
    "write_visual_state",
]
