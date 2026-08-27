"""Durable event journal tests.

The harness had no durable, replayable record of what happened to each
scene -- ``log.jsonl``/``repair_log.jsonl`` exist, but neither is a single
ordered per-scene timeline, and neither survives being read back into a
structured "why did this happen" answer. ``EventJournal`` closes that gap.

These tests exercise the journal in isolation, over ``tmp_path`` --  no
SceneContext, no LLM, no render.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.journal import EventJournal, VALID_EVENT_TYPES, replay


# --------------------------------------------------------------- append ---

def test_append_writes_one_jsonl_line(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    record = journal.append(
        event_type="scene.accepted",
        project="demo",
        scene_id="07",
        revision=2,
        status="ok",
        payload={"reason": "clean"},
    )

    assert record is not None
    assert record["event_type"] == "scene.accepted"
    assert record["scene_id"] == "07"
    assert record["revision"] == 2
    assert record["seq"] == 1

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event_id"] == record["event_id"]


def test_seq_is_monotonic_across_appends(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    seqs = [
        journal.append(event_type="scene.planned", project="demo", scene_id="01")["seq"]
        for _ in range(5)
    ]

    assert seqs == [1, 2, 3, 4, 5]


def test_seq_resumes_after_reopen(tmp_path):
    path = tmp_path / "events.jsonl"
    first = EventJournal(path)
    first.append(event_type="scene.planned", project="demo", scene_id="01")
    first.append(event_type="scene.generated", project="demo", scene_id="01")

    # Simulates a fresh process (e.g. a second `prompt2render harness` run)
    # opening the same journal -- seq must not restart at 0, or replay
    # (P2-2) would see two "seq 1" events and could not order them.
    second = EventJournal(path)
    record = second.append(event_type="scene.accepted", project="demo", scene_id="01")

    assert record["seq"] == 3


# ---------------------------------------------------------- fail-safe -----

def test_unknown_event_type_does_not_raise(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    # Must not raise -- a bad call site must not be the reason a build
    # fails. It is still recorded, under a reserved type, with the bad
    # value preserved for diagnosis.
    record = journal.append(event_type="not.a.real.event", project="demo", scene_id="01")

    assert record is not None
    assert record["event_type"] == "harness.selfcheck"
    assert record["payload"]["_invalid_event_type"] == "not.a.real.event"


def test_valid_event_types_cover_the_brief_vocabulary():
    expected = {
        "build.started", "build.completed", "build.failed",
        "scene.planned", "scene.generated",
        "scene.render.started", "scene.render.completed",
        "scene.verify.started", "scene.verify.completed",
        "scene.repair.started", "scene.repair.candidate",
        "scene.repair.rendered", "scene.repair.verified",
        "scene.accepted", "scene.rejected", "scene.rollback",
        "cache.hit", "cache.invalidated",
    }
    assert expected <= VALID_EVENT_TYPES


def test_path_payload_value_is_stringified(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    record = journal.append(
        event_type="scene.render.completed",
        project="demo",
        scene_id="03",
        payload={"artifact": tmp_path / "out.png"},
    )

    # A Path is not JSON-native; it must be down-converted rather than
    # raising, and the journal must never store a "reference" that isn't
    # actually a plain string a future reader can round-trip.
    assert record["payload"]["artifact"] == str(tmp_path / "out.png")
    json.dumps(record)  # must not raise


def test_append_never_raises_on_bad_project_type(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    class Unserializable:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    # project is coerced with str(); if that itself raises, append() must
    # still swallow it rather than propagate into the caller's pipeline.
    result = journal.append(
        event_type="scene.planned",
        project=Unserializable(),
        scene_id="01",
    )

    assert result is None


# -------------------------------------------------------------- read -----

def test_read_filters_by_scene_and_type(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.planned", project="demo", scene_id="01")
    journal.append(event_type="scene.generated", project="demo", scene_id="01")
    journal.append(event_type="scene.planned", project="demo", scene_id="02")

    only_01 = journal.read(scene_id="01")
    assert [r["event_type"] for r in only_01] == ["scene.planned", "scene.generated"]

    only_planned = journal.read(event_type="scene.planned")
    assert [r["scene_id"] for r in only_planned] == ["01", "02"]


def test_read_limit_keeps_the_last_n(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    for i in range(10):
        journal.append(event_type="scene.planned", project="demo", scene_id=str(i))

    tail = journal.read(limit=3)
    assert [r["scene_id"] for r in tail] == ["7", "8", "9"]


def test_read_on_missing_file_returns_empty(tmp_path):
    journal = EventJournal(tmp_path / "does_not_exist.jsonl")
    assert journal.read() == []


def test_read_tolerates_corrupt_line(tmp_path):
    path = tmp_path / "events.jsonl"
    journal = EventJournal(path)
    journal.append(event_type="scene.planned", project="demo", scene_id="01")

    with path.open("a", encoding="utf-8") as handle:
        handle.write("not json at all\n")

    journal.append(event_type="scene.generated", project="demo", scene_id="01")

    records = journal.read()
    assert [r["event_type"] for r in records] == ["scene.planned", "scene.generated"]


# ------------------------------------------------------------- replay ----
# P2-2: reconstruct per-scene lifecycle state and decision history purely
# from durable events -- no SceneContext, no repair_log.jsonl.

def test_replay_tracks_scene_state_transitions(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.state", project="demo", scene_id="07", revision=0,
                    payload={"from": "planned", "to": "generated"})
    journal.append(event_type="scene.state", project="demo", scene_id="07", revision=0,
                    payload={"from": "generated", "to": "rendering"})

    state = replay(journal.read())

    assert state.scenes["07"].state == "rendering"


def test_replay_tracks_accepted_revision_and_decision_history(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.accepted", project="demo", scene_id="07", revision=2,
                    payload={"decision": "accepted", "reason": ""})

    state = replay(journal.read())
    scene = state.scenes["07"]

    assert scene.accepted_revision == 2
    assert scene.current_revision == 2
    assert len(scene.decisions) == 1
    assert scene.decisions[0]["decision"] == "accepted"


def test_replay_does_not_advance_accepted_revision_for_dry_run(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.rollback", project="demo", scene_id="07", revision=2,
                    payload={"decision": "accepted", "reason": "[dry-run] would accept", "dry_run": True})

    state = replay(journal.read())
    scene = state.scenes["07"]

    # current_revision still reflects the candidate revision that was
    # evaluated; accepted_revision must not move for a dry run.
    assert scene.current_revision == 2
    assert scene.accepted_revision == 0
    assert scene.decisions[0]["dry_run"] is True


def test_replay_tracks_rejected_scene_without_advancing_accepted(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.rollback", project="demo", scene_id="07", revision=2,
                    payload={"decision": "regression_rejected", "reason": "worse"})

    state = replay(journal.read())
    scene = state.scenes["07"]

    assert scene.accepted_revision == 0
    assert scene.current_revision == 2
    assert scene.decisions[0]["decision"] == "regression_rejected"


def test_replay_tracks_build_status_from_the_last_build_event(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="build.started", project="demo", scene_id="__all__")
    journal.append(event_type="build.failed", project="demo", scene_id="__all__")

    state = replay(journal.read())
    assert state.build_status == "fail"


def test_replay_ignores_whole_video_pseudo_stem_for_scene_tracking(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="cache.invalidated", project="demo", scene_id="__all__")

    state = replay(journal.read())
    assert "__all__" not in state.scenes


def test_replay_processes_events_in_seq_order_regardless_of_input_order(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")
    journal.append(event_type="scene.state", project="demo", scene_id="07",
                    payload={"to": "generated"})
    journal.append(event_type="scene.state", project="demo", scene_id="07",
                    payload={"to": "rendering"})

    events = journal.read()
    reversed_events = list(reversed(events))  # deliberately out of order

    state = replay(reversed_events)
    # If replay respected input order instead of seq, this would read
    # "generated" (the last item in the reversed list).
    assert state.scenes["07"].state == "rendering"


def test_replay_matches_live_repair_controller_state():
    """Replay must agree with what RepairController actually did -- not
    merely be internally self-consistent. Drives one real accepted repair
    cycle through RepairController (same dummy-router pattern as
    test_repair_controller_wiring.py) and compares."""
    import tempfile
    from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
    from prompt2render.harness.lifecycle import current_state
    from prompt2render.harness.repair_controller import RepairController

    STEM = "07"

    class _Plan:
        finding_type = "layout_violation"
        targets = ["generator_code"]
        routable = True

    class _Router:
        def __init__(self, on_execute):
            self.on_execute = on_execute

        def plan(self, finding, source):
            return _Plan()

        def execute(self, plan, context):
            self.on_execute(context)

            class _Execution:
                ok = True
                targets_run = ["generator_code"]
                errors = []

            return _Execution()

        def emit(self, name, **kw):
            pass

    class _VerifierClean:
        name = "verifier_layout"

        def enabled(self):
            return True

        def run(self, ctx):
            ctx.check_results["verifier_layout"] = [
                {"stem": STEM, "status": "pass", "finding_type": "layout_audit", "category": "LAYOUT"}
            ]
            return ctx

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        canonical = tmp_path / "build" / "scenes" / f"scene_{STEM}.py"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("# accepted\n")
        render_dir = tmp_path / "build" / "scenes" / STEM
        render_dir.mkdir(parents=True, exist_ok=True)

        ctx = SceneContext(project_dir=tmp_path)
        ctx.scene_versions[STEM] = 1
        ctx.code_artifacts[STEM] = CodeArtifact(
            stem=STEM, path=canonical, generated=True, accepted=True, revision=1,
        )
        ctx.render_artifacts[STEM] = RenderArtifact(stem=STEM, outdir=render_dir, manifest=[{"png": "a"}])
        ctx.check_results["verifier_layout"] = [
            {"stem": STEM, "status": "fail", "finding_type": "layout_violation",
             "category": "LAYOUT", "severity": "BLOCKING", "detail": "crowding"}
        ]

        def write_candidate(context):
            context.candidate.code_path.write_text("# candidate\n")

        journal = EventJournal(tmp_path / "events.jsonl")
        controller = RepairController(
            router=_Router(write_candidate),
            plugins_by_name={"verifier_layout": _VerifierClean()},
            log_path=None,
            journal=journal,
        )

        record = controller.repair_scene(
            ctx, STEM,
            [{"stem": STEM, "status": "fail", "finding_type": "layout_violation",
              "category": "LAYOUT", "severity": "BLOCKING", "detail": "crowding"}],
            "verifier_layout",
        )

        replayed = replay(journal.read())

        assert record.accepted is True
        assert replayed.scenes[STEM].state == current_state(ctx, STEM).value
        assert replayed.scenes[STEM].accepted_revision == record.candidate_revision
