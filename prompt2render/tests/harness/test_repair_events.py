"""Repair lifecycle events must actually reach subscribers.

Regression: ``repair.started``/``repair.finished`` were absent from
``EventBus.VALID_EVENTS``, so every emit raised ValueError straight into
``repair_router._emit``'s bare ``except Exception: return``. The result was
that no repair lifecycle event was ever delivered to anyone, and subscribing
to one raised outright -- a silent, total failure of the repair observability
surface. These tests assert delivery through a real repair cycle, not just
through the bus in isolation, because the bus was only half the bug.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.plugins.repair_router import RepairRouterPlugin


class _Repairable(Plugin):
    """Stands in for a generator that can regenerate a single scene."""

    name = "generator_code"

    def __init__(self):
        super().__init__()
        self.reverted: list[str] = []
        self.regenerated: list[str] = []

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["code_artifacts"]

    def run(self, ctx):
        return ctx

    def revert_scene(self, ctx, stem):
        self.reverted.append(stem)

    def regenerate_one(self, ctx, stem):
        self.regenerated.append(stem)


def _finding(stem: str = "01") -> dict:
    return {
        "status": "fail",
        "finding_type": "execution_failure",
        "category": "TECHNICAL",
        "severity": "BLOCKING",
        "stem": stem,
        "scene_id": stem,
        "detail": "boom",
    }


def test_valid_events_includes_the_repair_lifecycle():
    assert "repair.started" in EventBus.VALID_EVENTS
    assert "repair.finished" in EventBus.VALID_EVENTS


def test_subscribing_to_repair_events_does_not_raise():
    # This alone used to raise ValueError.
    bus = EventBus()
    bus.subscribe("repair.started", lambda e: None)
    bus.subscribe("repair.finished", lambda e: None)


def test_repair_cycle_delivers_started_and_finished():
    seen: list[tuple[str, dict]] = []

    bus = EventBus()
    bus.subscribe("repair.started", lambda e: seen.append((e.type, e.payload)))
    bus.subscribe("repair.finished", lambda e: seen.append((e.type, e.payload)))

    target = _Repairable()
    router = RepairRouterPlugin({"max_repair_cycles": 1})

    with tempfile.TemporaryDirectory() as d:
        router.attach(
            bus=bus,
            plugins_by_name={"generator_code": target},
            log_path=Path(d) / "repair_log.jsonl",
        )
        ctx = SceneContext(project_dir=Path(d))
        bus.emit(
            "check.failed",
            plugin="verifier_execution",
            findings=[_finding()],
            context=ctx,
            is_gate=True,
        )

    kinds = [t for t, _ in seen]
    assert "repair.started" in kinds, f"no repair.started delivered; saw {kinds}"
    assert "repair.finished" in kinds, f"no repair.finished delivered; saw {kinds}"
    # The repair must genuinely have run, not merely emitted.
    assert target.regenerated == ["01"]


def test_a_raising_subscriber_does_not_abort_the_repair():
    """One bad listener must not crash the repair it is observing."""

    def explode(event):
        raise RuntimeError("subscriber is broken")

    bus = EventBus()
    bus.subscribe("repair.started", explode)

    target = _Repairable()
    router = RepairRouterPlugin({"max_repair_cycles": 1})

    with tempfile.TemporaryDirectory() as d:
        router.attach(
            bus=bus,
            plugins_by_name={"generator_code": target},
            log_path=Path(d) / "repair_log.jsonl",
        )
        ctx = SceneContext(project_dir=Path(d))
        bus.emit(
            "check.failed",
            plugin="verifier_execution",
            findings=[_finding()],
            context=ctx,
            is_gate=True,
        )

    assert target.regenerated == ["01"]
