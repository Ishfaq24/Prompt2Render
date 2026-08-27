"""Sidecar candidate workspace for regression-safe repair.

The problem this solves: every repair path in the harness used to overwrite
the accepted scene in place. ``generator_code._remove_scene_artifacts`` and
``generator_manim._remove_generated_scene`` both do
``path.unlink(missing_ok=True)`` before regenerating, and ``stills.render``
deletes ``manifest.json``/``audit.json`` up front. So the moment a repair
started, the previously-accepted artifact was **gone** -- and if the LLM
came back with something worse, there was nothing left to fall back to. A
failed regeneration was a net loss.

A candidate is therefore written to a sidecar path and only *promoted* onto
the canonical path once it has been verified and judged at least as good:

    build/harness/candidates/<stem>/rev<N>/
        scene_<stem>.py          <- candidate source
        render/                  <- candidate stills dir / Manim output

    accepted (canonical, untouched while the candidate is evaluated):
        build/scenes/scene_<stem>.py       (stills path)
        build/scenes/<stem>/                (stills output)
        build/manim/scene_<stem>.py         (Manim path)

The accepted files are never modified during evaluation. Promotion is a
move onto the canonical path; discard is a delete of the sidecar tree. Only
promotion advances ``scene_versions[stem]`` -- a rejected candidate leaves
the scene at exactly the revision it was already at, so nothing derived
from it becomes spuriously stale.

Path threading is narrower than it looks because most verifiers already
follow ``CodeArtifact.path`` / ``RenderArtifact.manifest`` rather than
recomputing canonical locations. ``resolve_code_path`` /
``resolve_render_dir`` below are the two seams the generators and renderers
consult; when no candidate is open they return the canonical paths, so
ordinary non-repair builds behave exactly as before.
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

from . import lineage
from .context import CandidateScope, SceneContext

#: Root for all candidate trees, under the project's build directory.
CANDIDATE_ROOT = ("build", "harness", "candidates")


def candidate_root(
    project_dir: Path,
    stem: str,
    revision: int,
) -> Path:
    """``build/harness/candidates/<stem>/rev<N>/``."""

    root = Path(project_dir)

    for part in CANDIDATE_ROOT:
        root = root / part

    return root / str(stem) / f"rev{int(revision)}"


def is_candidate_open(
    context: SceneContext,
    stem: str | None = None,
) -> bool:
    """Whether a candidate is currently under evaluation.

    With ``stem``, narrows the question to that specific scene -- which is
    what generators and renderers need, since a candidate for scene 03 must
    not redirect scene 07's paths.
    """

    scope = context.candidate

    if scope is None:
        return False

    if stem is None:
        return True

    return str(scope.stem) == str(stem)


def resolve_code_path(
    context: SceneContext,
    stem: str,
    canonical: Path,
) -> Path:
    """Where this scene's source should be written/read right now.

    The candidate path while a candidate for this scene is open, otherwise
    the canonical path unchanged.
    """

    if is_candidate_open(context, stem):
        return context.candidate.code_path

    return canonical


def resolve_render_dir(
    context: SceneContext,
    stem: str,
    canonical: Path,
) -> Path:
    """Where this scene's render output should go right now."""

    if is_candidate_open(context, stem):
        return context.candidate.render_dir

    return canonical


def open_candidate(
    context: SceneContext,
    stem: str,
    *,
    canonical_code: Path,
    trigger_finding_type: str = "",
) -> CandidateScope:
    """Begin evaluating a repair candidate for one scene.

    Snapshots the accepted artifact records (deep copies, so a later
    in-place mutation by a generator cannot corrupt the restore point) and
    allocates a clean sidecar tree. Does **not** touch the accepted files on
    disk in any way.

    Raises ``ValueError`` for a non-scene stem -- whole-video findings carry
    the ``"__all__"`` pseudo-stem and have no single scene to repair.
    """

    if not lineage.is_scene_stem(stem):
        raise ValueError(
            f"cannot open a repair candidate for non-scene stem {stem!r}"
        )

    if context.candidate is not None:
        raise RuntimeError(
            f"a candidate for {context.candidate.stem!r} is already open; "
            "candidates are evaluated one at a time"
        )

    base = lineage.current_revision(context, stem)
    revision = base + 1

    root = candidate_root(context.project_dir, stem, revision)

    # A leftover tree from an interrupted earlier attempt must never be
    # mistaken for this attempt's output.
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

    render_dir = root / "render"
    root.mkdir(parents=True, exist_ok=True)
    render_dir.mkdir(parents=True, exist_ok=True)

    scope = CandidateScope(
        stem=str(stem),
        base_revision=base,
        revision=revision,
        root=root,
        code_path=root / Path(canonical_code).name,
        render_dir=render_dir,
        accepted_code=copy.deepcopy(
            context.code_artifacts.get(str(stem))
        ),
        accepted_render=copy.deepcopy(
            context.render_artifacts.get(str(stem))
        ),
        trigger_finding_type=str(trigger_finding_type or ""),
    )

    context.candidate = scope

    return scope


def _replace(source: Path, destination: Path) -> None:
    """Move ``source`` onto ``destination``, replacing what is there.

    Directories are replaced wholesale. ``Path.replace`` is atomic within a
    filesystem; the copy fallback covers the cross-device case, matching how
    ``encode.py`` already handles its own transactional installs on Windows.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)

        try:
            source.replace(destination)
        except OSError:
            shutil.copytree(source, destination)
            shutil.rmtree(source, ignore_errors=True)

        return

    try:
        source.replace(destination)
    except OSError:
        shutil.copyfile(source, destination)
        source.unlink(missing_ok=True)


def promote(
    context: SceneContext,
    scope: CandidateScope,
    *,
    canonical_code: Path,
    canonical_render_dir: Path | None = None,
) -> int:
    """Accept a candidate: move it onto the canonical paths.

    This is the *only* place ``scene_versions`` advances. Returns the new
    revision.

    Everything derived from this scene is now stale by revision comparison,
    which is what makes ``out/final.mp4`` rebuild automatically rather than
    a stale file being mistaken for current.
    """

    stem = scope.stem

    if scope.code_path.exists():
        _replace(scope.code_path, Path(canonical_code))

    render = context.render_artifacts.get(stem)

    if (
        canonical_render_dir is not None
        and scope.render_dir.exists()
        and any(scope.render_dir.iterdir())
    ):
        # Per-scene render directory (stills path): swap the whole tree.
        _replace(scope.render_dir, Path(canonical_render_dir))
    elif (
        render is not None
        and render.clip is not None
        and render.clip.exists()
        and scope.render_dir in render.clip.parents
    ):
        # Manim path: _canonical_render_dir() returns None here because
        # there is no per-scene render directory to swap -- every section's
        # clip lives together in one shared `sections/` directory. Only the
        # single rendered file needs to survive scope.root's cleanup below.
        # Before this, the candidate's mp4 was silently deleted by that
        # cleanup while RenderArtifact.clip/manifest kept pointing at the
        # now-gone candidate path -- so a scene that passed judging here
        # still crashed downstream in the finish stage with "no rendered
        # clip for section N", even though the fix had genuinely worked.
        #
        # The `scope.render_dir in render.clip.parents` guard matters: if
        # this repair cycle never re-rendered (code-only fix), `render.clip`
        # still points at the OLD accepted clip in `sections/`, not at
        # anything under this candidate -- moving it "onto itself" would be
        # a no-op at best, but must not be attempted as if it were new work.
        dest = Path(context.project_dir) / "sections" / render.clip.name
        _replace(render.clip, dest)
        render.clip = dest

        for entry in render.manifest:
            if entry.get("mp4"):
                entry["mp4"] = str(dest)

    shutil.rmtree(scope.root, ignore_errors=True)

    revision = lineage.bump(context, stem)

    # Repoint the in-memory artifacts at the now-canonical files and stamp
    # them with the revision they represent.
    code = context.code_artifacts.get(stem)

    if code is not None:
        code.path = Path(canonical_code)
        code.revision = revision

    if render is not None:
        render.source_revision = revision

        if canonical_render_dir is not None:
            render.outdir = Path(canonical_render_dir)
        elif render.clip is not None:
            render.outdir = render.clip.parent

    context.candidate = None

    return revision


def discard(
    context: SceneContext,
    scope: CandidateScope,
) -> int:
    """Reject a candidate: delete the sidecar and restore accepted records.

    The canonical files on disk were never touched, so restoring is purely a
    matter of putting back the artifact objects (which a generator may have
    repointed at the candidate path) and dropping the findings the candidate
    produced. Returns the revision the scene remains at.

    Deliberately does **not** bump ``scene_versions``: the accepted scene did
    not change, so nothing derived from it became stale.
    """

    stem = scope.stem

    shutil.rmtree(scope.root, ignore_errors=True)

    if scope.accepted_code is not None:
        context.code_artifacts[stem] = copy.deepcopy(scope.accepted_code)
    else:
        context.code_artifacts.pop(stem, None)

    if scope.accepted_render is not None:
        context.render_artifacts[stem] = copy.deepcopy(scope.accepted_render)
    else:
        context.render_artifacts.pop(stem, None)

    context.candidate = None

    return lineage.current_revision(context, stem)


def cleanup_candidates(
    project_dir: Path | None,
    stem: str | None = None,
) -> None:
    """Remove leftover candidate trees (crash recovery / housekeeping).

    Never raises -- a failure to tidy scratch space must not affect a build.
    """

    if project_dir is None:
        return

    root = Path(project_dir)

    for part in CANDIDATE_ROOT:
        root = root / part

    target = root if stem is None else root / str(stem)

    try:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    except OSError:
        return


__all__ = [
    "CANDIDATE_ROOT",
    "candidate_root",
    "cleanup_candidates",
    "discard",
    "is_candidate_open",
    "open_candidate",
    "promote",
    "resolve_code_path",
    "resolve_render_dir",
]
