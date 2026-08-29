"""Per-dimension regression guard and visual-diff guard (Phases 9-13).

Dummy-router/dummy-verifier pattern (same as test_repair_controller_wiring):
no LLM, no render, no real scenekit/manim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
from prompt2render.harness.repair_controller import Decision, RepairController

STEM = "07"


class _Plan:
    def __init__(self, finding_type):
        self.finding_type = finding_type
        self.targets = ["generator_code"]
        self.routable = True


class _Router:
    def __init__(self, on_execute, finding_type):
        self.on_execute = on_execute
        self.finding_type = finding_type
        self.events = []

    def plan(self, finding, source):
        return _Plan(self.finding_type)

    def execute(self, plan, context):
        self.on_execute(context)

        class _Execution:
            ok = True
            targets_run = ["generator_code"]
            errors = []

        return _Execution()

    def emit(self, name, **kw):
        self.events.append((name, kw))


class _VerifierScripted:
    """Writes a scripted set of candidate findings for every verifier name."""

    name = "verifier_layout"

    def __init__(self, findings_by_verifier):
        self.findings_by_verifier = findings_by_verifier

    def enabled(self):
        return True

    def run(self, ctx):
        for verifier_name, findings in self.findings_by_verifier.items():
            ctx.check_results[verifier_name] = [dict(f) for f in findings]
        return ctx


def _seed(tmp_path: Path, *, trigger_type: str, manifest=None) -> SceneContext:
    canonical = tmp_path / "build" / "scenes" / f"scene_{STEM}.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("# accepted\n")

    render_dir = tmp_path / "build" / "scenes" / STEM
    render_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest if manifest is not None else [{"i": 0, "name": "s0", "png": "a.png"}]
    (render_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions[STEM] = 1
    ctx.code_artifacts[STEM] = CodeArtifact(
        stem=STEM, path=canonical, generated=True, accepted=True, revision=1,
    )
    ctx.render_artifacts[STEM] = RenderArtifact(
        stem=STEM, outdir=render_dir, manifest=manifest, source_revision=1
    )
    # Accepted evidence: one blocking semantic finding, layout clean.
    ctx.check_results["verifier_semantic"] = [
        {"stem": STEM, "status": "fail", "finding_type": trigger_type,
         "category": "SEMANTIC", "severity": "BLOCKING",
         "detail": "wrong object shown"}
    ]
    ctx.check_results["verifier_layout"] = [
        {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
         "category": "LAYOUT"}
    ]
    return ctx


def _controller(tmp_path, router, candidate_findings):
    verif = _VerifierScripted(candidate_findings)
    return RepairController(
        router=router,
        plugins_by_name={
            "verifier_layout": verif,
            "verifier_semantic": verif,
            "verifier_spatial": verif,
            "verifier_temporal": verif,
        },
        log_path=None,
        journal=None,
    )


def _write_candidate(context):
    context.candidate.code_path.write_text("# candidate\n")


# -----------------------------------------------------------------------

def test_dimension_regression_rejects_layout_drop_despite_semantic_fix(tmp_path):
    """Semantic 40->100 improvement must not pay for layout 100->85."""

    def execute(context):
        _write_candidate(context)

    ctx = _seed(tmp_path, trigger_type="semantic_mismatch")
    router = _Router(execute, "semantic_mismatch")

    # Candidate fixes the semantic finding but introduces three layout
    # warnings: layout_score 100 -> 85.
    candidate = {
        "verifier_semantic": [
            {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
             "category": "SEMANTIC"}
        ],
        "verifier_layout": [
            {"stem": STEM, "status": "warn", "severity": "WARNING",
             "finding_type": f"layout_warning_{i}", "category": "LAYOUT",
             "detail": f"crowding {i}"}
            for i in range(3)
        ],
        "verifier_spatial": [],
        "verifier_temporal": [],
    }

    controller = _controller(tmp_path, router, candidate)
    record = controller.repair_scene(
        ctx, STEM,
        [{"stem": STEM, "status": "fail", "finding_type": "semantic_mismatch",
          "category": "SEMANTIC", "severity": "BLOCKING",
          "detail": "wrong object shown"}],
        "verifier_semantic",
    )

    assert record.decision == Decision.REGRESSION_REJECTED.value
    assert "hard dimension regression: layout" in record.rejection_reason
    # The accepted revision survived untouched.
    assert ctx.scene_versions[STEM] == 1


def test_small_dimension_movement_within_tolerance_accepts(tmp_path):
    """A single advisory warning (100 -> 95) is tolerated."""

    def execute(context):
        _write_candidate(context)

    ctx = _seed(tmp_path, trigger_type="semantic_mismatch")
    router = _Router(execute, "semantic_mismatch")

    candidate = {
        "verifier_semantic": [
            {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
             "category": "SEMANTIC"}
        ],
        "verifier_layout": [
            {"stem": STEM, "status": "warn", "severity": "WARNING",
             "finding_type": "layout_warning", "category": "LAYOUT",
             "detail": "near margin"}
        ],
        "verifier_spatial": [],
        "verifier_temporal": [],
    }

    controller = _controller(tmp_path, router, candidate)
    record = controller.repair_scene(
        ctx, STEM,
        [{"stem": STEM, "status": "fail", "finding_type": "semantic_mismatch",
          "category": "SEMANTIC", "severity": "BLOCKING",
          "detail": "wrong object shown"}],
        "verifier_semantic",
    )

    assert record.decision == Decision.ACCEPTED.value
    assert ctx.scene_versions[STEM] == 2


def test_visual_churn_rejected_for_local_repair(tmp_path):
    """A LOCAL caption repair that loses half the frames is suspect."""

    four_frames = [
        {"i": i, "name": f"state_{i}", "png": f"{i}.png"} for i in range(4)
    ]

    def execute(context):
        _write_candidate(context)
        # The candidate render keeps only two of the four states.
        sidecar = context.candidate.render_dir
        reduced = four_frames[:2]
        (sidecar / "manifest.json").write_text(json.dumps(reduced), encoding="utf-8")
        context.render_artifacts[STEM] = RenderArtifact(
            stem=STEM, outdir=sidecar, manifest=reduced, source_revision=2
        )

    ctx = _seed(tmp_path, trigger_type="caption_overflow", manifest=four_frames)
    router = _Router(execute, "caption_overflow")

    candidate = {
        "verifier_semantic": [],
        "verifier_layout": [
            {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
             "category": "LAYOUT"}
        ],
        "verifier_spatial": [],
        "verifier_temporal": [],
    }

    controller = _controller(tmp_path, router, candidate)
    record = controller.repair_scene(
        ctx, STEM,
        [{"stem": STEM, "status": "fail", "finding_type": "caption_overflow",
          "category": "LAYOUT", "severity": "BLOCKING",
          "detail": "caption exceeds safe area"}],
        "verifier_layout",
    )

    assert record.decision == Decision.REGRESSION_REJECTED.value
    assert "visual regression" in record.rejection_reason
    assert ctx.scene_versions[STEM] == 1


def test_scene_scope_repair_may_restructure_visuals(tmp_path):
    """SCENE-scoped repairs are allowed to change the visual inventory."""

    four_frames = [
        {"i": i, "name": f"state_{i}", "png": f"{i}.png"} for i in range(4)
    ]

    def execute(context):
        _write_candidate(context)
        sidecar = context.candidate.render_dir
        reduced = four_frames[:2]
        (sidecar / "manifest.json").write_text(json.dumps(reduced), encoding="utf-8")
        context.render_artifacts[STEM] = RenderArtifact(
            stem=STEM, outdir=sidecar, manifest=reduced, source_revision=2
        )

    ctx = _seed(tmp_path, trigger_type="semantic_mismatch", manifest=four_frames)
    router = _Router(execute, "semantic_mismatch")

    candidate = {
        "verifier_semantic": [
            {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
             "category": "SEMANTIC"}
        ],
        "verifier_layout": [
            {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
             "category": "LAYOUT"}
        ],
        "verifier_spatial": [],
        "verifier_temporal": [],
    }

    controller = _controller(tmp_path, router, candidate)
    record = controller.repair_scene(
        ctx, STEM,
        [{"stem": STEM, "status": "fail", "finding_type": "semantic_mismatch",
          "category": "SEMANTIC", "severity": "BLOCKING",
          "detail": "concept wrong"}],
        "verifier_semantic",
    )

    assert record.decision == Decision.ACCEPTED.value
