"""SceneContext — the explicit, in-memory replacement for prompt2render's file-based reach-around
(docs/MIGRATION_INVENTORY.md §2). Every field below corresponds to a named handoff that stage
code today reads/writes as a bare file path; the harness reads/writes the same underlying files
through a typed field instead.

Schema is the canonical one from the migration brief:
    prompt, scene_plan, object_table, narration, code_artifacts, render_artifacts,
    check_results, hitl_annotations, history

`repair_context` (Stage 4) and the `Finding`/severity enum (Stage 5) are deliberately not here —
the brief calls those out as additions to make when those stages need them, not before.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScenePlanEntry:
    """One section, as `chunker_scene` extracts it from script.md — not model output."""
    index: int
    stem: str
    title: str
    anim: str = ""              # the human-authored "> ANIM:" brief
    narration_text: str = ""    # the section's spoken narration, as written
    planned: bool = False       # set by planner_llm (passthrough — see its docstring)


@dataclass
class NarrationEntry:
    """Per-section timed narration, ingested from voice/align output (not planned)."""
    stem: str
    sentences: list[dict] = field(default_factory=list)   # mirrors align.load()["sentences"]
    source: str = "align"


@dataclass
class CodeArtifact:
    stem: str
    path: Path | None = None
    accepted: bool = False


@dataclass
class RenderArtifact:
    stem: str
    outdir: Path | None = None
    manifest: list[dict] = field(default_factory=list)
    audit: dict | None = None


@dataclass
class ObjectRow:
    """One object_table row. Designed now, per the brief; populated by nothing yet — no live
    prompt2render code assigns cross-scene object identity (docs/MIGRATION_INVENTORY.md §7)."""
    id: str
    kind: str = ""
    created_at_scene: str | None = None
    removed_at_scene: str | None = None
    referenced_at: list[str] = field(default_factory=list)


@dataclass
class HistoryEntry:
    plugin: str
    at: str            # ISO 8601 timestamp
    effects: list[str]
    ok: bool


@dataclass
class SceneContext:
    prompt: Path | None = None                                   # path to script.md
    scene_plan: list[ScenePlanEntry] = field(default_factory=list)
    object_table: list[ObjectRow] = field(default_factory=list)
    narration: dict[str, NarrationEntry] = field(default_factory=dict)      # keyed by stem
    code_artifacts: dict[str, CodeArtifact] = field(default_factory=dict)   # keyed by stem
    render_artifacts: dict[str, RenderArtifact] = field(default_factory=dict)  # keyed by stem
    # keyed by verifier plugin name -> list of finding-shaped dicts. Stage 5 formalizes the
    # dict shape into Finding; kept loose here so Stage 3 verifiers don't need to know about it.
    check_results: dict[str, list[dict]] = field(default_factory=dict)
    hitl_annotations: list[dict] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    # Stage 4 addition (not in the original Stage 2/3 schema — added here because Stage 4 is
    # where it's first read): keyed by stem -> diagnostic strings repair_router appends so
    # generator_code can receive repair feedback on the next attempt.
    repair_context: dict[str, list[str]] = field(default_factory=dict)

    # --- non-schema convenience, not part of the brief's field list ---
    project_dir: Path | None = None   # the prompt2render project root this context operates on


def snapshot(ctx: SceneContext) -> SceneContext:
    """Copy-on-write snapshot, per the brief: deep-copy now, don't build diff tracking yet.

    Cost may matter for long-form videos — profile once Stage 4's repair loops actually call
    revert() repeatedly, not before.
    """
    return copy.deepcopy(ctx)


def restore(ctx: SceneContext, snap: SceneContext) -> SceneContext:
    """Restore `ctx` in place from `snap`, so callers holding a reference see the reverted state."""
    ctx.__dict__.update(copy.deepcopy(snap).__dict__)
    return ctx
