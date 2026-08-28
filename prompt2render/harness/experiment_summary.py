"""Experiment summary for the Prompt2Render harness (section 19).

Aggregates all already-produced evidence into a single research-grade report:

* repair decisions (repair_controller)
* stage latency (log.jsonl)
* quality ledger (check_results + SceneQuality)
* verification completeness

Never introduces new instrumentation; every number is derived from data
structures the harness already writes. Pure aggregation, never raises.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .context import SceneContext
from .scene_quality import SceneQuality, classify

EXPERIMENT_SUMMARY_SCHEMA_VERSION = "1.0"


def _is_blocking(finding: Any) -> bool:
    return classify(finding) == "blocking"


def _is_warning(finding: Any) -> bool:
    return classify(finding) == "warning"


def _is_unavailable(finding: Any) -> bool:
    if not isinstance(finding, dict):
        return False
    ft = str(finding.get("finding_type", "")).strip()
    vs = str(finding.get("verifier_state", "")).strip()
    return ft == "verification_unavailable" or vs == "VERIFICATION_UNAVAILABLE"


def _is_render_failure(finding: Any) -> bool:
    if not isinstance(finding, dict):
        return False
    ft = str(finding.get("finding_type", "")).strip()
    return ft in {"manim_crash", "stills_render_failure", "render_failure", "execution_failure"}


def build_experiment_summary(
    ctx: SceneContext,
    decisions: list[Any] | None = None,
    *,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate a harness run into a single experiment summary.

    Pure function; never raises.
    """
    try:
        decisions = list(decisions or [])
        # scene counts
        scene_stems = set()
        if getattr(ctx, "scene_plan", None):
            scene_stems.update(str(e.stem) for e in ctx.scene_plan)
        if getattr(ctx, "scene_versions", None):
            scene_stems.update(str(k) for k, v in ctx.scene_versions.items() if v and int(v) > 0)
        total_scenes = len(scene_stems)

        # per-scene blocking status
        successful_scenes = 0
        failed_scenes = 0
        for stem in scene_stems:
            q = SceneQuality.collect(ctx, stem)
            if q.blocking == 0 and not any(
                isinstance(f, dict) and str(f.get("stem") or f.get("scene_id") or "") == stem and _is_unavailable(f)
                for results in ctx.check_results.values() for f in (results or [])
            ):
                successful_scenes += 1
            else:
                failed_scenes += 1
        if total_scenes == 0:
            successful_scenes = 0
            failed_scenes = 0

        # findings
        all_findings: list[dict[str, Any]] = []
        for results in (ctx.check_results or {}).values():
            if isinstance(results, list):
                for f in results:
                    if isinstance(f, dict):
                        all_findings.append(f)
        blocking_findings = sum(1 for f in all_findings if _is_blocking(f))
        warnings = sum(1 for f in all_findings if _is_warning(f))
        verification_unavailable_events = sum(1 for f in all_findings if _is_unavailable(f))
        render_failures = sum(1 for f in all_findings if _is_render_failure(f))

        # repair counts
        repair_attempts = len(decisions)
        accepted_repairs = 0
        rejected_repairs = 0
        regression_rejections = 0
        for d in decisions:
            data = d.to_dict() if hasattr(d, "to_dict") else d
            if not isinstance(data, dict):
                continue
            dec = str(data.get("decision", ""))
            if dec == "accepted":
                accepted_repairs += 1
            else:
                rejected_repairs += 1
            if dec == "regression_rejected":
                regression_rejections += 1

        # repair cycles per scene
        attempts_per_stem: dict[str, int] = defaultdict(int)
        for d in decisions:
            data = d.to_dict() if hasattr(d, "to_dict") else d
            if isinstance(data, dict) and data.get("stem"):
                attempts_per_stem[str(data["stem"])] += 1
        if attempts_per_stem:
            vals = sorted(attempts_per_stem.values())
            mean_repair_cycles = sum(vals) / len(vals)
            median_repair_cycles = float(statistics.median(vals))
        else:
            mean_repair_cycles = 0.0
            median_repair_cycles = 0.0

        repair_success_rate = (accepted_repairs / repair_attempts) if repair_attempts else 0.0
        regression_rate = (regression_rejections / repair_attempts) if repair_attempts else 0.0

        # quality scores
        layout_scores: list[int] = []
        semantic_scores: list[int] = []
        pedagogical_scores: list[int] = []
        temporal_diffs: list[float] = []
        for stem in scene_stems:
            q = SceneQuality.collect(ctx, stem)
            layout_scores.append(q.layout_score)
            semantic_scores.append(q.semantic_score)
            pedagogical_scores.append(q.pedagogical_score)
            if q.temporal_difference is not None:
                temporal_diffs.append(float(q.temporal_difference))

        mean_layout_score = (sum(layout_scores) / len(layout_scores)) if layout_scores else 100.0
        mean_semantic_score = (sum(semantic_scores) / len(semantic_scores)) if semantic_scores else 100.0
        mean_pedagogical_score = (sum(pedagogical_scores) / len(pedagogical_scores)) if pedagogical_scores else 100.0
        mean_temporal_error = (sum(temporal_diffs) / len(temporal_diffs)) if temporal_diffs else 0.0

        # timing
        render_time = 0.0
        verification_time = 0.0
        inference_cost: float | None = None
        total_inference = 0.0
        has_inference = False
        for d in decisions:
            data = d.to_dict() if hasattr(d, "to_dict") else d
            if isinstance(data, dict):
                if isinstance(data.get("render_time_s"), (int, float)):
                    render_time += float(data["render_time_s"])
                if isinstance(data.get("verification_time_s"), (int, float)):
                    verification_time += float(data["verification_time_s"])
                if isinstance(data.get("inference_cost"), (int, float)):
                    total_inference += float(data["inference_cost"])
                    has_inference = True
        # also add stage latency from log.jsonl
        if log_path is not None:
            try:
                from .metrics import build_stage_latency
                latency = build_stage_latency(Path(log_path))
                # render stages
                for k in ["renderer_stills", "renderer_manim", "renderer_encode", "renderer_finish", "renderer_manim_finish"]:
                    render_time += latency.get(k, 0.0)
                for k in ["verifier_execution", "verifier_semantic", "verifier_spatial", "verifier_layout", "verifier_temporal", "verifier_motion"]:
                    verification_time += latency.get(k, 0.0)
            except Exception:
                pass
        if has_inference:
            inference_cost = total_inference
        else:
            inference_cost = None

        # final pass
        from .logging_ import compute_final_pass
        final_pass, final_reason = compute_final_pass(ctx)

        return {
            "schema_version": EXPERIMENT_SUMMARY_SCHEMA_VERSION,
            "total_scenes": total_scenes,
            "successful_scenes": successful_scenes,
            "failed_scenes": failed_scenes,
            "blocking_findings": blocking_findings,
            "warnings": warnings,
            "repair_attempts": repair_attempts,
            "accepted_repairs": accepted_repairs,
            "rejected_repairs": rejected_repairs,
            "regression_rejections": regression_rejections,
            "verification_unavailable_events": verification_unavailable_events,
            "render_failures": render_failures,
            "mean_repair_cycles": round(mean_repair_cycles, 3),
            "median_repair_cycles": round(median_repair_cycles, 3),
            "repair_success_rate": round(repair_success_rate, 3),
            "regression_rate": round(regression_rate, 3),
            "mean_temporal_error": round(mean_temporal_error, 3),
            "mean_layout_score": round(mean_layout_score, 1),
            "mean_semantic_score": round(mean_semantic_score, 1),
            "mean_pedagogical_score": round(mean_pedagogical_score, 1),
            "render_time": round(render_time, 3),
            "verification_time": round(verification_time, 3),
            "inference_cost": inference_cost,
            "final_pass": bool(final_pass),
            "final_pass_reason": final_reason,
        }
    except Exception as exc:
        return {
            "schema_version": EXPERIMENT_SUMMARY_SCHEMA_VERSION,
            "error": f"failed to build summary: {exc}",
            "total_scenes": 0,
            "successful_scenes": 0,
            "failed_scenes": 0,
            "blocking_findings": 0,
            "warnings": 0,
            "repair_attempts": 0,
            "accepted_repairs": 0,
            "rejected_repairs": 0,
            "regression_rejections": 0,
            "verification_unavailable_events": 0,
            "render_failures": 0,
            "mean_repair_cycles": 0.0,
            "median_repair_cycles": 0.0,
            "repair_success_rate": 0.0,
            "regression_rate": 0.0,
            "mean_temporal_error": 0.0,
            "mean_layout_score": 0.0,
            "mean_semantic_score": 0.0,
            "mean_pedagogical_score": 0.0,
            "render_time": 0.0,
            "verification_time": 0.0,
            "inference_cost": None,
            "final_pass": False,
            "final_pass_reason": str(exc),
        }


def write_experiment_summary(
    project_dir: Path | None,
    ctx: SceneContext,
    decisions: list[Any] | None = None,
    *,
    log_path: Path | None = None,
) -> Path | None:
    """Write build/harness/experiment_summary.json. Never raises."""
    if project_dir is None:
        return None
    try:
        summary = build_experiment_summary(ctx, decisions, log_path=log_path)
        path = Path(project_dir) / "build" / "harness" / "experiment_summary.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return path
    except Exception:
        return None


__all__ = ["EXPERIMENT_SUMMARY_SCHEMA_VERSION", "build_experiment_summary", "write_experiment_summary"]
