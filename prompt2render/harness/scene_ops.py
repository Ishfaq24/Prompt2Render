"""Single-scene operations behind the verify/repair/revisions/rollback/replay
CLI commands (Phase 22).

Everything here works against a project's on-disk state -- no full pipeline
run, no LLM unless a repair genuinely regenerates code. The context is
reconstructed from ``script.md``, the revision history, and the build
directories, which is precisely the subset of state these operations need
(``cmd_harness`` remains the owner of full builds).

    verify   deterministic verification of one scene's current artifacts
    repair   one repair-controller cycle for one scene's blocking findings
    rollback restore an archived revision as the accepted one
    replay   deterministic re-render + re-verify, no LLM
"""

from __future__ import annotations

import ast
import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import evidence
from .context import (
    CodeArtifact,
    NarrationEntry,
    RenderArtifact,
    SceneContext,
    ScenePlanEntry,
)
from .lineage import current_revision
from .revision_history import (
    RevisionEntry,
    load_revision_history,
    record_revision,
)
from .scene_quality import classify


# ---------------------------------------------------------------------------
# Context reconstruction
# ---------------------------------------------------------------------------

def _scene_source_candidates(project_dir: Path, stem: str) -> list[Path]:
    return [
        project_dir / "build" / "scenes" / f"scene_{stem}.py",
        project_dir / "build" / "manim" / f"scene_{stem}.py",
    ]


def find_scene_source(project_dir: Path, stem: str) -> Path | None:
    for candidate in _scene_source_candidates(project_dir, stem):
        if candidate.exists():
            return candidate

    return None


def _is_manim_text(text: str) -> bool:
    lower = text.lower()

    return ("from manim import" in lower or "import manim" in lower) and (
        "class scene" in lower or "(scene)" in lower
    )


def reconstruct_context(project_dir: Path) -> SceneContext:
    """Rebuild the subset of SceneContext these operations need.

    Scene plan from ``script.md``, revisions from ``revisions.json``,
    artifacts from the build directories, narration from alignment output.
    """

    from ..project import parse_script

    project_dir = Path(project_dir)
    script_path = project_dir / "script.md"

    ctx = SceneContext(project_dir=project_dir, prompt=script_path)

    if script_path.exists():
        try:
            script = parse_script(script_path)
            ctx.scene_plan = [
                ScenePlanEntry(
                    index=sec.index,
                    stem=sec.stem,
                    title=sec.title,
                    anim=sec.anim,
                    narration_text=sec.narration,
                )
                for sec in script.sections
            ]
        except (Exception, SystemExit):
            ctx.scene_plan = []

    history = load_revision_history(project_dir)

    for stem, scene in (history.get("scenes") or {}).items():
        revision = int(scene.get("current", 0) or 0)

        if revision <= 0:
            continue

        ctx.scene_versions[str(stem)] = revision

        source = find_scene_source(project_dir, str(stem))

        if source is not None:
            ctx.code_artifacts[str(stem)] = CodeArtifact(
                stem=str(stem),
                path=source,
                generated=True,
                accepted=(revision == int(scene.get("accepted", 0) or 0)),
                revision=revision,
            )

        manifest_path = (
            project_dir / "build" / "scenes" / str(stem) / "manifest.json"
        )

        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = []

            ctx.render_artifacts[str(stem)] = RenderArtifact(
                stem=str(stem),
                outdir=manifest_path.parent,
                manifest=manifest if isinstance(manifest, list) else [],
                source_revision=revision,
            )

    # Narration timing from alignment artifacts, when present.
    try:
        from .. import align

        for entry in ctx.scene_plan:
            try:
                data = align.load(project_dir, entry.stem)
                sentences = data.get("sentences") or []

                if sentences:
                    ctx.narration[entry.stem] = NarrationEntry(
                        stem=entry.stem, sentences=list(sentences)
                    )
            except (Exception, SystemExit):
                continue
    except Exception:
        pass

    return ctx


def _entry_for(ctx: SceneContext, stem: str) -> Any:
    for entry in ctx.scene_plan:
        if str(entry.stem) == str(stem):
            return entry

    # A scene without a script.md entry still needs a stem-bearing object
    # for the deterministic checks.
    try:
        index = int(str(stem).lstrip("0") or "0")
    except ValueError:
        index = 0

    return ScenePlanEntry(index=index, stem=str(stem), title=str(stem))


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def verify_scene(project_dir: Path, stem: str) -> dict[str, Any]:
    """Deterministically verify one scene's current artifacts.

    Runs the deterministic preflight (verifier_execution) and summarizes the
    persisted check results into a fresh scene report + evidence bundle.
    LLM-backed verifiers are deliberately not invoked here -- this command
    must stay cheap and reproducible.
    """

    from .plugins.verifier_execution import check_scene_artifact
    from .scene_report import report_path, write_scene_report

    project_dir = Path(project_dir)
    ctx = reconstruct_context(project_dir)
    entry = _entry_for(ctx, stem)

    source = find_scene_source(project_dir, str(stem))

    if source is None:
        return {
            "scene_id": str(stem),
            "status": "missing",
            "detail": f"no generated scene source for {stem!r}",
        }

    findings = check_scene_artifact(ctx, entry, gate=True)

    if not findings:
        # Preflight ran and found nothing: that is a pass, not an absence
        # of evidence. Record it so the checks map says so.
        findings = [
            {
                "stem": str(stem),
                "status": "pass",
                "finding_type": "stage_success",
                "category": "TECHNICAL",
                "severity": "INFO",
                "detail": "deterministic preflight passed",
            }
        ]

    ctx.check_results["verifier_execution"] = findings

    revision = current_revision(ctx, str(stem)) or 1

    # A scene on disk with no tracked history is at least revision 1;
    # seeding it keeps the latest-report write from being treated as a
    # candidate-only write.
    if ctx.scene_versions.get(str(stem), 0) < revision:
        ctx.scene_versions[str(stem)] = revision

    write_scene_report(ctx, str(stem), revision=revision)
    bundle = evidence.build_evidence_bundle(ctx, str(stem), revision=revision)
    evidence_path = evidence.write_evidence_bundle(
        project_dir, str(stem), revision, bundle
    )

    blocking = [f for f in findings if classify(f) == "blocking"]

    return {
        "scene_id": str(stem),
        "revision": int(revision),
        "status": bundle.get("status"),
        "checks": bundle.get("checks", {}),
        "blocking_count": len(blocking),
        "findings": findings,
        "report_path": str(report_path(project_dir, str(stem))),
        "evidence_path": str(evidence_path) if evidence_path else None,
    }


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

def rollback_scene(project_dir: Path, stem: str, revision: int) -> dict[str, Any]:
    """Restore an archived revision as the accepted scene.

    The revision's source snapshot is copied back onto the canonical path;
    ``revisions.json`` records the rollback and moves the accepted pointer.
    Render artifacts are intentionally NOT copied back -- the revision bump
    makes every downstream artifact stale, so the next harness run (or
    ``replay``) re-renders from the restored source.
    """

    project_dir = Path(project_dir)
    stem = str(stem)
    revision = int(revision)

    rev_dir = evidence.revision_dir(project_dir, stem, revision)
    archived_source = rev_dir / f"scene_{stem}.py"

    if not archived_source.exists():
        raise FileNotFoundError(
            f"no archived source for scene {stem} revision {revision} at "
            f"{archived_source} -- archived revisions live under "
            "build/revisions/<stem>/revision_<N>/"
        )

    text = archived_source.read_text(encoding="utf-8")
    canonical = (
        project_dir / "build" / "manim" / f"scene_{stem}.py"
        if _is_manim_text(text)
        else project_dir / "build" / "scenes" / f"scene_{stem}.py"
    )

    canonical.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(archived_source, canonical)

    history = load_revision_history(project_dir)
    scene_record = (history.get("scenes") or {}).get(stem, {})
    previous = int(scene_record.get("current", 0) or 0)

    entry = RevisionEntry(
        revision=revision,
        parent_revision=previous,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        reason=f"cli rollback to revision {revision}",
        decision="rollback",
    )
    record_revision(project_dir, stem, entry, accepted=True)

    # Keep the latest report consistent with the restored revision.
    archived_report = rev_dir / "report.json"

    if archived_report.exists():
        try:
            latest = (
                project_dir / "build" / "reports" / "scenes" / f"{stem}.json"
            )
            latest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archived_report, latest)
        except OSError:
            pass

    return {
        "scene_id": stem,
        "rolled_back_to": revision,
        "previous_revision": previous,
        "source": str(canonical),
        "note": (
            "render artifacts were not restored; re-run the harness or "
            "`replay` to re-render from the accepted source"
        ),
    }


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------

def _scene_class_name(source: Path) -> str | None:
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(
            (isinstance(base, ast.Name) and base.id == "Scene")
            or (isinstance(base, ast.Attribute) and base.attr == "Scene")
            for base in node.bases
        ):
            return node.name

    return None


def replay_scene(project_dir: Path, stem: str) -> dict[str, Any]:
    """Deterministically re-render and re-verify one scene -- no LLM.

    The stills path re-renders through ``stills.render_into``; the Manim
    path re-renders through ``visuals.manim_scene``. Either way the result
    is verified by the deterministic preflight and summarized exactly like
    ``verify``.
    """

    project_dir = Path(project_dir)
    stem = str(stem)

    source = find_scene_source(project_dir, stem)

    if source is None:
        return {
            "scene_id": stem,
            "status": "missing",
            "detail": f"no generated scene source for {stem!r}",
        }

    text = source.read_text(encoding="utf-8", errors="replace")
    rendered = False
    render_error = ""

    if _is_manim_text(text):
        scene_name = _scene_class_name(source)

        if scene_name is None:
            render_error = "no Scene subclass found in the archived source"
        else:
            try:
                from .. import visuals
                from ..project import parse_script

                script = parse_script(project_dir / "script.md")
                index = 0

                try:
                    index = int(stem.lstrip("0") or "0")
                except ValueError:
                    index = 0

                visuals.manim_scene(
                    project_dir, script, source, scene_name, index
                )
                rendered = True
            except (Exception, SystemExit) as exc:
                render_error = f"{type(exc).__name__}: {exc}"
    else:
        try:
            from .. import stills

            outdir = project_dir / "build" / "scenes" / stem
            outdir.mkdir(parents=True, exist_ok=True)
            stills.render_into(source, outdir, max_cue=None, strict=True)
            rendered = True
        except (Exception, SystemExit) as exc:
            render_error = f"{type(exc).__name__}: {exc}"

    result = verify_scene(project_dir, stem)
    result["replayed"] = rendered
    result["render_error"] = render_error

    return result


# ---------------------------------------------------------------------------
# repair
# ---------------------------------------------------------------------------

def repair_scene(
    project_dir: Path,
    stem: str,
    *,
    manim: bool = False,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one repair-controller cycle for one scene.

    The context is reconstructed from disk, every enabled scene-scoped
    verifier runs to collect findings, and the repair controller performs
    its full regression-safe cycle (generate candidate -> render ->
    re-verify -> judge -> accept or rollback). No unrelated scene is
    touched.
    """

    from .loader import build_plugins, build_repair_controller, load_config
    from .repair_controller import SCENE_OBSERVERS, SCENE_VERIFIERS
    from .journal import EventJournal
    from .finding import verification_unavailable, Category

    project_dir = Path(project_dir)
    stem = str(stem)

    ctx = reconstruct_context(project_dir)

    if find_scene_source(project_dir, stem) is None:
        return {
            "scene_id": stem,
            "decision": "missing",
            "detail": f"no generated scene source for {stem!r}",
        }

    # The generator's prerequisites are planning-stage facts; a CLI repair
    # against already-built artifacts supplies them directly.
    ctx.pedagogy_verified = True
    ctx.storyboard_verified = True

    if getattr(ctx, "animation_ir", None) is None:
        ctx.animation_ir = {}

    if getattr(ctx, "semantic_ir", None) is None:
        ctx.semantic_ir = {}

    config = load_config(config_path)

    if manim:
        config.setdefault("generator_code", {})["enabled"] = False
        config.setdefault("generator_manim", {})["enabled"] = True
        config.setdefault("renderer_stills", {})["enabled"] = False
        config.setdefault("renderer_manim", {})["enabled"] = True
        config.setdefault("observer_visual", {})["enabled"] = True
        config.setdefault("verifier_motion", {})["enabled"] = True
    else:
        config.setdefault("generator_manim", {})["enabled"] = False
        config.setdefault("renderer_manim", {})["enabled"] = False
        config.setdefault("observer_visual", {})["enabled"] = False
        config.setdefault("verifier_motion", {})["enabled"] = False

    plugins = build_plugins(config=config)
    plugins_by_name = {plugin.name: plugin for plugin in plugins}

    harness_dir = project_dir / "build" / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)

    controller = build_repair_controller(
        plugins,
        config=config,
        logger=None,
        log_path=harness_dir / "repair_log.jsonl",
        journal=EventJournal(harness_dir / "events.jsonl"),
    )

    if controller is None:
        return {
            "scene_id": stem,
            "decision": "unavailable",
            "detail": "repair controller could not be constructed",
        }

    controller.router.attach(plugins_by_name=plugins_by_name)

    # Collect findings: run every enabled scene-scoped verifier.
    for name in SCENE_OBSERVERS + SCENE_VERIFIERS:
        plugin = plugins_by_name.get(name)

        if plugin is None or not plugin.enabled():
            continue

        try:
            plugin.run(ctx)
        except (Exception, SystemExit) as exc:
            ctx.check_results.setdefault(name, []).append(
                verification_unavailable(
                    verifier=name,
                    stem=stem,
                    reason=f"{name} crashed: {type(exc).__name__}: {exc}",
                    category=Category.TECHNICAL,
                )
            )

    blocking: list[dict[str, Any]] = []
    source_plugin = "verifier_execution"

    for plugin_name, results in ctx.check_results.items():
        if not isinstance(results, list):
            continue

        for finding in results:
            if not isinstance(finding, dict):
                continue

            owner = str(finding.get("stem") or finding.get("scene_id") or "")

            if owner != stem or classify(finding) != "blocking":
                continue

            blocking.append(finding)
            source_plugin = str(plugin_name)

    if not blocking:
        return {
            "scene_id": stem,
            "decision": "no_findings",
            "detail": "no blocking findings for this scene; nothing to repair",
            "revision": current_revision(ctx, stem),
        }

    record = controller.repair_scene(
        ctx, stem, blocking, source_plugin, dry_run=dry_run
    )

    result = record.to_dict()
    result["scene_id"] = stem

    try:
        from .scene_report import write_scene_report

        write_scene_report(ctx, stem)
    except Exception:
        pass

    return result


__all__ = [
    "find_scene_source",
    "reconstruct_context",
    "repair_scene",
    "replay_scene",
    "rollback_scene",
    "verify_scene",
]
