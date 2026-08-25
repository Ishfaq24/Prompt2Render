"""Typed in-memory state for the Prompt2Render harness.

``SceneContext`` is the canonical handoff object between plugins. It replaces
the historical file-based reach-around while continuing to point at the same
on-disk artifacts produced by the live pipeline.

The context intentionally separates:
    authored/planned state
    generated artifacts
    verification results
    repair state
    provenance/history

Plugins should mutate their declared effects only. They should not use
``SceneContext`` as an unstructured dumping ground.

The schema is backward-compatible with the existing Stage 2/3 fields while
including the Stage 4/5 state that is now actively consumed by the repair
router and verifiers.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .animation_ir import AnimationIR


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

@dataclass
class ScenePlanEntry:
    """One section extracted from ``script.md``.

    This object represents authored/source planning state. LLM-generated
    storyboard detail belongs in ``storyboard_plan`` rather than silently
    replacing the original ``anim`` brief.
    """

    index: int
    stem: str
    title: str
    anim: str = ""
    narration_text: str = ""
    planned: bool = False


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

@dataclass
class NarrationEntry:
    """Per-section timed narration produced by voice/alignment stages."""

    stem: str
    sentences: list[dict[str, Any]] = field(
        default_factory=list
    )
    source: str = "align"


# ---------------------------------------------------------------------------
# Generated code
# ---------------------------------------------------------------------------

@dataclass
class CodeArtifact:
    """Generated scene source.

    ``accepted`` is intentionally separate from ``generated``. Generation
    success does not imply semantic/spatial/temporal acceptance.
    """

    stem: str
    path: Path | None = None
    generated: bool = False
    accepted: bool = False


# ---------------------------------------------------------------------------
# Rendered artifacts
# ---------------------------------------------------------------------------

@dataclass
class RenderArtifact:
    """Rendered scene artifacts and the renderer's recorded audit.

    ``clip`` is optional because different renderers expose different output
    representations. The temporal verifier may use it when available and
    otherwise falls back to its backend-specific path resolution.
    """

    stem: str
    outdir: Path | None = None
    clip: Path | None = None
    manifest: list[dict[str, Any]] = field(
        default_factory=list
    )
    audit: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Audio/video artifacts
# ---------------------------------------------------------------------------

@dataclass
class AudioArtifact:
    """Artifacts from TTS/mastering."""

    stem: str
    raw_wav: Path | None = None
    sentences_json: Path | None = None
    meta_json: Path | None = None


@dataclass
class VideoArtifact:
    """Artifacts produced by downstream encode/finalization stages."""

    stem: str
    clip_mp4: Path | None = None
    final_mp4: Path | None = None
    captions_srt: Path | None = None


# ---------------------------------------------------------------------------
# Cross-scene object model
# ---------------------------------------------------------------------------

@dataclass
class ObjectRow:
    """Cross-scene object identity record.

    The table is intentionally present even though current plugins do not yet
    populate authoritative object identity.
    """

    id: str
    kind: str = ""
    created_at_scene: str | None = None
    removed_at_scene: str | None = None
    referenced_at: list[str] = field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Provenance/history
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    """One successful/failed plugin execution record."""

    plugin: str
    at: str
    effects: list[str] = field(
        default_factory=list
    )
    ok: bool = True


# ---------------------------------------------------------------------------
# SceneContext
# ---------------------------------------------------------------------------

@dataclass
class SceneContext:
    """Complete mutable state for one Prompt2Render harness execution."""

    # ------------------------------------------------------------------
    # Source / project
    # ------------------------------------------------------------------

    prompt: Path | None = None
    project_dir: Path | None = None

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    scene_plan: list[ScenePlanEntry] = field(
        default_factory=list
    )

    object_table: list[ObjectRow] = field(
        default_factory=list
    )

    # ------------------------------------------------------------------
    # Narration / generation
    # ------------------------------------------------------------------

    narration: dict[
        str,
        NarrationEntry,
    ] = field(
        default_factory=dict
    )

    code_artifacts: dict[
        str,
        CodeArtifact,
    ] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # Rendering / downstream artifacts
    # ------------------------------------------------------------------

    render_artifacts: dict[
        str,
        RenderArtifact,
    ] = field(
        default_factory=dict
    )

    audio_artifacts: dict[
        str,
        AudioArtifact,
    ] = field(
        default_factory=dict
    )

    video_artifacts: dict[
        str,
        VideoArtifact,
    ] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    # keyed by verifier plugin name -> list of finding-shaped dictionaries.
    check_results: dict[
        str,
        list[dict[str, Any]],
    ] = field(
        default_factory=dict
    )

    # Aggregate/static verification marker. This is informational and does
    # not replace individual verifier findings.
    static_code_verified: bool = False
    pedagogy_verified: bool = False
    storyboard_verified: bool = False

    # ------------------------------------------------------------------
    # Educational planning/review
    # ------------------------------------------------------------------

    pedagogy_review: dict[str, Any] = field(
        default_factory=dict
    )

    # Explicit ordering marker emitted after the reviser has reconciled the
    # canonical script, scene plan, and pedagogy review. It is intentionally
    # separate from those mutable fields so the dependency DAG can represent
    # the revision boundary without declaring an in-place read/write conflict.
    script_revision: int = 0

    storyboard_plan: dict[str, Any] = field(
        default_factory=dict
    )

    # Typed, versioned, hashed counterpart to storyboard_plan, built by
    # verifier_animation_ir. None until that plugin has run successfully;
    # AnimationIR is only imported under TYPE_CHECKING below to avoid a
    # circular import (animation_ir -> motion -> context).
    animation_ir: "AnimationIR | None" = None

    # Deterministic local retrieval context. Kept separate from authored
    # ScenePlanEntry.anim so retrieved snippets cannot silently rewrite the
    # visual brief.
    retrieval_context: dict[
        str,
        list[dict[str, Any]],
    ] = field(
        default_factory=dict
    )

    # Compatibility alias used by older retriever implementations.
    retriever_manim_rag: dict[
        str,
        list[dict[str, Any]],
    ] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # Human feedback
    # ------------------------------------------------------------------

    hitl_annotations: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    # ------------------------------------------------------------------
    # Self-correction / repair
    # ------------------------------------------------------------------

    # keyed by scene stem -> accumulated diagnostic messages.
    repair_context: dict[
        str,
        list[str],
    ] = field(
        default_factory=dict
    )

    # Machine-readable repair-cycle records used to build
    # self_correction_report.json.
    repair_records: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    # ------------------------------------------------------------------
    # Execution provenance
    # ------------------------------------------------------------------

    history: list[HistoryEntry] = field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# Snapshot / restore
# ---------------------------------------------------------------------------

def snapshot(
    ctx: SceneContext,
) -> SceneContext:
    """Create a complete copy-on-write snapshot.

    Deep copying is intentional for the current repair architecture. Diff
    tracking can be introduced later if profiling shows snapshot cost is
    material for long-form videos.
    """

    return copy.deepcopy(
        ctx
    )


def restore(
    ctx: SceneContext,
    snap: SceneContext,
) -> SceneContext:
    """Restore ``ctx`` in place from a previous snapshot.

    The object identity of ``ctx`` is preserved, so references held by the
    pipeline continue to point to the restored context.
    """

    if not isinstance(
        snap,
        SceneContext,
    ):
        raise TypeError(
            "snap must be a SceneContext"
        )

    restored = copy.deepcopy(
        snap
    )

    ctx.__dict__.clear()
    ctx.__dict__.update(
        restored.__dict__
    )

    return ctx


__all__ = [
    "ScenePlanEntry",
    "NarrationEntry",
    "CodeArtifact",
    "RenderArtifact",
    "AudioArtifact",
    "VideoArtifact",
    "ObjectRow",
    "HistoryEntry",
    "SceneContext",
    "snapshot",
    "restore",
]