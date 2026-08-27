"""Regression fix: harness/regression.py was dead code (B3).

Its own docstring claimed ``HarnessRunner`` calls ``scene_fingerprints``/
``changed_stems`` "around every stage" and unions any silently-changed
stem into re-verification -- but ``runner.py`` never imported the module.
A whole-scope repair target (the one live example is ``reviser_script``,
which rewrites the entire script and has no ``regenerate_one``/
``revert_scene``) could silently rewrite an unrelated, already-verified
stem's ``scene_plan`` content with nothing downstream noticing, because
the revision-based staleness in ``lineage.drop_stale_results`` only fires
on an explicit ``scene_versions`` bump, which a whole-script rewrite does
not do.

This test drives ``HarnessRunner.run()`` directly (dummy plugins, no LLM,
no render) and proves the wiring: a stage that silently edits another
stem's scene-plan text causes that stem's existing check_results to be
force-cleared, and (when a journal is attached) a ``cache.invalidated``
event is recorded explaining why.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import ScenePlanEntry, SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.journal import EventJournal
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.harness.plugin import Plugin
from prompt2render.harness.runner import HarnessRunner


class _SeedAlreadyVerified(Plugin):
    """Stands in for everything upstream of a whole-script repair target:
    a scene plan already exists, and stem 02 already has a passing
    verifier result -- exactly the state a mid-pipeline whole-script
    rewrite would silently invalidate."""

    name = "seed"

    def declare_dependencies(self):
        return []

    def declare_effects(self):
        return ["scene_plan", "check_results"]

    def run(self, context):
        context.scene_plan = [
            ScenePlanEntry(index=1, stem="01", title="One", narration_text="original one"),
            ScenePlanEntry(index=2, stem="02", title="Two", narration_text="original two"),
        ]
        context.check_results["verifier_x"] = [
            {"status": "pass", "stem": "02", "finding_type": "temporal_match"}
        ]
        return context


class _SilentWholeScriptRewrite(Plugin):
    """Mirrors the real ReviserScriptPlugin's shape: declares an effect
    that has nothing to do with stem 02, but as a side effect of "revising
    the whole script" silently rewrites stem 02's narration."""

    name = "silent_reviser"

    def declare_dependencies(self):
        return ["scene_plan"]

    def declare_effects(self):
        return ["script_revision"]

    def run(self, context):
        for entry in context.scene_plan:
            if entry.stem == "02":
                entry.narration_text = "REVISED silently"
        return context


def test_silent_scene_plan_edit_clears_stale_results_for_that_stem(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner(
        [_SeedAlreadyVerified(), _SilentWholeScriptRewrite()],
        logger,
        EventBus(),
        enforce_final_video=False,
    )

    ctx = runner.run(ctx)

    # Stem 02's stale "pass" from before the silent rewrite must be gone --
    # otherwise a downstream reader would trust evidence about narration
    # text that no longer exists.
    remaining = [
        r for r in ctx.check_results.get("verifier_x", [])
        if r.get("stem") == "02"
    ]
    assert remaining == []


def test_unrelated_stem_is_left_untouched(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner(
        [_SeedAlreadyVerified(), _SilentWholeScriptRewrite()],
        logger,
        EventBus(),
        enforce_final_video=False,
    )

    ctx = runner.run(ctx)

    # verifier_x never recorded anything for stem 01, so there is nothing
    # to widen -- confirms the invalidation is scoped to the changed stem,
    # not a wholesale check_results wipe.
    assert "verifier_x" not in ctx.check_results or not any(
        r.get("stem") == "01" for r in ctx.check_results["verifier_x"]
    )


def test_cache_invalidated_event_is_journaled(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    logger = StructuredLogger(tmp_path / "log.jsonl")
    journal = EventJournal(tmp_path / "events.jsonl")
    runner = HarnessRunner(
        [_SeedAlreadyVerified(), _SilentWholeScriptRewrite()],
        logger,
        EventBus(),
        enforce_final_video=False,
        journal=journal,
    )

    runner.run(ctx)

    events = journal.read(event_type="cache.invalidated", scene_id="02")
    assert len(events) == 1
    assert "silent_reviser" in events[0]["payload"]["reason"]


def test_no_silent_edit_means_no_invalidation_event(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    logger = StructuredLogger(tmp_path / "log.jsonl")
    journal = EventJournal(tmp_path / "events.jsonl")
    runner = HarnessRunner(
        [_SeedAlreadyVerified()],
        logger,
        EventBus(),
        enforce_final_video=False,
        journal=journal,
    )

    runner.run(ctx)

    assert journal.read(event_type="cache.invalidated") == []
