"""Canonical per-scene report for report-driven Manim self-correction.

Every verification produces a machine-readable report at:

    build/reports/scenes/<scene_id>.json          # latest
    build/revisions/<scene_id>/revision_<N>/report.json  # per-revision

The report normalizes all verifier findings into a single structure
preserving evidence, while also separating layout/semantic/visual
dimensions and deriving recommended_actions.

This is the evidence that the generator must consume on the next
revision -- not a generic "fix it" string.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .context import SceneContext
from .scene_quality import SceneQuality, classify

REPORT_SCHEMA_VERSION = "1.0"


def _is_blocking(f: dict[str, Any]) -> bool:
    return classify(f) == "blocking"


def _is_warning(f: dict[str, Any]) -> bool:
    return classify(f) == "warning"


def _group_findings(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {"layout": [], "semantic": [], "visual": [], "other": []}
    for f in findings:
        cat = str(f.get("category", "")).upper()
        if cat in ("LAYOUT", "SPATIAL"):
            groups["layout"].append(f)
        elif cat in ("SEMANTIC", "PEDAGOGY", "PEDAGOGICAL"):
            groups["semantic"].append(f)
        elif cat in ("SPATIAL", "VISUAL", "MOTION"):
            groups["visual"].append(f)
        else:
            # also route via finding_type
            ft = str(f.get("finding_type", "")).lower()
            if "layout" in ft or "overlap" in ft or "caption" in ft or "safe" in ft:
                groups["layout"].append(f)
            elif "semantic" in ft:
                groups["semantic"].append(f)
            else:
                groups["other"].append(f)
    return groups


def _quality_score(ctx: SceneContext, stem: str) -> float:
    """Normalized quality score 0..1 derived from SceneQuality."""
    q = SceneQuality.collect(ctx, stem)
    # Structural/layout/semantic/pedagogical/temporal scores are 0..100
    # Overall as weighted average; simpler: 1 - blocking*0.25 - warnings*0.05 capped
    # Use SceneQuality's own dimension scores for reproducibility.
    # For report we expose a single 0..1 score:
    #   1.0 when no blocking, ~0.5 when warnings, 0 when blocking
    if q.blocking > 0:
        return max(0.0, 0.72 - q.blocking * 0.15 - q.warnings * 0.03)
    if q.warnings > 0:
        return max(0.6, 0.92 - q.warnings * 0.05)
    return 0.95 if q.has_evidence else 0.5


def _recommended_actions(findings: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for f in findings:
        if not _is_blocking(f):
            continue
        cat = str(f.get("category", "")).upper()
        ft = str(f.get("finding_type", "")).lower()
        msg = str(f.get("detail") or f.get("message") or "").lower()
        # Layout
        if cat == "LAYOUT" or "caption" in ft or "caption" in msg:
            if "caption" in msg or "caption" in ft:
                cand = "Reserve bottom caption zone and move lower labels upward; keep caption inside safe area"
            elif "overlap" in ft or "overlap" in msg:
                cand = "Fix overlap by moving elements, wrapping text, and increasing vertical spacing; do not shrink everything"
            elif "safe" in msg or "offframe" in ft or "out_of_bounds" in msg:
                cand = "Move elements inside safe margins (x 0.4-15.6, y 0.4-8.6); restructure layout, wrap text"
            elif "crowd" in ft or "crowd" in msg:
                cand = "Reduce crowding by increasing spacing and moving supporting labels away from caption zone"
            else:
                cand = "Resolve layout violation by adjusting position/scale/spacing while preserving educational meaning"
        elif cat == "SEMANTIC":
            cand = "Correct semantic content to match narration; preserve layout for passing elements"
        elif cat == "SPATIAL":
            cand = "Fix spatial conflict; ensure elements do not intersect and remain readable"
        elif cat == "TEMPORAL":
            cand = "Adjust animation timing and self.wait gaps to match narration cues"
        else:
            cand = str(f.get("fix") or f.get("detail") or f.get("message") or "").strip()
            if not cand:
                continue
        if cand and cand not in seen:
            seen.add(cand)
            actions.append(cand)
    if not actions and findings:
        actions.append("Review blocking findings and apply targeted fixes without introducing regressions")
    return actions


def build_scene_report(ctx: SceneContext, stem: str, revision: int | None = None) -> dict[str, Any]:
    """Build canonical report for one scene at its current revision."""
    from .lineage import current_revision

    if revision is None:
        revision = current_revision(ctx, stem)
    else:
        revision = int(revision)
    # Collect all findings for this stem across all verifiers
    findings: list[dict[str, Any]] = []
    for results in (ctx.check_results or {}).values():
        if not isinstance(results, list):
            continue
        for f in results:
            if not isinstance(f, dict):
                continue
            owner = str(f.get("stem") or f.get("scene_id") or "")
            if owner == str(stem):
                findings.append(dict(f))

    blocking = [f for f in findings if _is_blocking(f)]
    status = "fail" if blocking else ("warn" if any(_is_warning(f) for f in findings) else "pass")

    groups = _group_findings(findings)
    q = SceneQuality.collect(ctx, stem)
    score = _quality_score(ctx, stem)

    # Layout detail: collect overlaps/overflow/safe_area_violations from layout findings
    layout_detail: dict[str, list[Any]] = {"overlaps": [], "overflow": [], "safe_area_violations": []}
    for f in groups["layout"]:
        ft = str(f.get("finding_type", "")).lower()
        lk = str(f.get("layout_subtype") or f.get("mismatch_subtype") or "").lower()
        if "overlap" in ft or "overlap" in lk or "caption_collision" in ft:
            layout_detail["overlaps"].append(f)
        if "overflow" in ft or "overflow" in lk or "text_overflow" in ft:
            layout_detail["overflow"].append(f)
        if "safe" in ft or "safe" in lk or "offframe" in ft or "out_of_bounds" in ft:
            layout_detail["safe_area_violations"].append(f)

    # Previous successful properties (findings that are pass)
    passing = [f for f in findings if classify(f) == "pass"]

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "scene_id": str(stem),
        "revision": int(revision),
        "status": status,
        "quality_score": round(float(score), 3),
        "findings": findings,
        "blocking_count": len(blocking),
        "warning_count": sum(1 for f in findings if _is_warning(f)),
        "layout": {
            "status": "fail" if any(_is_blocking(f) for f in groups["layout"]) else ("warn" if groups["layout"] else "pass"),
            "findings": groups["layout"],
            **layout_detail,
        },
        "semantic": {
            "status": "fail" if any(_is_blocking(f) for f in groups["semantic"]) else ("warn" if groups["semantic"] else "pass"),
            "findings": groups["semantic"],
        },
        "visual": {
            "status": "fail" if any(_is_blocking(f) for f in groups["visual"]) else ("warn" if groups["visual"] else "pass"),
            "findings": groups["visual"],
        },
        "recommended_actions": _recommended_actions(findings),
        "passing_properties": passing,
        "quality": q.to_dict(),
    }
    return report


def report_path(project_dir: Path | None, stem: str) -> Path:
    if project_dir is None:
        return Path("build") / "reports" / "scenes" / f"{stem}.json"
    return Path(project_dir) / "build" / "reports" / "scenes" / f"{stem}.json"


def revision_report_path(project_dir: Path | None, stem: str, revision: int) -> Path:
    if project_dir is None:
        return Path("build") / "revisions" / str(stem) / f"revision_{int(revision):02d}" / "report.json"
    return Path(project_dir) / "build" / "revisions" / str(stem) / f"revision_{int(revision):02d}" / "report.json"


def write_scene_report(ctx: SceneContext, stem: str, revision: int | None = None) -> Path | None:
    """Write canonical report for one scene. Never raises."""
    try:
        report = build_scene_report(ctx, stem, revision=revision)
        project_dir = getattr(ctx, "project_dir", None)
        # latest
        path = report_path(project_dir, stem)
        # Only overwrite latest when this is the current revision or newer
        # During a repair candidate we still want to keep the *candidate* report
        # separate so the next generation sees the candidate's own findings.
        # The caller decides whether to treat this as latest (initial) or
        # candidate (explicit revision). Here we always write latest as well
        # for simplicity; the candidate's report will be written with its own
        # revision number to the per-revision path, and the next repair will
        # read the latest which after a REJECT is still the accepted one.
        path.parent.mkdir(parents=True, exist_ok=True)
        # For candidate writes we do NOT overwrite the latest accepted report
        # when revision is a future candidate that hasn't been accepted yet.
        # Detect: if revision is provided and differs from current, write only
        # the per-revision copy, not the latest.
        from .lineage import current_revision as _cur
        cur = int(_cur(ctx, stem))
        is_candidate_write = revision is not None and int(revision) != cur
        if not is_candidate_write:
            path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        # per-revision copy
        rev = int(report.get("revision", 0))
        rev_path = revision_report_path(project_dir, stem, rev)
        rev_path.parent.mkdir(parents=True, exist_ok=True)
        rev_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        return rev_path if is_candidate_write else path
    except Exception:
        return None


def load_scene_report(project_dir: Path | None, stem: str) -> dict[str, Any] | None:
    """Load latest report for a stem. Never raises."""
    try:
        p = report_path(project_dir, stem)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def archive_revision(
    ctx: SceneContext,
    stem: str,
    revision: int | None = None,
) -> Path | None:
    """Archive source + render + preview + report for one revision.

    Writes to ``build/revisions/<stem>/revision_<N>/`` preserving the four
    artifacts the spec requires to remain available for every evaluated
    revision. Never raises.
    """
    try:
        from .lineage import current_revision as _cur
        import shutil

        rev = int(revision) if revision is not None else int(_cur(ctx, stem))
        project_dir = getattr(ctx, "project_dir", None)
        if project_dir is None:
            return None
        dest = Path(project_dir) / "build" / "revisions" / str(stem) / f"revision_{rev:02d}"
        dest.mkdir(parents=True, exist_ok=True)

        # Source
        art = (getattr(ctx, "code_artifacts", {}) or {}).get(str(stem))
        if art is not None and getattr(art, "path", None) is not None:
            src = Path(art.path)
            if src.exists():
                try:
                    shutil.copyfile(src, dest / src.name)
                except Exception:
                    pass

        # Render (clip)
        rend = (getattr(ctx, "render_artifacts", {}) or {}).get(str(stem))
        if rend is not None:
            clip = rend.clip_path() if hasattr(rend, "clip_path") else getattr(rend, "clip", None)
            if clip is not None and Path(clip).exists():
                try:
                    shutil.copyfile(Path(clip), dest / Path(clip).name)
                except Exception:
                    pass
            # Also copy manifest if exists
            manifest_src = None
            outdir = getattr(rend, "outdir", None)
            if outdir is not None:
                cand = Path(outdir) / "manifest.json"
                if cand.exists():
                    manifest_src = cand
            if manifest_src:
                try:
                    shutil.copyfile(manifest_src, dest / "manifest.json")
                except Exception:
                    pass

        # Preview
        try:
            from .preview import canonical_preview_path, preview_path_for
            # Prefer candidate-aware when open, otherwise canonical
            try:
                from . import workspace as _ws
                if _ws.is_candidate_open(ctx, stem):
                    pp = preview_path_for(ctx, stem)
                else:
                    pp = canonical_preview_path(project_dir, stem)
            except Exception:
                pp = canonical_preview_path(project_dir, stem)
            if pp.exists():
                try:
                    shutil.copyfile(pp, dest / pp.name)
                except Exception:
                    pass
        except Exception:
            pass

        # Report (ensure it exists)
        try:
            write_scene_report(ctx, stem)
            src_report = report_path(project_dir, stem)
            if src_report.exists():
                shutil.copyfile(src_report, dest / "report.json")
        except Exception:
            pass

        return dest
    except Exception:
        return None


def build_repair_context(
    *,
    stem: str,
    revision: int,
    report: dict[str, Any] | None,
    current_source: str | None,
    previous_source: str | None = None,
    preview_available: bool = False,
    best_report: dict[str, Any] | None = None,
    backend: str = "Manim",
) -> str:
    """Construct the report-conditioned repair prompt fragment.

    This is the exact text that must be injected into the next generation
    prompt. It is built dynamically from the report, not hard-coded.
    """
    if report is None:
        return ""

    blocking = [f for f in report.get("findings", []) if classify(f) == "blocking"]
    if not blocking:
        return ""

    lines: list[str] = []
    lines.append(f"SCENE REVISION CONTEXT -- Scene {stem} revision {revision}")
    lines.append("")
    lines.append(f"You are revising an existing {backend} educational scene. This scene has already been rendered and evaluated.")
    lines.append("You MUST use the verifier report below as evidence. Do not redesign the entire scene.")
    lines.append("")
    # Animation brief / narration are injected by the caller via the main prompt; we focus on report here
    lines.append("BLOCKING FINDINGS (must be fixed):")
    for f in blocking:
        msg = str(f.get("detail") or f.get("message") or f.get("reason") or "").strip()
        cat = str(f.get("category", "")).strip()
        fid = str(f.get("finding_id", "")).strip()
        lines.append(f"- [{cat} {fid}] {msg}")
        ev = f.get("evidence") or f.get("recorded_problem") or f.get("detail")
        if isinstance(ev, list):
            for e in ev[:2]:
                if str(e).strip():
                    lines.append(f"  evidence: {str(e).strip()[:300]}")
        elif isinstance(ev, str) and ev.strip() and ev.strip() != msg:
            lines.append(f"  evidence: {ev.strip()[:300]}")
        fix = str(f.get("fix") or "").strip()
        if fix:
            lines.append(f"  fix: {fix[:300]}")

    rec = report.get("recommended_actions", [])
    if rec:
        lines.append("")
        lines.append("REQUIRED REPAIRS:")
        for a in rec[:6]:
            lines.append(f"- {a}")

    # Previous successful properties
    passing = report.get("passing_properties", [])
    if passing:
        lines.append("")
        lines.append("PREVIOUSLY PASSING (do not undo):")
        for p in passing[:4]:
            detail = str(p.get("detail") or p.get("message") or "").strip()[:200]
            if detail:
                lines.append(f"- {detail}")

    lines.append("")
    lines.append("CONSTRAINTS:")
    # Determine mutability from category
    has_semantic = any(str(f.get("category","")).upper() == "SEMANTIC" for f in blocking)
    has_layout = any(str(f.get("category","")).upper() in ("LAYOUT","SPATIAL") for f in blocking)
    if has_layout and not has_semantic:
        lines.append("- CONTENT CONSTRAINTS: preserve equations, values, labels, relationships, educational meaning, intended animation. Do NOT change mathematical/content semantics.")
        lines.append("- LAYOUT CONSTRAINTS: allowed to change position, scale, spacing, wrapping, grouping, timing where necessary for readability.")
    elif has_semantic and not has_layout:
        lines.append("- CONTENT CONSTRAINTS: you MAY change objects, values, labels, relationships to fix semantic mismatch.")
        lines.append("- LAYOUT CONSTRAINTS: preserve safe areas and caption zone where possible; keep layout coherent.")
    else:
        lines.append("- Preserve educational semantics unless explicitly identified as incorrect.")
        lines.append("- Preserve passing components; modify only components implicated by the report.")

    lines.append("- Do not introduce new overlaps, safe-area violations, or unreadable text.")
    lines.append("- Maintain title/main-visual/supporting-labels/caption zones and safe margins.")
    lines.append("- Keep caption inside caption zone, readable font, wrapped if long.")
    lines.append(f"- Generate the corrected {backend} source only.")

    if preview_available:
        lines.append("")
        lines.append("A preview image of the current rendering is provided alongside this report. Use it as visual evidence.")

    # Include source snippet hint (not the full source here; caller appends source separately)
    # This fragment is appended to extra_feedback, which already sits after the full prompt that
    # contains the current source when provided by the caller.

    return "\n".join(lines)


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "build_scene_report",
    "write_scene_report",
    "load_scene_report",
    "build_repair_context",
    "report_path",
    "revision_report_path",
]
