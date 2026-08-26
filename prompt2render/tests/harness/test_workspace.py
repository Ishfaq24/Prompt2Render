"""Sidecar candidate workspace.

The property that matters most here, and is asserted repeatedly below: while
a candidate is being evaluated, the *accepted* files on disk are byte-for-byte
untouched. Before this existed, every repair path unlinked the accepted scene
before regenerating, so a worse LLM result was a net loss of working work.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness import lineage, workspace
from prompt2render.harness.context import (
    CodeArtifact,
    RenderArtifact,
    SceneContext,
)

ACCEPTED_SOURCE = "# accepted scene 03\nprint('good')\n"


def _project(tmp_path: Path) -> tuple[SceneContext, Path, Path]:
    """A context with one accepted scene 03 on disk at revision 1."""

    canonical = tmp_path / "build" / "scenes" / "scene_03.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(ACCEPTED_SOURCE, encoding="utf-8")

    render_dir = tmp_path / "build" / "scenes" / "03"
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "manifest.json").write_text("[]", encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions["03"] = 1
    ctx.code_artifacts["03"] = CodeArtifact(
        stem="03", path=canonical, accepted=True, revision=1
    )
    ctx.render_artifacts["03"] = RenderArtifact(
        stem="03", outdir=render_dir, manifest=[{"png": "a.png"}], source_revision=1
    )
    return ctx, canonical, render_dir


# ------------------------------------------------------------ path resolution

def test_paths_are_canonical_when_no_candidate_is_open(tmp_path):
    """Ordinary non-repair builds must behave exactly as before."""
    ctx, canonical, render_dir = _project(tmp_path)

    assert workspace.is_candidate_open(ctx) is False
    assert workspace.resolve_code_path(ctx, "03", canonical) == canonical
    assert workspace.resolve_render_dir(ctx, "03", render_dir) == render_dir


def test_open_candidate_redirects_only_its_own_scene(tmp_path):
    """A candidate for 03 must not redirect scene 07's paths."""
    ctx, canonical, render_dir = _project(tmp_path)
    workspace.open_candidate(ctx, "03", canonical_code=canonical)

    other = tmp_path / "build" / "scenes" / "scene_07.py"
    assert workspace.resolve_code_path(ctx, "07", other) == other
    assert workspace.resolve_code_path(ctx, "03", canonical) != canonical
    assert workspace.is_candidate_open(ctx, "07") is False
    assert workspace.is_candidate_open(ctx, "03") is True


def test_candidate_paths_live_under_the_project_build_dir(tmp_path):
    ctx, canonical, _ = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    assert scope.root == tmp_path / "build" / "harness" / "candidates" / "03" / "rev2"
    assert scope.code_path.name == "scene_03.py"
    assert scope.root.is_dir() and scope.render_dir.is_dir()


# ------------------------------------------------------------------- opening

def test_open_records_base_and_next_revision(tmp_path):
    ctx, canonical, _ = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    assert (scope.base_revision, scope.revision) == (1, 2)
    # Opening must NOT advance the authoritative revision -- only acceptance does.
    assert lineage.current_revision(ctx, "03") == 1


def test_open_does_not_touch_the_accepted_files(tmp_path):
    ctx, canonical, render_dir = _project(tmp_path)
    workspace.open_candidate(ctx, "03", canonical_code=canonical)

    assert canonical.read_text(encoding="utf-8") == ACCEPTED_SOURCE
    assert (render_dir / "manifest.json").exists()


def test_open_rejects_the_global_pseudo_stem(tmp_path):
    """Whole-video findings carry "__all__" and have no single scene to repair."""
    ctx, canonical, _ = _project(tmp_path)

    with pytest.raises(ValueError, match="non-scene stem"):
        workspace.open_candidate(ctx, "__all__", canonical_code=canonical)


def test_open_refuses_a_second_concurrent_candidate(tmp_path):
    ctx, canonical, _ = _project(tmp_path)
    workspace.open_candidate(ctx, "03", canonical_code=canonical)

    with pytest.raises(RuntimeError, match="already open"):
        workspace.open_candidate(ctx, "07", canonical_code=canonical)


def test_open_clears_a_leftover_tree_from_an_interrupted_attempt(tmp_path):
    ctx, canonical, _ = _project(tmp_path)
    stale = workspace.candidate_root(tmp_path, "03", 2)
    stale.mkdir(parents=True, exist_ok=True)
    (stale / "scene_03.py").write_text("# stale junk", encoding="utf-8")

    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    assert not scope.code_path.exists()


# ------------------------------------------------------------------ promotion

def test_promote_moves_the_candidate_onto_the_canonical_path(tmp_path):
    ctx, canonical, render_dir = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    scope.code_path.write_text("# repaired scene 03\n", encoding="utf-8")
    (scope.render_dir / "manifest.json").write_text('[{"png":"new.png"}]', encoding="utf-8")

    revision = workspace.promote(
        ctx, scope, canonical_code=canonical, canonical_render_dir=render_dir
    )

    assert revision == 2
    assert canonical.read_text(encoding="utf-8") == "# repaired scene 03\n"
    assert (render_dir / "manifest.json").read_text(encoding="utf-8") == '[{"png":"new.png"}]'
    assert not scope.root.exists()
    assert ctx.candidate is None


def test_promote_advances_lineage_and_restamps_artifacts(tmp_path):
    ctx, canonical, render_dir = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    scope.code_path.write_text("# repaired\n", encoding="utf-8")

    workspace.promote(
        ctx, scope, canonical_code=canonical, canonical_render_dir=render_dir
    )

    assert lineage.current_revision(ctx, "03") == 2
    assert ctx.code_artifacts["03"].revision == 2
    assert ctx.code_artifacts["03"].path == canonical
    assert ctx.render_artifacts["03"].source_revision == 2


def test_promote_makes_the_existing_programme_stale(tmp_path):
    """A scene repair must invalidate out/final.mp4 automatically."""
    ctx, canonical, render_dir = _project(tmp_path)
    lineage.record_program(ctx, final_mp4=None)
    assert not lineage.program_is_stale(ctx)

    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    scope.code_path.write_text("# repaired\n", encoding="utf-8")
    workspace.promote(
        ctx, scope, canonical_code=canonical, canonical_render_dir=render_dir
    )

    assert lineage.program_is_stale(ctx)


# ------------------------------------------------------------------ discard

def test_discard_leaves_the_accepted_scene_byte_for_byte_intact(tmp_path):
    """The core regression-safety guarantee."""
    ctx, canonical, render_dir = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    scope.code_path.write_text("# WORSE repair\n", encoding="utf-8")
    (scope.render_dir / "manifest.json").write_text("[]", encoding="utf-8")

    workspace.discard(ctx, scope)

    assert canonical.read_text(encoding="utf-8") == ACCEPTED_SOURCE
    assert not scope.root.exists()
    assert ctx.candidate is None


def test_discard_does_not_advance_the_revision(tmp_path):
    """A rejected candidate did not change the scene, so nothing derived
    from it became stale."""
    ctx, canonical, _ = _project(tmp_path)
    lineage.record_program(ctx, final_mp4=None)

    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    scope.code_path.write_text("# worse\n", encoding="utf-8")

    assert workspace.discard(ctx, scope) == 1
    assert lineage.current_revision(ctx, "03") == 1
    assert not lineage.program_is_stale(ctx)


def test_discard_restores_artifacts_a_generator_repointed(tmp_path):
    """A generator repoints CodeArtifact.path at the candidate during
    evaluation; rejection must put the accepted record back."""
    ctx, canonical, _ = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    ctx.code_artifacts["03"] = CodeArtifact(
        stem="03", path=scope.code_path, accepted=True, revision=2
    )

    workspace.discard(ctx, scope)

    assert ctx.code_artifacts["03"].path == canonical
    assert ctx.code_artifacts["03"].revision == 1


def test_discard_removes_an_artifact_that_had_none_before(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    canonical = tmp_path / "build" / "scenes" / "scene_03.py"
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    ctx.code_artifacts["03"] = CodeArtifact(stem="03", path=scope.code_path)

    workspace.discard(ctx, scope)

    assert "03" not in ctx.code_artifacts


def test_discarded_snapshot_is_immune_to_later_mutation(tmp_path):
    """The restore point is a deep copy, so a generator mutating the live
    artifact in place cannot corrupt it."""
    ctx, canonical, _ = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)

    ctx.code_artifacts["03"].path = scope.code_path
    ctx.code_artifacts["03"].accepted = False

    workspace.discard(ctx, scope)

    assert ctx.code_artifacts["03"].path == canonical
    assert ctx.code_artifacts["03"].accepted is True


# ------------------------------------------------------------------ cleanup

def test_cleanup_is_safe_on_a_project_with_no_candidates(tmp_path):
    workspace.cleanup_candidates(tmp_path)
    workspace.cleanup_candidates(None)
    workspace.cleanup_candidates(tmp_path, "03")


def test_cleanup_removes_leftover_trees(tmp_path):
    ctx, canonical, _ = _project(tmp_path)
    scope = workspace.open_candidate(ctx, "03", canonical_code=canonical)
    scope.code_path.write_text("x", encoding="utf-8")

    workspace.cleanup_candidates(tmp_path)

    assert not scope.root.exists()
