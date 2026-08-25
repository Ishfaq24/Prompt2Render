"""Tests for verifier_storyboard's Phase 2 motion-vocabulary checks."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import ScenePlanEntry, SceneContext
from prompt2render.harness.plugins.verifier_storyboard import VerifierStoryboardPlugin


def _state(motion):
    return {"name": "s", "cue": 0, "visual": "v", "transition": "t", "motion": motion}


def _context(states):
    entry = ScenePlanEntry(index=1, stem="01", title="T", anim="brief", narration_text="One sentence here.")
    ctx = SceneContext(
        prompt=None,
        project_dir=Path("/nonexistent/does/not/exist"),
        scene_plan=[entry],
    )
    ctx.storyboard_plan = {"sections": [{"index": 1, "states": states}]}
    return ctx


def _run(states):
    ctx = _context(states)
    plugin = VerifierStoryboardPlugin(config={})
    plugin.run(ctx)
    return ctx


def test_accepts_well_formed_motion():
    ctx = _run([_state([{"op": "Create", "target": "circle"}])])
    assert ctx.storyboard_verified is True


def test_rejects_non_list_motion():
    state = {"name": "s", "cue": 0, "visual": "v", "transition": "t", "motion": "nope"}
    ctx = _run([state])
    assert ctx.storyboard_verified is False
    assert any("motion must be a list" in i.get("detail", "") for i in ctx.check_results["verifier_storyboard"])


def test_rejects_unknown_op():
    ctx = _run([_state([{"op": "Spin", "target": "circle"}])])
    assert ctx.storyboard_verified is False
    assert any("unknown op 'Spin'" in i.get("detail", "") for i in ctx.check_results["verifier_storyboard"])


def test_rejects_missing_required_key():
    ctx = _run([_state([{"op": "MoveTo", "target": "circle"}])])  # missing "anchor"
    assert ctx.storyboard_verified is False
    assert any("missing required key(s) ['anchor']" in i.get("detail", "") for i in ctx.check_results["verifier_storyboard"])


def test_accepts_empty_motion_list():
    ctx = _run([_state([])])
    assert ctx.storyboard_verified is True
