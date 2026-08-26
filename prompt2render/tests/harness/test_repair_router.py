"""repair_router tests -- dummy plugins only, no real scenes/LLM calls.

The routing-policy tests at the top are unchanged: the policy table is not
affected by the controller redesign.

The lifecycle tests below were rewritten. They used to assert the router's
own outcome vocabulary ("attempted"/"gave_up") and its habit of rewriting a
finding's status to "resolved", both of which were the mechanism by which a
repair that merely *ran* was treated as a repair that *worked*. The router
is now a strategy provider -- plan() and execute() -- and acceptance belongs
to RepairController (see test_repair_acceptance.py). What is asserted here
is the router's remaining contract: correct routing, correct target
invocation, feedback plumbing, and honest error reporting.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import SceneContext
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.plugins.repair_router import (
    RepairRouterPlugin,
    finding_type_of,
)
from prompt2render.harness.plugins.repair_router.policy import (
    StaticTableRoutingPolicy,
)


# ------------------------------------------------------------------ policy --

def test_static_table_routes_known_finding_types():
    policy = StaticTableRoutingPolicy()
    assert policy.decide({"finding_type": "spatial_conflict"}) == ["generator_code"]
    assert policy.decide({"finding_type": "lifecycle_violation"}) == ["generator_code"]
    assert policy.decide({"finding_type": "unknown_type"}) == []


def test_static_table_routes_audio_visual_mismatch_by_subtype():
    policy = StaticTableRoutingPolicy()
    assert policy.decide({"finding_type": "audio_visual_mismatch",
                          "mismatch_subtype": "narration_wrong"}) == ["planner_audio"]
    assert policy.decide({"finding_type": "audio_visual_mismatch",
                          "mismatch_subtype": "visual_wrong"}) == ["generator_code"]
    assert policy.decide({"finding_type": "audio_visual_mismatch",
                          "mismatch_subtype": "unclear"}) == ["generator_code", "planner_audio"]


def test_static_table_routes_vlm_post_render_defect_by_category():
    policy = StaticTableRoutingPolicy()
    assert policy.decide({"finding_type": "vlm_post_render_defect",
                          "category": "SPATIAL"}) == ["verifier_spatial"]
    assert policy.decide({"finding_type": "vlm_post_render_defect",
                          "category": "AUDIO"}) == ["verifier_audio"]


# ----------------------------------------------------------- dummy targets --

class RepairableTarget(Plugin):
    """A scene-scoped repair target, named to match the routing table."""

    name = "generator_code"

    def __init__(self, config=None, raise_on_regenerate: bool = False):
        super().__init__(config)
        self.raise_on_regenerate = raise_on_regenerate
        self.calls = 0
        self.reverted: list[str] = []
        self.seen_repair_context: list[list[str]] = []

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["code_artifacts"]

    def run(self, context):
        return context

    def revert_scene(self, context, stem):
        self.reverted.append(stem)

    def regenerate_one(self, context, stem):
        self.calls += 1
        self.seen_repair_context.append(
            list(context.repair_context.get(stem, []))
        )

        if self.raise_on_regenerate:
            raise SystemExit(f"section {stem} rejected (simulated)")


class WholeStageTarget(Plugin):
    """A target implementing neither method -- must degrade to run(ctx)."""

    name = "reviser_script"

    def __init__(self, config=None):
        super().__init__(config)
        self.runs = 0

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["script_revision"]

    def run(self, context):
        self.runs += 1
        return context


def _router(**targets) -> RepairRouterPlugin:
    router = RepairRouterPlugin()
    router.attach(plugins_by_name=targets)
    return router


# -------------------------------------------------------------------- plan --

def test_plan_routes_and_carries_the_diagnostic():
    router = _router(generator_code=RepairableTarget())

    plan = router.plan(
        {
            "status": "fail",
            "finding_type": "spatial_conflict",
            "stem": "01",
            "detail": "collision at (1,2)",
        },
        "verifier_spatial",
    )

    assert plan.stem == "01"
    assert plan.finding_type == "spatial_conflict"
    assert plan.targets == ["generator_code"]
    assert plan.diagnostic == "collision at (1,2)"
    assert plan.routable is True


def test_plan_is_not_routable_for_an_unknown_finding_type():
    router = _router(generator_code=RepairableTarget())
    plan = router.plan({"finding_type": "no_such_type", "stem": "01"}, "v")
    assert plan.routable is False


def test_plan_falls_back_to_the_source_plugins_default_finding_type():
    """A verifier that forgets finding_type still routes correctly."""
    assert finding_type_of({}, "verifier_spatial") == "spatial_conflict"
    assert finding_type_of({}, "verifier_semantic") == "semantic_mismatch"


def test_plan_assigns_the_global_pseudo_stem_when_no_scene_is_named():
    router = _router(generator_code=RepairableTarget())
    plan = router.plan({"finding_type": "spatial_conflict"}, "verifier_spatial")
    assert plan.stem == "__all__"


def test_plan_aliases_generator_code_to_generator_manim_when_that_is_the_backend():
    manim = RepairableTarget()
    manim.name = "generator_manim"
    router = _router(generator_manim=manim)

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01"}, "verifier_spatial"
    )

    assert plan.targets == ["generator_manim"]


def test_plan_mutates_nothing():
    router = _router(generator_code=RepairableTarget())
    ctx = SceneContext()
    finding = {"finding_type": "spatial_conflict", "stem": "01", "status": "fail"}

    router.plan(finding, "verifier_spatial")

    assert finding["status"] == "fail"       # NOT rewritten to "resolved"
    assert ctx.repair_context == {}


# ----------------------------------------------------------------- execute --

def test_execute_prefers_scene_scoped_repair():
    target = RepairableTarget()
    router = _router(generator_code=target)
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01", "detail": "boom"},
        "verifier_spatial",
    )
    execution = router.execute(plan, ctx)

    assert execution.ok is True
    assert execution.targets_run == ["generator_code"]
    assert target.reverted == ["01"]        # revert precedes regenerate
    assert target.calls == 1


def test_execute_feeds_the_diagnostic_forward_to_the_generator():
    target = RepairableTarget()
    router = _router(generator_code=target)
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01",
         "detail": "collision at (1,2)"},
        "verifier_spatial",
    )
    router.execute(plan, ctx)

    assert target.seen_repair_context[0] == ["collision at (1,2)"]


def test_execute_does_not_duplicate_an_identical_diagnostic():
    """The same message re-appended each attempt grew the prompt without
    adding information, and both generators truncate to the last 6000 chars."""
    target = RepairableTarget()
    router = _router(generator_code=target)
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01", "detail": "same"},
        "verifier_spatial",
    )
    router.execute(plan, ctx)
    router.execute(plan, ctx)

    assert ctx.repair_context["01"] == ["same"]


def test_execute_degrades_to_a_full_run_without_scene_scoped_methods():
    target = WholeStageTarget()
    router = _router(reviser_script=target)
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "pedagogy_review", "stem": "01"}, "verifier_pedagogy"
    )
    execution = router.execute(plan, ctx)

    assert execution.ok is True
    assert target.runs == 1


def test_execute_reports_a_raising_target_without_claiming_success():
    target = RepairableTarget(raise_on_regenerate=True)
    router = _router(generator_code=target)
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01"}, "verifier_spatial"
    )
    execution = router.execute(plan, ctx)

    assert execution.ok is False
    assert execution.errors
    assert "SystemExit" in execution.errors[0]
    # The failure is also surfaced to the next generation attempt.
    assert any("repair failed" in m for m in ctx.repair_context["01"])


def test_execute_reports_an_unregistered_target():
    router = _router()          # nothing registered
    ctx = SceneContext()

    plan = router.plan(
        {"finding_type": "spatial_conflict", "stem": "01"}, "verifier_spatial"
    )
    execution = router.execute(plan, ctx)

    assert execution.ok is False
    assert "not registered" in execution.errors[0]


def test_execute_never_rewrites_a_finding_status():
    """The mechanism by which an unproven repair used to clear the gate."""
    target = RepairableTarget()
    router = _router(generator_code=target)
    ctx = SceneContext()

    finding = {
        "status": "fail",
        "finding_type": "spatial_conflict",
        "stem": "01",
        "detail": "boom",
    }
    router.execute(router.plan(finding, "verifier_spatial"), ctx)

    assert finding["status"] == "fail"


# -------------------------------------------------------------- plugin role --

def test_router_is_not_a_pipeline_stage():
    router = RepairRouterPlugin()
    ctx = SceneContext()

    assert router.run(ctx) is ctx
    assert router.declare_effects() == []
    assert router._default_gate() is False


def test_subscribe_deliberately_does_not_subscribe():
    """Repair is initiated by the runner, not by an event handler racing
    the runner's own control flow."""
    from prompt2render.harness.events import EventBus

    bus = EventBus()
    router = RepairRouterPlugin()
    router.subscribe(bus)

    seen = []
    bus.subscribe("check.failed", lambda e: seen.append(e))
    bus.emit("check.failed", plugin="v", findings=[], context=SceneContext())

    # Only our own subscriber ran; the router did not act on the event.
    assert len(seen) == 1
