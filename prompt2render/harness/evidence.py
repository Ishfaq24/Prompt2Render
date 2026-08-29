"""Artifact-centric evidence bundles, change contracts, and repair scopes.

The brief's core invariant:

    THE VERIFICATION REPORT MUST BECOME ACTIONABLE MEMORY FOR THE NEXT
    REGENERATION.

A scene regeneration therefore never receives an undifferentiated "fix it"
blob. Before every repair the controller assembles:

1. an **evidence bundle** -- what failed, where, why, and what already
   passed (and must therefore remain unchanged);
2. a **change contract** -- the machine-readable problems/targets/
   required_changes/preserve/success_conditions/forbidden_changes the
   generator must honor;
3. a **repair scope** -- LOCAL / REGIONAL / SCENE, defaulting to the
   smallest scope the findings support (PATCH > PARTIAL > FULL).

This module is taxonomy and serialization only (the same discipline as
:mod:`finding`): it builds and persists the structures, it never mutates
pipeline state. Routing stays in ``repair_router``; acceptance stays in
``repair_controller``.

Per-revision artifacts land next to the existing ``report.json`` archive
(see :mod:`scene_report`):

    build/revisions/<stem>/revision_<N>/
        evidence.json        # this module's bundle
        repair.json          # the change contract used for this revision
        generation.json      # model/hashes/timestamps for this revision
    build/revisions/<stem>/accepted/
        manifest.json        # pointer at the accepted revision
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .context import SceneContext
from .scene_quality import SceneQuality, classify

EVIDENCE_SCHEMA_VERSION = "1.0"
CONTRACT_SCHEMA_VERSION = "1.0"
GENERATION_SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Repair scopes and typed failure routing (Phase 5/7)
# ---------------------------------------------------------------------------

SCOPE_LOCAL = "LOCAL"
SCOPE_REGIONAL = "REGIONAL"
SCOPE_SCENE = "SCENE"

#: finding_type -> repair strategy label. This is the centralized
#: failure-to-repair map: nothing downstream sends an undifferentiated
#: report to the generator; the contract builder reads these labels.
REPAIR_TYPE_BY_FINDING_TYPE: dict[str, str] = {
    # Execution / code-level
    "execution_failure": "code_local_repair",
    "undefined_identifier": "code_local_repair",
    "undefined_method": "manim_api_repair",
    "execution_trace_failure": "code_local_repair",
    "invalid_manim_api": "manim_api_repair",
    "manim_crash": "manim_api_repair",
    "stills_render_failure": "code_local_repair",
    "render_failure": "code_local_repair",
    # Layout / typography
    "layout_violation": "layout_repair",
    "layout_warning": "layout_repair",
    "layout_audit": "layout_repair",
    "spatial_audit": "layout_repair",
    "spatial_conflict": "layout_repair",
    "layout_overflow": "layout_repair",
    "text_overflow": "typography_repair",
    "text_overlap": "typography_repair",
    "overlap": "layout_repair",
    "crowding": "layout_repair",
    "out_of_bounds": "layout_repair",
    "caption_collision": "caption_layout_repair",
    "caption_overflow": "caption_layout_repair",
    # Semantic / content
    "semantic_mismatch": "semantic_repair",
    "semantic_plan_failure": "semantic_repair",
    "missing_visual_concept": "scene_content_repair",
    "storyboard_failure": "scene_content_repair",
    # Temporal
    "timing_mismatch": "timing_repair",
    "temporal_mismatch": "timing_repair",
    # Pedagogy / visual quality
    "pedagogy_review": "pedagogical_repair",
    "motion_absence": "visual_refinement",
    "vlm_post_render_defect": "visual_refinement",
    # Whole-video / other
    "audio_visual_mismatch": "semantic_repair",
    "verification_unavailable": "verification_repair",
    "stage_exception": "verification_repair",
    "feedback_hitl": "code_local_repair",
}

#: finding classes repairable by touching only the implicated lines.
_LOCAL_FINDING_TYPES = {
    "execution_failure",
    "undefined_identifier",
    "undefined_method",
    "invalid_manim_api",
    "manim_crash",
    "execution_trace_failure",
    "caption_overflow",
    "caption_collision",
    "text_overflow",
}

#: finding classes that act on one zone/component, not the whole concept.
_REGIONAL_FINDING_TYPES = {
    "layout_violation",
    "layout_warning",
    "layout_audit",
    "spatial_audit",
    "spatial_conflict",
    "layout_overflow",
    "text_overlap",
    "overlap",
    "crowding",
    "out_of_bounds",
    "timing_mismatch",
    "temporal_mismatch",
    "motion_absence",
}

#: finding classes whose fix may legitimately restructure the scene.
_SCENE_FINDING_TYPES = {
    "semantic_mismatch",
    "semantic_plan_failure",
    "missing_visual_concept",
    "storyboard_failure",
    "pedagogy_review",
}


def repair_type_for(finding: dict[str, Any]) -> str:
    """The repair strategy label for one finding."""

    explicit = str(finding.get("repair_type") or "").strip()

    if explicit:
        return explicit

    finding_type = str(finding.get("finding_type") or "").strip()

    return REPAIR_TYPE_BY_FINDING_TYPE.get(finding_type, "scene_content_repair")


def classify_repair_scope(findings: list[dict[str, Any]]) -> str:
    """Smallest repair scope the reported findings support.

    Preference order is PATCH > PARTIAL REGENERATION > FULL REGENERATION,
    encoded as LOCAL > REGIONAL > SCENE:

    - any semantic/conceptual failure forces SCENE (the concept is wrong,
      not the pixels);
    - otherwise layout/temporal/motion failures are REGIONAL (one zone or
      component changes, the rest is preserved);
    - otherwise (code-local / typography failures, or findings carrying
      explicit line locations) the scope is LOCAL.
    """

    cleaned = [f for f in findings or [] if isinstance(f, dict)]

    if not cleaned:
        return SCOPE_LOCAL

    types = {str(f.get("finding_type") or "").strip() for f in cleaned}

    if types & _SCENE_FINDING_TYPES:
        return SCOPE_SCENE

    if types & _REGIONAL_FINDING_TYPES:
        return SCOPE_REGIONAL

    if types & _LOCAL_FINDING_TYPES:
        return SCOPE_LOCAL

    # Unknown finding types with a precise location are still localizable.
    if all(f.get("location") for f in cleaned):
        return SCOPE_LOCAL

    return SCOPE_SCENE


# ---------------------------------------------------------------------------
# Dimension (check) model
# ---------------------------------------------------------------------------

#: quality dimension -> verifier plugins whose evidence feeds it.
CHECK_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "syntax": ("verifier_execution",),
    "execution": ("verifier_execution",),
    "layout": ("verifier_layout", "verifier_spatial"),
    "visual": ("observer_visual", "verifier_motion"),
    "semantic": ("verifier_semantic", "verifier_storyboard"),
    "pedagogy": ("verifier_pedagogy",),
    "temporal": ("verifier_temporal", "verifier_lifecycle"),
}

#: what a locked (passing) dimension must preserve in the next revision.
PRESERVE_BY_DIMENSION: dict[str, list[str]] = {
    "syntax": ["module syntax"],
    "execution": ["executable scene structure"],
    "layout": [
        "object positions",
        "caption position",
        "font sizes",
        "safe areas",
    ],
    "visual": [
        "visual hierarchy",
        "known-good composition",
    ],
    "semantic": [
        "equations",
        "values and labels",
        "object relationships",
    ],
    "pedagogy": [
        "narrative progression",
        "teaching examples",
    ],
    "temporal": [
        "animation timing",
        "narration cue alignment",
    ],
}


def _scene_findings(context: SceneContext, stem: str) -> list[dict[str, Any]]:
    """Every finding recorded against one scene, across all verifiers."""

    target = str(stem)
    found: list[dict[str, Any]] = []

    for results in (context.check_results or {}).values():
        if not isinstance(results, list):
            continue

        for finding in results:
            if not isinstance(finding, dict):
                continue

            owner = str(finding.get("stem") or finding.get("scene_id") or "")

            if owner == target:
                found.append(finding)

    return found


def _check_status(findings: list[dict[str, Any]]) -> str:
    """pass / warn / fail / skip for one dimension's findings."""

    buckets = {classify(f) for f in findings}

    if "blocking" in buckets:
        return "fail"

    if "warning" in buckets:
        return "warn"

    if "pass" in buckets:
        return "pass"

    return "skip"


def dimension_findings(
    context: SceneContext,
    stem: str,
    dimension: str,
) -> list[dict[str, Any]]:
    """Findings feeding one check dimension for one scene."""

    plugins = CHECK_DIMENSIONS.get(dimension, ())
    owners = {str(p) for p in plugins}
    results: list[dict[str, Any]] = []

    for plugin_name, entries in (context.check_results or {}).items():
        if str(plugin_name) not in owners or not isinstance(entries, list):
            continue

        for finding in entries:
            if not isinstance(finding, dict):
                continue

            if str(finding.get("stem") or finding.get("scene_id") or "") == str(stem):
                results.append(finding)

    return results


# ---------------------------------------------------------------------------
# Evidence bundle (Phase 4)
# ---------------------------------------------------------------------------

def build_evidence_bundle(
    context: SceneContext,
    stem: str,
    revision: int | None = None,
) -> dict[str, Any]:
    """Assemble the structured evidence for one scene at one revision.

    Common schema with verifier-specific evidence preserved: findings keep
    every extra key their verifier attached (``bbox``, ``safe_area``,
    ``fix``, ``evidence`` ...), so the bundle normalizes without flattening.
    """

    from .lineage import current_revision

    if revision is None:
        revision = current_revision(context, stem)

    all_findings = _scene_findings(context, stem)

    checks: dict[str, str] = {}
    locked: dict[str, bool] = {}

    for dimension in CHECK_DIMENSIONS:
        status = _check_status(dimension_findings(context, stem, dimension))
        checks[dimension] = status
        locked[dimension] = status == "pass"

    blocking = [f for f in all_findings if classify(f) == "blocking"]
    warnings = [f for f in all_findings if classify(f) == "warning"]
    passing = [f for f in all_findings if classify(f) == "pass"]

    status = "fail" if blocking else ("warn" if warnings else "pass")

    must_preserve: list[str] = []

    for dimension, is_locked in locked.items():
        if not is_locked:
            continue

        for item in PRESERVE_BY_DIMENSION.get(dimension, []):
            if item not in must_preserve:
                must_preserve.append(item)

    findings = [
        {**finding, "repair_type": repair_type_for(finding)}
        for finding in all_findings
    ]

    quality = SceneQuality.collect(context, stem)

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "scene_id": str(stem),
        "revision": int(revision),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "checks": checks,
        "findings": findings,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
        "passing_properties": sorted(
            dimension for dimension, ok in locked.items() if ok
        ),
        "locked_properties": locked,
        "must_preserve": must_preserve,
        "recommended_actions": _recommended_actions(blocking),
        "quality": quality.to_dict(),
    }


def _recommended_actions(blocking: list[dict[str, Any]]) -> list[str]:
    """Explicit fixes recorded on findings first, generic guidance last."""

    actions: list[str] = []

    for finding in blocking:
        fix = str(finding.get("fix") or finding.get("recommended_fix") or "").strip()

        if fix and fix not in actions:
            actions.append(fix)
            continue

        message = str(finding.get("detail") or finding.get("message") or "").strip()

        if message and message not in actions:
            actions.append(message)

    if not actions:
        actions.append(
            "resolve the blocking findings with the smallest safe change"
        )

    return actions


# ---------------------------------------------------------------------------
# Change contract (Phase 6)
# ---------------------------------------------------------------------------

def _finding_location(finding: dict[str, Any], stem: str) -> str:
    location = finding.get("location")

    if isinstance(location, dict):
        file_name = str(location.get("file") or f"scene_{stem}.py")
        line = location.get("line")

        if line is not None:
            return f"{file_name} line {line}"

        return file_name

    line = finding.get("line")

    if line is not None:
        return f"scene_{stem}.py line {line}"

    return f"scene_{stem}.py"


def build_change_contract(
    *,
    stem: str,
    parent_revision: int,
    findings: list[dict[str, Any]],
    bundle: dict[str, Any] | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """Machine-readable change contract for the next regeneration.

    ``findings`` are the blocking findings that triggered the repair;
    ``bundle`` is the full evidence bundle of the (accepted) parent
    revision, used for preserve/locked/success terms. Pass ``scope`` to
    override :func:`classify_repair_scope`.
    """

    blocking = [
        f for f in findings or []
        if isinstance(f, dict) and classify(f) == "blocking"
    ] or [f for f in findings or [] if isinstance(f, dict)]

    scope = scope or classify_repair_scope(blocking)

    problems: list[str] = []
    targets: list[str] = []
    required_changes: list[str] = []

    for finding in blocking:
        message = str(
            finding.get("detail") or finding.get("message") or "unspecified defect"
        ).strip()

        if message not in problems:
            problems.append(message)

        target = _finding_location(finding, stem)

        if target not in targets:
            targets.append(target)

        fix = str(finding.get("fix") or "").strip()

        if fix and fix not in required_changes:
            required_changes.append(fix)

    if not required_changes:
        required_changes = [
            f"resolve: {problem}" for problem in problems
        ]

    locked = dict((bundle or {}).get("locked_properties") or {})
    must_preserve = list((bundle or {}).get("must_preserve") or [])

    preserve = list(must_preserve)

    for extra in ("all verified layout", "previously passing properties"):
        if extra not in preserve:
            preserve.append(extra)

    success_conditions = [
        "the reported failures no longer occur",
        "execution passes",
    ]

    success_conditions.extend(
        f"{dimension} remains passing"
        for dimension, is_locked in sorted(locked.items())
        if is_locked
    )

    forbidden = [
        "do not redesign the scene unless the failure explicitly requires redesign",
        "do not modify properties that already passed verification",
        "do not move unrelated objects",
        "do not introduce unrelated modifications",
    ]

    if scope == SCOPE_LOCAL:
        forbidden.append(
            "change only the code implicated by the reported findings"
        )

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "scene_id": str(stem),
        "parent_revision": int(parent_revision),
        "repair_scope": scope,
        "problems": problems,
        "targets": targets,
        "required_changes": required_changes,
        "preserve": preserve,
        "locked_properties": locked,
        "success_conditions": success_conditions,
        "forbidden_changes": forbidden,
    }


def contract_prompt_text(contract: dict[str, Any]) -> str:
    """Render a change contract as the prompt fragment the generator sees."""

    if not isinstance(contract, dict) or not contract.get("problems"):
        return ""

    lines: list[str] = []
    lines.append(
        f"CHANGE CONTRACT -- scene {contract.get('scene_id')} "
        f"(parent revision {contract.get('parent_revision')}, "
        f"scope {contract.get('repair_scope', SCOPE_SCENE)})"
    )
    lines.append("")
    lines.append("PROBLEMS (must be fixed):")
    lines.extend(f"- {problem}" for problem in contract.get("problems", []))
    lines.append("")
    lines.append("TARGETS:")
    lines.extend(f"- {target}" for target in contract.get("targets", []))
    lines.append("")
    lines.append("REQUIRED CHANGES:")
    lines.extend(f"- {change}" for change in contract.get("required_changes", []))
    lines.append("")
    lines.append("PRESERVE (already verified -- do not change):")
    lines.extend(f"- {item}" for item in contract.get("preserve", []))

    locked = contract.get("locked_properties") or {}
    locked_names = sorted(name for name, ok in locked.items() if ok)

    if locked_names:
        lines.append("")
        lines.append(f"LOCKED PROPERTIES: {', '.join(locked_names)}")

    lines.append("")
    lines.append("SUCCESS CONDITIONS:")
    lines.extend(f"- {item}" for item in contract.get("success_conditions", []))
    lines.append("")
    lines.append("FORBIDDEN:")
    lines.extend(f"- {item}" for item in contract.get("forbidden_changes", []))
    lines.append("")
    lines.append(
        "Preserve all properties that already passed verification. Modify "
        "only what is necessary to resolve the reported failures. Fix the "
        "reported failure with the smallest safe change."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def revision_dir(project_dir: Path | None, stem: str, revision: int) -> Path:
    """``build/revisions/<stem>/revision_<N>/`` (matches scene_report)."""

    base = Path(project_dir) if project_dir is not None else Path(".")

    return base / "build" / "revisions" / str(stem) / f"revision_{int(revision):02d}"


def _write_json(path: Path, payload: dict[str, Any]) -> Path | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def write_evidence_bundle(
    project_dir: Path | None,
    stem: str,
    revision: int,
    bundle: dict[str, Any],
) -> Path | None:
    """Persist ``evidence.json`` for one revision. Never raises."""

    if project_dir is None:
        return None

    return _write_json(
        revision_dir(project_dir, stem, revision) / "evidence.json",
        bundle,
    )


def write_change_contract(
    project_dir: Path | None,
    stem: str,
    revision: int,
    contract: dict[str, Any],
) -> Path | None:
    """Persist ``repair.json`` (the contract this revision was built under)."""

    if project_dir is None:
        return None

    return _write_json(
        revision_dir(project_dir, stem, revision) / "repair.json",
        contract,
    )


def write_generation_meta(
    project_dir: Path | None,
    stem: str,
    revision: int,
    meta: dict[str, Any],
) -> Path | None:
    """Persist ``generation.json`` (provenance for one revision)."""

    if project_dir is None:
        return None

    payload = {"schema_version": GENERATION_SCHEMA_VERSION, **meta}

    return _write_json(
        revision_dir(project_dir, stem, revision) / "generation.json",
        payload,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path: Path | str) -> str | None:
    """SHA-256 of a file, or ``None`` when unreadable."""

    try:
        digest = hashlib.sha256()

        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()
    except OSError:
        return None


def build_generation_meta(
    context: SceneContext,
    stem: str,
    *,
    revision: int,
    parent_revision: int,
    model_env: str = "",
    model_primary: str = "",
    trigger_finding_type: str = "",
    fallbacks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Provenance record for one revision: hashes, model, parent linkage."""

    code = (context.code_artifacts or {}).get(str(stem))
    source_hash = None

    if code is not None and getattr(code, "path", None) is not None:
        source_hash = sha256_file(Path(code.path))

    spec_hash = None

    try:
        entry = next(
            (e for e in context.scene_plan if str(getattr(e, "stem", "")) == str(stem)),
            None,
        )

        if entry is not None:
            spec_text = json.dumps(
                {
                    "anim": getattr(entry, "anim", None),
                    "title": getattr(entry, "title", None),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            spec_hash = sha256_text(spec_text)
    except Exception:
        spec_hash = None

    return {
        "scene_id": str(stem),
        "revision": int(revision),
        "parent_revision": int(parent_revision),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_env": str(model_env or ""),
        "model_primary": str(model_primary or ""),
        "fallbacks": list(fallbacks or []),
        "source_sha256": source_hash,
        "spec_sha256": spec_hash,
        "trigger_finding_type": str(trigger_finding_type or ""),
    }


def sync_accepted_dir(context: SceneContext, stem: str) -> Path | None:
    """Maintain ``build/revisions/<stem>/accepted/`` for one scene.

    Copies only small artifacts (source, report, evidence); heavy render
    files stay in the revision directory and are referenced by path. Never
    raises -- the accepted pointer is explanatory, and the canonical files
    under ``build/scenes``/``build/manim`` remain authoritative.
    """

    try:
        from .lineage import current_revision

        project_dir = getattr(context, "project_dir", None)

        if project_dir is None:
            return None

        accepted_revision = int(current_revision(context, stem))

        if accepted_revision <= 0:
            return None

        src_dir = revision_dir(project_dir, stem, accepted_revision)
        dest_dir = Path(project_dir) / "build" / "revisions" / str(stem) / "accepted"
        dest_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "scene_id": str(stem),
            "accepted_revision": accepted_revision,
            "revision_dir": str(src_dir),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        import shutil

        for name in ("report.json", "evidence.json", "repair.json", "generation.json"):
            src = src_dir / name

            if src.exists():
                try:
                    shutil.copyfile(src, dest_dir / name)
                    manifest[name] = str(dest_dir / name)
                except OSError:
                    pass

        code = (context.code_artifacts or {}).get(str(stem))

        if code is not None and getattr(code, "path", None) is not None:
            source = Path(code.path)

            if source.exists():
                try:
                    shutil.copyfile(source, dest_dir / source.name)
                    manifest["source"] = str(dest_dir / source.name)
                    manifest["source_sha256"] = sha256_file(source)
                except OSError:
                    pass

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

            if clip is not None and Path(clip).exists():
                # Reference only -- never duplicate the render artifact.
                manifest["render"] = str(clip)

        _write_json(dest_dir / "manifest.json", manifest)

        return dest_dir
    except Exception:
        return None


__all__ = [
    "CHECK_DIMENSIONS",
    "CONTRACT_SCHEMA_VERSION",
    "EVIDENCE_SCHEMA_VERSION",
    "PRESERVE_BY_DIMENSION",
    "REPAIR_TYPE_BY_FINDING_TYPE",
    "SCOPE_LOCAL",
    "SCOPE_REGIONAL",
    "SCOPE_SCENE",
    "build_change_contract",
    "build_evidence_bundle",
    "build_generation_meta",
    "classify_repair_scope",
    "contract_prompt_text",
    "dimension_findings",
    "repair_type_for",
    "revision_dir",
    "sha256_file",
    "sha256_text",
    "sync_accepted_dir",
    "write_change_contract",
    "write_evidence_bundle",
    "write_generation_meta",
]
