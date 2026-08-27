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

from prompt2render.harness.journal import EventJournal, VALID_EVENT_TYPES


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
