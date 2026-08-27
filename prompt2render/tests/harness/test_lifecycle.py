"""Scene lifecycle state machine tests.

Prior to this module a scene's "state" was scattered across three weaker
signals (CodeArtifact booleans, an int revision, per-finding status
strings) with nothing to notice an impossible transition. These tests
exercise SceneState/transition/derive_state directly against SceneContext
-- no LLM, no render, no repair controller.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
from prompt2render.harness.journal import EventJournal
from prompt2render.harness.lifecycle import (
    InvalidTransition,
    SceneState,
    current_state,
    derive_state,
    transition,
)


# -------------------------------------------------------------- derive ---

def test_derive_state_no_code_artifact_is_planned():
    ctx = SceneContext()
    assert derive_state(ctx, "07") is SceneState.PLANNED


def test_derive_state_generated_no_render_is_generated():
    ctx = SceneContext()
    ctx.code_artifacts["07"] = CodeArtifact(stem="07", generated=True)
    assert derive_state(ctx, "07") is SceneState.GENERATED


def test_derive_state_rendered_no_findings_is_rendered():
    ctx = SceneContext()
    ctx.code_artifacts["07"] = CodeArtifact(stem="07", generated=True)
    ctx.render_artifacts["07"] = RenderArtifact(stem="07")
    assert derive_state(ctx, "07") is SceneState.RENDERED


def test_derive_state_blocking_finding_is_failed():
    ctx = SceneContext()
    ctx.code_artifacts["07"] = CodeArtifact(stem="07", generated=True)
    ctx.render_artifacts["07"] = RenderArtifact(stem="07")
    ctx.check_results["verifier_layout"] = [
        {"stem": "07", "status": "fail", "severity": "BLOCKING", "finding_type": "layout_violation"}
    ]
    assert derive_state(ctx, "07") is SceneState.FAILED


def test_derive_state_clean_findings_is_accepted():
    ctx = SceneContext()
    ctx.code_artifacts["07"] = CodeArtifact(stem="07", generated=True)
    ctx.render_artifacts["07"] = RenderArtifact(stem="07")
    ctx.check_results["verifier_layout"] = [
        {"stem": "07", "status": "pass", "finding_type": "layout_audit"}
    ]
    assert derive_state(ctx, "07") is SceneState.ACCEPTED


def test_current_state_prefers_explicit_over_derived():
    ctx = SceneContext()
    # No artifacts at all -- derive_state would say PLANNED -- but an
    # explicit entry (e.g. set mid-repair) must win.
    ctx.scene_states["07"] = SceneState.REPAIRING.value
    assert current_state(ctx, "07") is SceneState.REPAIRING


# --------------------------------------------------------- transitions ---

def test_valid_transition_updates_state():
    ctx = SceneContext()
    ctx.scene_states["07"] = SceneState.PLANNED.value

    result = transition(ctx, "07", SceneState.GENERATED)

    assert result is SceneState.GENERATED
    assert ctx.scene_states["07"] == SceneState.GENERATED.value


def test_invalid_transition_raises_and_does_not_mutate():
    import pytest

    ctx = SceneContext()
    ctx.scene_states["07"] = SceneState.PLANNED.value

    with pytest.raises(InvalidTransition):
        transition(ctx, "07", SceneState.ACCEPTED)

    # State must be untouched after a rejected transition.
    assert ctx.scene_states["07"] == SceneState.PLANNED.value


def test_full_happy_path_sequence():
    ctx = SceneContext()
    ctx.scene_states["07"] = SceneState.PLANNED.value

    for target in (
        SceneState.GENERATED,
        SceneState.RENDERING,
        SceneState.RENDERED,
        SceneState.VERIFYING,
        SceneState.ACCEPTED,
    ):
        transition(ctx, "07", target)

    assert current_state(ctx, "07") is SceneState.ACCEPTED


def test_repair_cycle_can_return_to_accepted_or_roll_back():
    ctx = SceneContext()
    ctx.scene_states["07"] = SceneState.ACCEPTED.value

    transition(ctx, "07", SceneState.REPAIRING)
    transition(ctx, "07", SceneState.RENDERING)
    transition(ctx, "07", SceneState.RENDERED)
    transition(ctx, "07", SceneState.VERIFYING)
    transition(ctx, "07", SceneState.REJECTED)

    assert current_state(ctx, "07") is SceneState.REJECTED

    transition(ctx, "07", SceneState.ROLLED_BACK)
    assert current_state(ctx, "07") is SceneState.ROLLED_BACK

    # A rolled-back scene can still be repaired again later.
    transition(ctx, "07", SceneState.REPAIRING)
    assert current_state(ctx, "07") is SceneState.REPAIRING


def test_accepted_scene_cannot_jump_straight_to_rejected():
    ctx = SceneContext()
    ctx.scene_states["07"] = SceneState.ACCEPTED.value

    try:
        transition(ctx, "07", SceneState.REJECTED)
        raised = False
    except InvalidTransition as exc:
        raised = True
        assert exc.stem == "07"
        assert exc.from_state is SceneState.ACCEPTED
        assert exc.to_state is SceneState.REJECTED

    assert raised


# ------------------------------------------------------------ journal ---

def test_transition_emits_scene_state_event(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_states["07"] = SceneState.PLANNED.value
    journal = EventJournal(tmp_path / "events.jsonl")

    transition(ctx, "07", SceneState.GENERATED, journal=journal, reason="generator_code")

    events = journal.read(scene_id="07", event_type="scene.state")
    assert len(events) == 1
    assert events[0]["payload"]["from"] == "planned"
    assert events[0]["payload"]["to"] == "generated"
    assert events[0]["payload"]["reason"] == "generator_code"
