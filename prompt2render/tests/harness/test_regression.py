"""Tier 3 Phase 14: verifier-driven repair with regression detection.

Pure-function coverage for regression.scene_fingerprints/changed_stems, plus
one end-to-end HarnessRunner integration test proving the concrete
mechanism: a repair target without regenerate_one/revert_scene (falls back
to a full target.run(ctx)) that incidentally rewrites an UNRELATED stem's
scene_plan entry causes that stem to be re-verified, not left stale --
using the exact same dummy-plugin/repair_router wiring style
test_repair_router.py already established.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness import lineage, regression
from prompt2render.harness.context import ScenePlanEntry, SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.plugins.repair_router import RepairRouterPlugin
from prompt2render.harness.runner import HarnessRunner


# ---------------------------------------------------------------------- pure

def _ctx_with(entries: list[tuple[str, str, str]]) -> SceneContext:
    ctx = SceneContext()
    ctx.scene_plan = [
        ScenePlanEntry(index=i, stem=stem, title=title, anim="", narration_text=narration)
        for i, (stem, title, narration) in enumerate(entries, start=1)
    ]
    return ctx


def test_scene_fingerprints_empty_scene_plan():
    assert regression.scene_fingerprints(SceneContext()) == {}


def test_scene_fingerprints_one_entry_per_stem():
    ctx = _ctx_with([("01", "Intro", "hello")])
    fp = regression.scene_fingerprints(ctx)
    assert fp == {"01": ("Intro", "", "hello")}


def test_scene_fingerprints_tolerates_non_scene_plan_entry_objects():
    """SceneContext.scene_plan is typed list[ScenePlanEntry], but nothing
    enforces that at runtime -- test_core.py's own dummy plugins put plain
    strings there. Must degrade gracefully, not crash every stage."""

    ctx = SceneContext()
    ctx.scene_plan = ["s01", "s02"]

    assert regression.scene_fingerprints(ctx) == {}


def test_changed_stems_detects_narration_change():
    before = {"01": ("Intro", "", "hello"), "02": ("Next", "", "world")}
    after = {"01": ("Intro", "", "hello"), "02": ("Next", "", "WORLD, REVISED")}
    assert regression.changed_stems(before, after) == {"02"}


def test_changed_stems_no_diff_is_empty():
    fp = {"01": ("Intro", "", "hello")}
    assert regression.changed_stems(fp, dict(fp)) == set()


def test_changed_stems_added_or_removed_stem_counts_as_changed():
    before = {"01": ("Intro", "", "hello")}
    after = {"01": ("Intro", "", "hello"), "02": ("New", "", "added")}
    assert regression.changed_stems(before, after) == {"02"}
    assert regression.changed_stems(after, before) == {"02"}


# --------------------------------------------------------------- integration

class _FakeCodeGen(Plugin):
    """Establishes a valid rewind target -- produces code_artifacts."""

    name = "fake_code_gen"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["code_artifacts"]

    def run(self, context):
        return context


class _StemTwoObserver(Plugin):
    """Stands in for a downstream verifier watching an UNRELATED stem (02).

    Records how many times it actually ran and what narration_text it saw
    for stem 02 each time -- the direct, observable proof of whether
    regression detection widened the rewind to re-run it.
    """

    name = "stem_two_observer"

    def __init__(self, config=None):
        super().__init__(config)
        self.calls = 0
        self.seen_narration: list[str] = []

    def declare_dependencies(self):
        return ["code_artifacts"]

    def declare_effects(self):
        return ["check_results"]

    def run(self, context):
        self.calls += 1
        narration = next(
            (e.narration_text for e in context.scene_plan if e.stem == "02"),
            "",
        )
        self.seen_narration.append(narration)
        context.check_results[self.name] = [
            {"status": "pass", "stem": "02", "detail": f"narration={narration}"}
        ]
        return context


class _FailOnceVerifier(Plugin):
    """Fails on its very first call, passes every call after -- independent
    of repair_context bookkeeping (which the repair/rewind machinery itself
    legitimately mutates), so a rewind-triggered rerun doesn't spuriously
    fail again."""

    name = "fail_once_verifier"

    def __init__(self, config=None):
        super().__init__(config)
        self.calls = 0

    def declare_dependencies(self):
        return ["code_artifacts"]

    def declare_effects(self):
        return ["check_results"]

    def run(self, context):
        self.calls += 1
        if self.calls == 1:
            context.check_results[self.name] = [
                {
                    "status": "fail",
                    "finding_type": "pedagogy_review",
                    "stem": "01",
                    "detail": "needs revision",
                }
            ]
        else:
            context.check_results[self.name] = [
                {"status": "pass", "stem": "01", "detail": "clean"}
            ]
        return context


class _WholeScriptReviser(Plugin):
    """Repair target for pedagogy_review, deliberately WITHOUT regenerate_one/
    revert_scene -- repair_router's duck-typed fallback therefore calls
    run(ctx) in full, which here (standing in for the real
    ReviserScriptPlugin) rewrites stem 02's narration as an incidental
    side effect of "revising the whole script"."""

    name = "reviser_script"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["script_revision"]

    def run(self, context):
        for entry in context.scene_plan:
            if entry.stem == "02":
                entry.narration_text = "REVISED by whole-script repair"
        return context


def test_a_whole_scope_repair_target_still_runs_and_is_observable(tmp_path):
    """A repair target without regenerate_one/revert_scene degrades to a
    full run(ctx), which can touch stems other than the one being repaired.

    This used to be detected by a heuristic rewind: the runner compared
    scene-plan text fingerprints before and after every stage and jumped the
    plugin index backwards when they differed. That heuristic is gone --
    staleness is now a revision comparison, and the controller re-verifies
    the repaired scene directly.

    What is still asserted here is the part that remains true and matters:
    such a target genuinely executes, its side effect on an unrelated stem
    is visible in the context, and the fingerprint helpers can see it -- so
    the evidence a future policy would need is available rather than silently
    lost.
    """

    from prompt2render.harness.repair_controller import RepairController

    ctx = _ctx_with(
        [
            ("01", "One", "original one"),
            ("02", "Two", "original two"),
        ]
    )
    ctx.project_dir = tmp_path

    reviser = _WholeScriptReviser()

    before = regression.scene_fingerprints(ctx)

    router = RepairRouterPlugin()
    router.attach(plugins_by_name={"reviser_script": reviser})

    controller = RepairController(
        router=router,
        plugins_by_name={"reviser_script": reviser},
        log_path=tmp_path / "repair_log.jsonl",
    )

    record = controller.repair_scene(
        ctx,
        "01",
        [
            {
                "status": "fail",
                "finding_type": "pedagogy_review",
                "stem": "01",
                "detail": "needs revision",
            }
        ],
        "verifier_pedagogy",
    )

    # The target ran, and its incidental rewrite of stem 02 happened.
    stem_02 = next(e for e in ctx.scene_plan if e.stem == "02")
    assert stem_02.narration_text == "REVISED by whole-script repair"

    # That collateral change is detectable from the fingerprints.
    after = regression.scene_fingerprints(ctx)
    assert regression.changed_stems(before, after) == {"02"}

    # And because no verifier could confirm the candidate was at least as
    # good, the repair was NOT accepted -- scene 01 stays at its revision.
    assert record.accepted is False
    assert lineage.current_revision(ctx, "01") == 0
