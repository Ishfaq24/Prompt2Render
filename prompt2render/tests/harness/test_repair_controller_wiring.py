"""RepairController wiring: durable journal events, lifecycle transitions,
and convergence detection (P0-1/P0-2/P0-3/P0-4 integration).

Follows the same dummy-router/dummy-verifier pattern already established
by the root test_layout_semantic.py's CASE F/G/H (a fake
plan()/execute()/emit() router plus a fake verifier registered under one
of RepairController.SCENE_VERIFIERS' names) -- no LLM, no render, no
real scenekit/manim.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
from prompt2render.harness.journal import EventJournal
from prompt2render.harness.lifecycle import SceneState, current_state
from prompt2render.harness.repair_controller import Decision, RepairController

STEM = "07"


class _Plan:
    def __init__(self, finding_type="layout_violation"):
        self.finding_type = finding_type
        self.targets = ["generator_code"]
        self.routable = True


class _Router:
    """Minimal plan()/execute()/emit() router, matching the real
    RoutingRouter's strategy-provider contract exactly enough for
    RepairController to drive a cycle end to end."""

    def __init__(self, on_execute, finding_type="layout_violation"):
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


def _seed_context(tmp_path: Path) -> tuple[SceneContext, Path]:
    canonical = tmp_path / "build" / "scenes" / f"scene_{STEM}.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("# accepted\nprint(1)\n")

    render_dir = tmp_path / "build" / "scenes" / STEM
    render_dir.mkdir(parents=True, exist_ok=True)
    (render_dir / "manifest.json").write_text("[]")

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions[STEM] = 1
    ctx.code_artifacts[STEM] = CodeArtifact(
        stem=STEM, path=canonical, generated=True, accepted=True, revision=1,
    )
    ctx.render_artifacts[STEM] = RenderArtifact(
        stem=STEM, outdir=render_dir, manifest=[{"png": "a.png"}], source_revision=1
    )
    ctx.check_results["verifier_layout"] = [
        {"stem": STEM, "status": "fail", "finding_type": "layout_violation",
         "category": "LAYOUT", "severity": "BLOCKING", "detail": "caption crowding"}
    ]
    ctx.check_results["verifier_semantic"] = [
        {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch", "category": "SEMANTIC"}
    ]

    return ctx, canonical


# ------------------------------------------------------------- accepted ---

class _VerifierClean:
    name = "verifier_layout"

    def enabled(self):
        return True

    def run(self, ctx):
        ctx.check_results["verifier_layout"] = [
            {"stem": STEM, "status": "pass", "finding_type": "layout_audit", "category": "LAYOUT"}
        ]
        ctx.check_results["verifier_semantic"] = [
            {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch", "category": "SEMANTIC"}
        ]
        ctx.check_results["verifier_spatial"] = [
            {"stem": STEM, "status": "pass", "finding_type": "spatial_audit", "category": "SPATIAL"}
        ]
        ctx.check_results["verifier_temporal"] = [
            {"stem": STEM, "status": "pass", "finding_type": "temporal_match",
             "category": "TEMPORAL", "difference": 0.1}
        ]
        return ctx


def test_accepted_cycle_emits_journal_sequence_and_reaches_accepted_state():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx, _ = _seed_context(tmp_path)
        journal = EventJournal(tmp_path / "events.jsonl")

        def write_candidate(context):
            context.candidate.code_path.write_text("# candidate\n")

        router = _Router(write_candidate)
        verif = _VerifierClean()
        controller = RepairController(
            router=router,
            plugins_by_name={
                "verifier_layout": verif, "verifier_semantic": verif,
                "verifier_spatial": verif, "verifier_temporal": verif,
            },
            log_path=None,
            journal=journal,
        )

        record = controller.repair_scene(
            ctx, STEM,
            [{"stem": STEM, "status": "fail", "finding_type": "layout_violation",
              "category": "LAYOUT", "severity": "BLOCKING", "detail": "caption crowding"}],
            "verifier_layout",
        )

        assert record.decision == Decision.ACCEPTED.value

        events = [e["event_type"] for e in journal.read(scene_id=STEM)]
        for expected in (
            "scene.state",  # -> REPAIRING
            "scene.repair.started",
            "scene.repair.candidate",
            "scene.repair.rendered",
            "scene.repair.verified",
            "scene.accepted",
        ):
            assert expected in events, "%r missing from %r" % (expected, events)

        # One scene.state event per lifecycle hop: REPAIRING, RENDERING,
        # RENDERED, VERIFYING, ACCEPTED.
        assert events.count("scene.state") == 5

        assert current_state(ctx, STEM) is SceneState.ACCEPTED


# ------------------------------------------------------------- rejected ---

class _VerifierRegresses:
    """Fixes layout, introduces a semantic defect -- CASE B/F."""

    name = "verifier_layout"

    def enabled(self):
        return True

    def run(self, ctx):
        ctx.check_results["verifier_layout"] = [
            {"stem": STEM, "status": "pass", "finding_type": "layout_audit", "category": "LAYOUT"}
        ]
        ctx.check_results["verifier_semantic"] = [
            {"stem": STEM, "status": "fail", "finding_type": "semantic_mismatch",
             "category": "SEMANTIC", "severity": "BLOCKING", "detail": "values changed"}
        ]
        return ctx


def test_rejected_cycle_emits_rollback_with_finding_diff():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx, canonical = _seed_context(tmp_path)
        journal = EventJournal(tmp_path / "events.jsonl")

        def write_candidate(context):
            context.candidate.code_path.write_text("# candidate\n")

        router = _Router(write_candidate)
        verif = _VerifierRegresses()
        controller = RepairController(
            router=router,
            plugins_by_name={"verifier_layout": verif, "verifier_semantic": verif},
            log_path=None,
            journal=journal,
        )

        record = controller.repair_scene(
            ctx, STEM,
            [{"stem": STEM, "status": "fail", "finding_type": "layout_violation",
              "category": "LAYOUT", "severity": "BLOCKING", "detail": "caption crowding"}],
            "verifier_layout",
        )

        assert record.decision == Decision.REGRESSION_REJECTED.value
        assert record.finding_diff["resolved"] == ["layout_violation"]
        assert record.finding_diff["introduced"] == ["semantic_mismatch"]

        # The accepted file on disk must be untouched -- the whole point
        # of the transactional candidate workspace.
        assert canonical.read_text() == "# accepted\nprint(1)\n"

        rollback_events = journal.read(event_type="scene.rollback", scene_id=STEM)
        assert len(rollback_events) == 1
        assert rollback_events[0]["payload"]["finding_diff"]["introduced"] == ["semantic_mismatch"]

        assert current_state(ctx, STEM) is SceneState.ROLLED_BACK


# ---------------------------------------------------------- convergence ---

class _VerifierNeverFixesIt:
    """Always reports the same blocking finding_type, regardless of what
    the candidate source actually says -- models a genuinely stuck
    repair loop (CASE G, "same verification result repeatedly returned")."""

    name = "verifier_layout"

    def enabled(self):
        return True

    def run(self, ctx):
        ctx.check_results["verifier_layout"] = [
            {"stem": STEM, "status": "fail", "finding_type": "layout_violation",
             "category": "LAYOUT", "severity": "BLOCKING", "detail": "still crowded"}
        ]
        return ctx


def test_repeated_stuck_repair_is_flagged_no_progress_on_second_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx, _ = _seed_context(tmp_path)

        calls = {"n": 0}

        def write_candidate(context):
            # Different content each time -- proves NO_PROGRESS is
            # detected from the unchanged *finding-type signature*, not
            # merely from re-proposing byte-identical source
            # (IDENTICAL_CANDIDATE is a distinct, separately-tested case).
            calls["n"] += 1
            context.candidate.code_path.write_text("# candidate rev %d\n" % calls["n"])

        router = _Router(write_candidate)
        verif = _VerifierNeverFixesIt()
        controller = RepairController(
            router=router,
            plugins_by_name={"verifier_layout": verif},
            log_path=None,
            max_repairs_per_scene=3,
        )

        finding = [{"stem": STEM, "status": "fail", "finding_type": "layout_violation",
                    "category": "LAYOUT", "severity": "BLOCKING", "detail": "still crowded"}]

        first = controller.repair_scene(ctx, STEM, finding, "verifier_layout")
        assert first.decision == Decision.TARGET_DEFECT_UNRESOLVED.value

        second = controller.repair_scene(ctx, STEM, finding, "verifier_layout")
        assert second.decision == Decision.NO_PROGRESS.value


# ------------------------------------------------------ repair contract ---
# P1-1: repair goals/invariants already exist as RepairPlan (repair_router/
# __init__.py's _contract_for) -- this only checks the contract is now
# surfaced onto the decision record and journal, not duplicated.

class _RealPlanRouter:
    """Uses the REAL RepairRouterPlugin.plan() (not a stub), to prove the
    extraction reads genuine category/allowed_changes/protected_properties
    values, not just field presence on a hand-rolled test double."""

    def __init__(self, on_execute):
        from prompt2render.harness.plugins.repair_router import RepairRouterPlugin

        self.on_execute = on_execute
        self._router = RepairRouterPlugin()
        self._router.attach(plugins_by_name={"generator_code": _DummyTarget()})

    def plan(self, finding, source):
        return self._router.plan(finding, source)

    def execute(self, plan, context):
        self.on_execute(context)

        class _Execution:
            ok = True
            targets_run = ["generator_code"]
            errors = []

        return _Execution()

    def emit(self, name, **kw):
        pass


class _DummyTarget:
    name = "generator_code"


def test_repair_contract_from_the_real_router_is_recorded_and_journaled():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx, _ = _seed_context(tmp_path)
        journal = EventJournal(tmp_path / "events.jsonl")

        def write_candidate(context):
            context.candidate.code_path.write_text("# candidate\n")

        router = _RealPlanRouter(write_candidate)
        verif = _VerifierClean()
        controller = RepairController(
            router=router,
            plugins_by_name={
                "verifier_layout": verif, "verifier_semantic": verif,
                "verifier_spatial": verif, "verifier_temporal": verif,
            },
            log_path=None,
            journal=journal,
        )

        record = controller.repair_scene(
            ctx, STEM,
            [{"stem": STEM, "status": "fail", "finding_type": "layout_violation",
              "category": "LAYOUT", "mismatch_subtype": "CROWDING",
              "detail": "caption crowding"}],
            "verifier_layout",
        )

        assert record.decision == Decision.ACCEPTED.value
        assert "position" in record.repair_contract["allowed_changes"]
        assert "values" in record.repair_contract["protected_properties"]
        assert "layout-only" in record.repair_contract["repair_instruction"].lower()

        started = journal.read(event_type="scene.repair.started", scene_id=STEM)
        assert len(started) == 1
        assert "position" in started[0]["payload"]["repair_contract"]["allowed_changes"]
