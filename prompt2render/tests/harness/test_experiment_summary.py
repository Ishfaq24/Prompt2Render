"""Experiment summary (section 19) -- research-grade aggregation."""
from pathlib import Path
import json

from prompt2render.harness.context import SceneContext, ScenePlanEntry, CodeArtifact, RenderArtifact
from prompt2render.harness.experiment_summary import build_experiment_summary, write_experiment_summary


def test_build_experiment_summary_aggregates_all_fields(tmp_path):
    ctx = SceneContext(project_dir=tmp_path, prompt=tmp_path / "script.md")
    (tmp_path / "script.md").write_text("---\ntitle: T\n---\n## 1 - Intro\n> ANIM: x\n\nNarr.\n")
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T", anim="x", narration_text="Narr.")]
    code = tmp_path / "build" / "scenes" / "scene_01.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("print('hi')")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code, generated=True, accepted=True, revision=1)
    ctx.scene_versions["01"] = 1
    render_dir = tmp_path / "build" / "scenes" / "01"
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "manifest.json").write_text(json.dumps([{"png": "a.png"}]))
    (render_dir / "a.png").write_bytes(b"0"*100)
    ctx.render_artifacts["01"] = RenderArtifact(stem="01", outdir=render_dir, manifest=[{"png": "a.png"}], audit={"status": "pass", "warnings": [], "stills": 1}, source_revision=1)
    ctx.check_results["verifier_execution"] = [{"status": "pass", "stem": "01", "finding_type": "ok", "category": "TECHNICAL"}]
    ctx.check_results["verifier_semantic"] = [{"status": "pass", "stem": "01", "finding_type": "ok", "category": "SEMANTIC"}]
    ctx.check_results["verifier_spatial"] = [{"status": "pass", "stem": "01", "finding_type": "ok", "category": "SPATIAL"}]
    ctx.check_results["verifier_layout"] = [{"status": "pass", "stem": "01", "finding_type": "ok", "category": "LAYOUT"}]
    ctx.check_results["verifier_temporal"] = [{"status": "pass", "stem": "01", "finding_type": "temporal_match", "category": "TEMPORAL", "difference": 0.2}]
    # Program
    out = tmp_path / "out" / "final.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"0"*8192)
    from prompt2render.harness.lineage import record_program
    record_program(ctx, final_mp4=out)

    decisions = [
        {"stem": "01", "decision": "accepted", "render_time_s": 1.5, "verification_time_s": 0.5},
        {"stem": "01", "decision": "regression_rejected", "render_time_s": 1.0, "verification_time_s": 0.4},
    ]
    # Create a fake log.jsonl
    log_path = tmp_path / "build" / "harness" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text('{"event":"plugin.invocation","plugin":"renderer_stills","duration_s":1.2}\n{"event":"plugin.invocation","plugin":"verifier_semantic","duration_s":0.3}\n')

    summary = build_experiment_summary(ctx, decisions, log_path=log_path)

    assert summary["total_scenes"] == 1
    assert summary["successful_scenes"] == 1
    assert summary["failed_scenes"] == 0
    assert summary["repair_attempts"] == 2
    assert summary["accepted_repairs"] == 1
    assert summary["regression_rejections"] == 1
    assert summary["repair_success_rate"] == 0.5
    assert summary["mean_temporal_error"] == 0.2
    assert summary["mean_layout_score"] == 100.0
    assert summary["final_pass"] is True
    # Check all required keys present
    for key in ["total_scenes", "successful_scenes", "failed_scenes", "blocking_findings", "warnings", "repair_attempts", "accepted_repairs", "rejected_repairs", "regression_rejections", "verification_unavailable_events", "render_failures", "mean_repair_cycles", "median_repair_cycles", "repair_success_rate", "regression_rate", "mean_temporal_error", "mean_layout_score", "mean_semantic_score", "mean_pedagogical_score", "render_time", "verification_time", "inference_cost"]:
        assert key in summary, f"missing {key}"


def test_write_experiment_summary_creates_file(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    path = write_experiment_summary(tmp_path, ctx, [], log_path=None)
    assert path is not None
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"


def test_experiment_summary_handles_empty_project(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    summary = build_experiment_summary(ctx, [])
    assert summary["total_scenes"] == 0
    # An empty harness context has no planned scenes, so compute_final_pass
    # considers it vacuously passing (no required artifacts to be missing).
    assert summary["final_pass"] is True
