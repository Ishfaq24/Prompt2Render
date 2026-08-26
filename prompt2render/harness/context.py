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
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .animation_ir import AnimationIR
    from .semantic_plan import SemanticAnimationIR
    from .temporal_ir import TemporalIR


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

    #: Explicit artifact lineage: which revision of this scene this source
    #: IS. Compare against ``SceneContext.scene_versions[stem]`` to decide
    #: staleness -- see :mod:`prompt2render.harness.lineage`. Dict-key
    #: presence and file mtime remain useful secondary signals but are no
    #: longer the authoritative mechanism.
    revision: int = 0


# ---------------------------------------------------------------------------
# Rendered artifacts
# ---------------------------------------------------------------------------

@dataclass
class RenderArtifact:
    """Rendered scene artifacts and the renderer's recorded audit.

    ``clip`` is the single rendered video for this scene, when the renderer
    produces one (Manim emits exactly one clip per section; the stills
    renderer emits a per-frame manifest instead and leaves this ``None``).

    Historical note: every Manim render site used to record the clip path
    *only* inside ``manifest[0]["mp4"]`` and never assign ``clip``, while
    ``RendererManimFinishPlugin`` read ``clip`` exclusively -- so it always
    saw an empty clip map and ``finish_manim`` could never assemble a final
    video. Both are now written at every render site; ``clip_path()`` below
    is the single reader that tolerates either.
    """

    stem: str
    outdir: Path | None = None
    clip: Path | None = None
    manifest: list[dict[str, Any]] = field(
        default_factory=list
    )
    audit: dict[str, Any] | None = None

    #: Explicit artifact lineage: the ``CodeArtifact.revision`` this render
    #: was produced from. A render whose ``source_revision`` is behind
    #: ``SceneContext.scene_versions[stem]`` is stale by definition, with no
    #: mtime comparison required.
    source_revision: int = 0

    #: Tier 3 Phase 12 (motion traces): raw per-state frame-delta evidence
    #: from ``visual_observe.observe_motion``, populated by
    #: ``ObserverVisualPlugin`` alongside ``audit``. Kept as a separate
    #: field rather than folded into ``audit`` -- unlike ``audit``, no
    #: existing consumer (verifier_spatial) needs to parse it unmodified,
    #: and "motion" is a distinct quality dimension from "spatial" in
    #: quality_report.py's own classification, so conflating the two
    #: records would blur a distinction Phase 10 deliberately introduced.
    motion: dict[str, Any] | None = None

    def clip_path(self) -> Path | None:
        """The rendered single-clip video for this scene, or ``None``.

        Prefers the explicit ``clip`` field and falls back to the first
        ``manifest`` entry carrying an ``mp4`` key, so a context restored
        from an older run (or a plugin that only populated the manifest)
        still resolves correctly.
        """

        if self.clip is not None:
            return Path(self.clip)

        for entry in self.manifest or []:
            if not isinstance(entry, dict):
                continue

            mp4 = entry.get("mp4")

            if mp4:
                return Path(mp4)

        return None


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


@dataclass
class ProgramArtifact:
    """The finished programme -- ``out/final.mp4`` and its siblings.

    Deliberately **not** modelled per scene. The final video depends on the
    complete accepted scene/timeline/audio state, so it carries the set of
    scene revisions it was built from. If any scene is later repaired, its
    revision advances and ``is_stale()`` becomes true automatically -- no
    mtime heuristic, and no way for an old ``final.mp4`` to be mistaken for
    current after a scene repair.
    """

    final_mp4: Path | None = None
    captions_srt: Path | None = None
    chapters: Path | None = None
    duration: float = 0.0

    #: sha256 over the sorted ``source_revisions`` mapping -- a single
    #: comparable token for logs and reports.
    source_fingerprint: str = ""

    #: ``{stem: revision}`` captured at production time.
    source_revisions: dict[str, int] = field(
        default_factory=dict
    )

    @staticmethod
    def fingerprint(
        source_revisions: dict[str, int],
    ) -> str:
        """Stable content hash of a scene-revision mapping."""

        canonical = json.dumps(
            {str(k): int(v) for k, v in source_revisions.items()},
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()

    def is_stale(
        self,
        scene_versions: dict[str, int],
    ) -> bool:
        """Whether any scene has advanced past what this was built from."""

        return dict(self.source_revisions) != dict(scene_versions)


# ---------------------------------------------------------------------------
# Repair candidates
# ---------------------------------------------------------------------------

@dataclass
class CandidateScope:
    """One in-flight repair candidate for exactly one scene.

    While this is set on the context, generators and renderers write to the
    sidecar paths below instead of the canonical ones, so the currently
    *accepted* scene on disk is never overwritten by an unproven repair.
    Promotion (on acceptance) moves the candidate onto the canonical paths;
    discard (on rejection) deletes it and leaves the accepted scene exactly
    as it was.

    Lives here rather than in :mod:`prompt2render.harness.workspace` purely
    to keep ``SceneContext`` free of a circular import -- ``workspace`` owns
    all the behaviour, this is only the record.
    """

    stem: str

    #: The revision the accepted artifacts are at, i.e. what a rejection
    #: restores to.
    base_revision: int

    #: The revision this candidate would become if accepted.
    revision: int

    #: Sidecar root: ``build/harness/candidates/<stem>/rev<N>/``.
    root: Path

    #: Where the candidate scene source is written.
    code_path: Path

    #: Where the candidate's render output goes (stills dir or Manim dir).
    render_dir: Path

    #: Deep copies of the accepted artifacts, restored verbatim on reject.
    accepted_code: CodeArtifact | None = None
    accepted_render: RenderArtifact | None = None

    #: Which finding triggered this repair -- carried for the decision log.
    trigger_finding_type: str = ""


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

    #: The finished programme. ``None`` until a finish stage produces it.
    #: Program-scoped, not per-scene -- see :class:`ProgramArtifact`.
    program: ProgramArtifact | None = None

    # ------------------------------------------------------------------
    # Artifact lineage
    # ------------------------------------------------------------------

    #: ``{stem: revision}`` -- the authoritative revision of each scene.
    #: Bumped only when a scene's source is genuinely regenerated and the
    #: result is *accepted*. Everything derived from a scene records the
    #: revision it came from, so staleness is a comparison rather than a
    #: heuristic. See :mod:`prompt2render.harness.lineage`.
    scene_versions: dict[str, int] = field(
        default_factory=dict
    )

    #: The repair candidate currently under evaluation, if any. Set by
    #: ``workspace.open_candidate`` and cleared on promote/discard, so
    #: generators and renderers can write to sidecar paths without the
    #: accepted artifact ever being overwritten.
    candidate: "CandidateScope | None" = None

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

    # Downstream pedagogical phase model (CONTEXT/ANTICIPATION/ACTION/
    # CONSEQUENCE/HOLD) built on top of animation_ir by planner_semantic.
    # None until that plugin has run successfully.
    semantic_ir: "SemanticAnimationIR | None" = None

    # Narration-authoritative timing built on top of semantic_ir by
    # planner_temporal. None until that plugin has run successfully;
    # advisory (non-blocking) -- see planner_temporal's _default_gate.
    temporal_ir: "TemporalIR | None" = None

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