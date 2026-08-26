"""Explicit artifact lineage for the self-correction harness.

Before this module, "is this artifact stale?" was answered with heuristics:
whether a dictionary key existed (``repair_context``, ``render_artifacts``),
whether a ``manifest`` list happened to be empty, or a file mtime
comparison. Those signals were indirect -- a repair that regenerated a
scene's source without touching any of them was invisible, and the runner
compensated with three separate trigger heuristics that could all miss.

Lineage replaces the guesswork with a comparison. Every scene has an
authoritative revision (``SceneContext.scene_versions[stem]``), and
everything derived from that scene records which revision it came from:

    scene 03 revision 5
        |
        +-- CodeArtifact.revision       == 5
        +-- RenderArtifact.source_revision == 5
        +-- check_results[...]["scene_revision"] == 5
        +-- ProgramArtifact.source_revisions["03"] == 5

When scene 03 advances to revision 6, every one of those is behind by
definition -- no mtime, no key-presence test. mtime and manifest checks
remain useful as *secondary* signals (a renderer can still skip work it
knows is current), but they are no longer what decides correctness.

No plugin imports and no side effects beyond mutating the ``SceneContext``
fields it is explicitly asked to mutate. The single exception is
:func:`record_program`, which probes the finished video's duration -- it
lives here because stamping "which scene revisions produced this" is
precisely lineage's concern, and duplicating it across the stills and Manim
finish stages is how the two paths drift apart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import ProgramArtifact, SceneContext

#: Pseudo-stem the repair router assigns to findings that carry no scene.
#: Whole-video verifiers (``verifier_audio``, ``verifier_pedagogy``) emit
#: these. They are deliberately NOT scene-repairable: there is no single
#: scene to regenerate, and every ``revert_scene`` implementation raises
#: ``KeyError`` on it. Callers filter with :func:`is_scene_stem`.
GLOBAL_STEM = "__all__"


def is_scene_stem(stem: Any) -> bool:
    """Whether ``stem`` names a real, individually-repairable scene."""

    text = str(stem or "").strip()

    return bool(text) and text != GLOBAL_STEM


def current_revision(
    context: SceneContext,
    stem: str,
) -> int:
    """The authoritative revision of one scene. Unknown scenes are 0."""

    try:
        return int(context.scene_versions.get(str(stem), 0))
    except (TypeError, ValueError):
        return 0


def bump(
    context: SceneContext,
    stem: str,
) -> int:
    """Advance one scene to its next revision and return it.

    Called only when a regenerated scene is genuinely *accepted*. A rejected
    repair candidate must never bump -- the accepted scene did not change,
    so nothing derived from it became stale.
    """

    key = str(stem)
    nxt = current_revision(context, key) + 1
    context.scene_versions[key] = nxt

    return nxt


def ensure_tracked(
    context: SceneContext,
    stem: str,
) -> int:
    """Make sure a scene has a revision, seeding revision 1 on first sight.

    Revision 0 means "never generated". The first successful generation of a
    scene moves it to 1 so that a later repair produces 2, and the
    difference between "no artifact" and "the original artifact" stays
    representable.
    """

    key = str(stem)

    if current_revision(context, key) == 0:
        context.scene_versions[key] = 1

    return current_revision(context, key)


def stamp_code_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    """Record the current revision on a scene's code artifact."""

    artifact = context.code_artifacts.get(str(stem))

    if artifact is not None:
        artifact.revision = current_revision(context, stem)


def stamp_render_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    """Record the source revision a render was produced from."""

    artifact = context.render_artifacts.get(str(stem))

    if artifact is not None:
        artifact.source_revision = current_revision(context, stem)


def render_is_stale(
    context: SceneContext,
    stem: str,
) -> bool:
    """Whether a scene's render is behind its source revision.

    A missing render counts as stale. So does a render with no output at
    all (empty manifest and no clip) -- that is a failed render recorded as
    a placeholder, not a usable artifact.
    """

    artifact = context.render_artifacts.get(str(stem))

    if artifact is None:
        return True

    if not artifact.manifest and artifact.clip_path() is None:
        return True

    return int(artifact.source_revision) != current_revision(context, stem)


def stamp_check_results(
    results: list[dict[str, Any]],
    revision: int,
) -> list[dict[str, Any]]:
    """Tag every scene-scoped finding with the revision it was produced at.

    Applied centrally by the runner rather than asking each of the eleven
    verifiers to remember -- the same reasoning that moved ``finding_type``
    onto ``Finding`` itself (F11). Findings that carry no stem are left
    alone: they are whole-video results and have no scene revision.
    """

    for result in results or []:
        if not isinstance(result, dict):
            continue

        stem = result.get("stem") or result.get("scene_id")

        if is_scene_stem(stem):
            result.setdefault("scene_revision", revision)

    return results


def result_is_current(
    context: SceneContext,
    result: dict[str, Any],
) -> bool:
    """Whether one recorded finding still describes the current revision.

    An untagged finding is treated as current: whole-video findings have no
    scene revision, and a finding written before lineage existed should not
    be silently discarded.
    """

    if not isinstance(result, dict):
        return False

    stem = result.get("stem") or result.get("scene_id")

    if not is_scene_stem(stem):
        return True

    if "scene_revision" not in result:
        return True

    try:
        recorded = int(result["scene_revision"])
    except (TypeError, ValueError):
        return True

    return recorded == current_revision(context, str(stem))


def drop_stale_results(
    context: SceneContext,
    stem: str,
) -> int:
    """Remove findings for one scene that predate its current revision.

    Deliberately surgical: only this scene's outdated entries are dropped.
    Other scenes' evidence, and this scene's still-current evidence, are
    preserved -- unlike the previous rewind path, which cleared whole
    verifier entries wholesale.

    Returns how many findings were removed.
    """

    removed = 0
    target = str(stem)

    for plugin_name in list(context.check_results):
        results = context.check_results.get(plugin_name)

        if not isinstance(results, list):
            continue

        kept = []

        for result in results:
            if (
                isinstance(result, dict)
                and str(
                    result.get("stem") or result.get("scene_id") or ""
                ) == target
                and not result_is_current(context, result)
            ):
                removed += 1
                continue

            kept.append(result)

        if len(kept) != len(results):
            context.check_results[plugin_name] = kept

    return removed


def program_is_stale(
    context: SceneContext,
) -> bool:
    """Whether the finished programme predates the current scene state.

    A missing programme is stale. This is what guarantees an old
    ``final.mp4`` can never be treated as current after a scene repair.
    """

    if context.program is None:
        return True

    return context.program.is_stale(context.scene_versions)


def record_program(
    context: SceneContext,
    *,
    final_mp4: Path | None,
    captions_srt: Path | None = None,
    chapters: Path | None = None,
) -> ProgramArtifact:
    """Record the finished programme, stamped with its source revisions.

    Called by whichever finish stage produced the video (``renderer_finish``
    on the stills path, ``renderer_manim_finish`` on the Manim path). The
    revision snapshot taken here is what makes a later scene repair
    invalidate this programme automatically.

    Duration probing is best-effort: a probe failure yields ``0.0`` rather
    than derailing a successful finish.
    """

    existing = final_mp4 if final_mp4 and Path(final_mp4).exists() else None

    duration = 0.0

    if existing is not None:
        try:
            from .. import cfg

            duration = float(cfg.duration(Path(existing)))
        except (Exception, SystemExit):
            # cfg.duration wraps ffprobe via cfg.run, which raises
            # SystemExit (a BaseException, NOT an Exception) on failure --
            # the same trap align.load() carries. A truncated or absent
            # video must not derail an otherwise successful finish; the
            # reachability gate checks the file separately.
            duration = 0.0

    revisions = {
        str(stem): int(rev)
        for stem, rev in context.scene_versions.items()
    }

    program = ProgramArtifact(
        final_mp4=Path(existing) if existing is not None else None,
        captions_srt=(
            Path(captions_srt)
            if captions_srt and Path(captions_srt).exists()
            else None
        ),
        chapters=(
            Path(chapters)
            if chapters and Path(chapters).exists()
            else None
        ),
        duration=duration,
        source_fingerprint=ProgramArtifact.fingerprint(revisions),
        source_revisions=revisions,
    )

    context.program = program

    return program


def invalidate_scene(
    context: SceneContext,
    stem: str,
) -> None:
    """Mark everything derived from one scene as needing rebuild.

    Drops the scene's stale findings and its render artifact, and clears the
    per-scene downstream video artifact. The programme is *not* explicitly
    cleared -- it becomes stale automatically via revision comparison, which
    keeps the previous ``final.mp4`` on disk inspectable while ensuring
    nothing treats it as current.
    """

    key = str(stem)

    drop_stale_results(context, key)

    if render_is_stale(context, key):
        context.render_artifacts.pop(key, None)

    context.video_artifacts.pop(key, None)


__all__ = [
    "GLOBAL_STEM",
    "bump",
    "current_revision",
    "drop_stale_results",
    "ensure_tracked",
    "invalidate_scene",
    "is_scene_stem",
    "program_is_stale",
    "record_program",
    "render_is_stale",
    "result_is_current",
    "stamp_check_results",
    "stamp_code_artifact",
    "stamp_render_artifact",
]
