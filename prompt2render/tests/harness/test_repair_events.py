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


def _controller(bus: EventBus, target: _Repairable, tmp: Path):
    """A repair controller wired the way the runner wires one.

    Repair is driven by the controller now, not by a ``check.failed``
    subscriber -- that indirection is exactly what let a second, competing
    repair loop race the runner's own control flow.
    """

    from prompt2render.harness.repair_controller import RepairController

    router = RepairRouterPlugin()
    router.attach(bus=bus, plugins_by_name={"generator_code": target})

    return RepairController(
        router=router,
        plugins_by_name={"generator_code": target},
        log_path=tmp / "repair_log.jsonl",
    )


def test_repair_cycle_delivers_started_and_finished():
    seen: list[tuple[str, dict]] = []

    bus = EventBus()
    bus.subscribe("repair.started", lambda e: seen.append((e.type, e.payload)))
    bus.subscribe("repair.finished", lambda e: seen.append((e.type, e.payload)))

    target = _Repairable()

    with tempfile.TemporaryDirectory() as d:
        controller = _controller(bus, target, Path(d))
        ctx = SceneContext(project_dir=Path(d))
        controller.repair_scene(ctx, "01", [_finding()], "verifier_execution")

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

    with tempfile.TemporaryDirectory() as d:
        controller = _controller(bus, target, Path(d))
        ctx = SceneContext(project_dir=Path(d))
        controller.repair_scene(ctx, "01", [_finding()], "verifier_execution")

    assert target.regenerated == ["01"]


def test_repair_finished_reports_the_real_decision():
    """The finished event carries the controller's verdict, not merely
    'the repair call did not raise'."""

    finished: list[dict] = []

    bus = EventBus()
    bus.subscribe("repair.finished", lambda e: finished.append(e.payload))

    target = _Repairable()

    with tempfile.TemporaryDirectory() as d:
        controller = _controller(bus, target, Path(d))
        ctx = SceneContext(project_dir=Path(d))
        record = controller.repair_scene(
            ctx, "01", [_finding()], "verifier_execution"
        )

    assert finished
    assert finished[0]["outcome"] == record.decision
    # No verifiers were registered, so nothing could establish the candidate
    # is at least as good -- it must NOT be accepted.
    assert record.accepted is False
