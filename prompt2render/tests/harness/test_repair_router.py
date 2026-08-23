"""repair_router tests — dummy plugins only, no real prompt2render.scenes/LLM calls (max_repair_cycles=3
default keeps this fast and offline, per the same "no Manim/LLM/network" constraint as the core
tests)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.plugins.repair_router import RepairRouterPlugin
from prompt2render.harness.plugins.repair_router.policy import StaticTableRoutingPolicy
from prompt2render.harness.runner import GateFailure, HarnessRunner


# ------------------------------------------------------------------------------ routing policy --

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


# -------------------------------------------------------------------------------- dummy plugins --

class DummyVerifier(Plugin):
    name = "dummy_verifier"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["check_results"]

    def run(self, context):
        cycle = len(context.repair_context.get("01", []))
        fail_until = int(self.config.get("fail_until", 1))
        
        if cycle < fail_until:
            context.check_results[self.name] = [{
                "status": "fail", "finding_type": "spatial_conflict", "stem": "01",
                "detail": "collision at (1,2)",
            }]
        else:
            context.check_results[self.name] = [{
                "status": "pass", "finding_type": "spatial_conflict", "stem": "01",
                "detail": "clean",
            }]
        return context


class SoftDummyVerifier(DummyVerifier):
    name = "soft_dummy_verifier"

    def _default_gate(self):
        return False

    def run(self, context):
        cycle = len(context.repair_context.get("01", []))
        fail_until = int(self.config.get("fail_until", 99))
        if cycle < fail_until:
            context.check_results[self.name] = [{
                "status": "fail", "finding_type": "spatial_conflict", "stem": "01",
                "detail": "collision at (1,2)",
            }]
        else:
            context.check_results[self.name] = [{
                "status": "pass", "finding_type": "spatial_conflict", "stem": "01",
                "detail": "clean",
            }]
        return context


class DummyGeneratorCode(Plugin):
    """Stands in for the real generator_code — fails `fail_until` regenerate_one() calls, then
    succeeds. Named "generator_code" to match StaticTableRoutingPolicy's default table.
    """
    name = "generator_code"

    def __init__(self, config=None, fail_until: int = 0):
        super().__init__(config)
        self.fail_until = fail_until
        self.calls = 0
        self.reverted = []
        self.seen_repair_context = []

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
        self.seen_repair_context.append(list(context.repair_context.get(stem, [])))
        return context
        if self.calls <= self.fail_until:
            raise SystemExit(f"[prompt2render] section {stem} rejected (simulated)")


# ------------------------------------------------------------------------------------- helpers --

def _wire(verifier: Plugin, generator: DummyGeneratorCode, tmp_path: Path, *,
         max_repair_cycles: int = 3):
    logger = StructuredLogger(tmp_path / "log.jsonl")
    bus = EventBus()
    router = RepairRouterPlugin({"max_repair_cycles": max_repair_cycles})
    router.attach(bus=bus, plugins_by_name={"generator_code": generator},
                 log_path=tmp_path / "repair_log.jsonl")
    runner = HarnessRunner([verifier], logger, bus)
    return runner, router


# ------------------------------------------------------------------------------------- resolves --

def test_repair_router_resolves_within_budget(tmp_path):
    generator = DummyGeneratorCode(fail_until=1)   # fails cycle 1, succeeds cycle 2
    runner, router = _wire(DummyVerifier({"fail_until": 1}), generator, tmp_path, max_repair_cycles=3)

    ctx = runner.run(SceneContext())   # must NOT raise — repair resolves it

    assert generator.calls == 1 # First run does nothing, repair triggers regenerate_one
    assert generator.reverted == ["01"]
    assert ctx.check_results["dummy_verifier"][0]["status"] == "pass" # Re-verification passes
    # repair_context is now cleared on successful repair
    assert not ctx.repair_context

    lines = [json.loads(l) for l in
            (tmp_path / "repair_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["outcome"] for r in lines] == ["attempted"]
    assert [r["cycles_used"] for r in lines] == [1]
    assert all(r["scene_id"] == "01" for r in lines)
    assert all(r["finding_type"] == "spatial_conflict" for r in lines)


def test_repair_router_feeds_prior_diagnostics_to_next_attempt(tmp_path):
    generator = DummyGeneratorCode(fail_until=2)
    runner, _ = _wire(DummyVerifier({"fail_until": 2}), generator, tmp_path, max_repair_cycles=3)
    runner.run(SceneContext())
    # second regenerate_one call should have seen the first cycle's accumulated repair_context
    assert generator.seen_repair_context[0] == ["collision at (1,2)"]
    assert generator.seen_repair_context[1] == ["collision at (1,2)", "collision at (1,2)"]


# ------------------------------------------------------------------------------- budget exceeded --

def test_repair_router_gives_up_hard_gate_halts(tmp_path):
    generator = DummyGeneratorCode(fail_until=99)   # never succeeds
    runner, _ = _wire(DummyVerifier({"fail_until": 99}), generator, tmp_path, max_repair_cycles=2)

    with pytest.raises(GateFailure):
        runner.run(SceneContext())

    assert generator.calls == 2   # exactly max_repair_cycles attempts, no more
    lines = [json.loads(l) for l in
            (tmp_path / "repair_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["outcome"] for r in lines] == ["attempted", "attempted", "gave_up"]


def test_repair_router_gives_up_soft_gate_continues(tmp_path):
    generator = DummyGeneratorCode(fail_until=99)
    runner, _ = _wire(SoftDummyVerifier({"fail_until": 99}), generator, tmp_path, max_repair_cycles=2)

    ctx = runner.run(SceneContext())   # must NOT raise — soft gate

    assert generator.calls == 2
    assert ctx.check_results["soft_dummy_verifier"][0]["status"] == "open_defect"

def test_runner_clears_repair_context_on_success():
    from prompt2render.harness.runner import HarnessRunner
    from prompt2render.harness.context import SceneContext
    from prompt2render.harness.plugin import Plugin
    from prompt2render.harness.logging_ import StructuredLogger
    from prompt2render.harness.events import EventBus
    import tempfile
    from pathlib import Path
    
    class DummyVerifier(Plugin):
        name = "dummy"
        def __init__(self):
            super().__init__()
            self.runs = 0
            
        def declare_dependencies(self):
            return []
            
        def declare_effects(self):
            return ["check_results"]

        def run(self, ctx):
            self.runs += 1
            if self.runs == 1:
                ctx.check_results[self.name] = [{"status": "fail", "detail": "bad"}]
                ctx.repair_context["01"] = ["fix it"]
            else:
                ctx.check_results[self.name] = [{"status": "pass"}]
            return ctx
            
        def is_gate(self):
            return True
            
    verifier = DummyVerifier()
    
    # We need a dummy event handler to mark the failure as "resolved" so the runner re-verifies
    bus = EventBus()
    def fake_repair(event):
        for f in event.payload["findings"]:
            f["status"] = "resolved"
    bus.subscribe("check.failed", fake_repair)
    
    with tempfile.TemporaryDirectory() as d:
        logger = StructuredLogger(Path(d) / "log.jsonl")
        runner = HarnessRunner([verifier], logger, bus)
        ctx = SceneContext()
        
        ctx = runner.run(ctx)
        
        assert verifier.runs == 2
        # The repair context MUST be cleared after a successful re-verification
        assert not ctx.repair_context
