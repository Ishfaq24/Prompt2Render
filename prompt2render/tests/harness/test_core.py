"""Harness core tests — dummy plugins only. No prompt2render.scenes/stills/network/Manim imports, per the
migration brief: "the core must be testable without Manim, without an LLM, and without network
access."
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import SceneContext, restore, snapshot
from prompt2render.harness.events import EventBus
from prompt2render.harness.loader import DependencyError, resolve_order
from prompt2render.harness.logging_ import StructuredLogger, context_hash
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.runner import GateFailure, HarnessRunner


class Producer(Plugin):
    name = "producer"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["scene_plan"]

    def run(self, context):
        context.scene_plan = ["s01"]
        return context


class Consumer(Plugin):
    name = "consumer"

    def declare_dependencies(self):
        return ["scene_plan"]

    def declare_effects(self):
        return ["code_artifacts"]

    def run(self, context):
        assert context.scene_plan == ["s01"]
        context.code_artifacts = {"s01": "generated"}
        return context


class FailingGate(Plugin):
    name = "failing_gate"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["check_results"]

    def run(self, context):
        context.check_results[self.name] = [{"status": "fail", "detail": "boom"}]
        return context


class SoftFail(FailingGate):
    name = "soft_fail"

    def _default_gate(self):
        return False


# --------------------------------------------------------------------------- dependency order --

def test_resolve_order_respects_dependencies():
    ordered = resolve_order([Consumer(), Producer()])
    assert [p.name for p in ordered] == ["producer", "consumer"]


def test_resolve_order_raises_on_unmet_dependency():
    with pytest.raises(DependencyError):
        resolve_order([Consumer()])


# ------------------------------------------------------------------- config-driven enable/disable --

def test_plugin_enabled_flag():
    assert Producer({"enabled": True}).enabled()
    assert not Producer({"enabled": False}).enabled()
    assert Producer({}).enabled()          # defaults to enabled


def test_gate_override_wins_over_default():
    p = FailingGate({"gate_override": False})
    assert p.is_gate() is False
    p2 = FailingGate({})
    assert p2.is_gate() is True            # FailingGate's _default_gate is True


# ------------------------------------------------------------------------------ snapshot/revert --

def test_snapshot_and_restore_roundtrip():
    ctx = SceneContext()
    ctx.scene_plan = ["a"]
    snap = snapshot(ctx)
    ctx.scene_plan.append("b")
    assert ctx.scene_plan == ["a", "b"]
    restore(ctx, snap)
    assert ctx.scene_plan == ["a"]


# ----------------------------------------------------------------------------------- event bus --

def test_event_bus_pub_sub():
    seen = []
    bus = EventBus()
    bus.subscribe("check.failed", lambda ev: seen.append(ev.payload))
    bus.emit("check.failed", plugin="x", findings=[{"status": "fail"}])
    assert seen == [{"plugin": "x", "findings": [{"status": "fail"}]}]


# --------------------------------------------------------------------------------- JSONL logging --

def test_structured_logger_writes_one_line(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = StructuredLogger(log_path)
    ctx = SceneContext()
    logger.log_invocation(plugin="producer", input_ctx=ctx, output_ctx=ctx,
                          ok=True, duration_s=0.01)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["plugin"] == "producer"
    assert record["ok"] is True
    assert record["input_context_hash"] == context_hash(ctx)


# -------------------------------------------------------------------------------------- runner --

def test_runner_executes_in_dependency_order(tmp_path):
    ordered = resolve_order([Consumer(), Producer()])
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner(ordered, logger)
    ctx = runner.run(SceneContext())
    assert ctx.code_artifacts == {"s01": "generated"}
    assert [h.plugin for h in ctx.history] == ["producer", "consumer"]


def test_runner_halts_on_hard_gate_failure(tmp_path):
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner([FailingGate()], logger)
    # Bug fix (B6): a GateFailure makes the runner call
    # write_self_correction_report(), which falls back to Path(".") when
    # SceneContext.project_dir is unset -- leaking a real
    # self_correction_report.json into whatever the test runner's cwd
    # happens to be. project_dir=tmp_path keeps this test's side effects
    # inside its own sandbox, matching every other test in this file.
    with pytest.raises(GateFailure):
        runner.run(SceneContext(project_dir=tmp_path))


class RaisesSystemExit(Plugin):
    """Mirrors prompt2render's own idiom (align.py/voice.py/scenes.py all `sys.exit(...)` on an expected
    fatal condition) — the runner must catch and log this, not let it silently bypass logging."""
    name = "raises_system_exit"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return []

    def run(self, context):
        raise SystemExit("[prompt2render] no build/master.wav — run `prompt2render voice` first")


def test_runner_logs_and_propagates_system_exit(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = StructuredLogger(log_path)
    runner = HarnessRunner([RaisesSystemExit()], logger)
    # Bug fix (B6): see the matching comment on
    # test_runner_halts_on_hard_gate_failure -- this path also triggers
    # write_self_correction_report(), which leaks to cwd without an
    # explicit project_dir.
    with pytest.raises(SystemExit):
        runner.run(SceneContext(project_dir=tmp_path))
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["ok"] is False
    assert "master.wav" in record["diagnostics"]


def test_runner_continues_on_soft_gate_failure(tmp_path):
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner([SoftFail()], logger)
    ctx = runner.run(SceneContext())
    assert ctx.check_results["soft_fail"][0]["status"] == "fail"
    assert ctx.history[0].ok is False
