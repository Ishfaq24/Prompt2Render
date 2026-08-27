"""build_repair_controller must forward a journal through to RepairController.

No prior test covered build_repair_controller at all (it is otherwise only
exercised by the real CLI). This is the minimal regression check for the
one-line passthrough added when cmd_harness started constructing a durable
EventJournal (P0-1) alongside the existing StructuredLogger.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.journal import EventJournal
from prompt2render.harness.loader import build_repair_controller


def test_journal_is_forwarded_to_the_repair_controller(tmp_path):
    journal = EventJournal(tmp_path / "events.jsonl")

    controller = build_repair_controller(
        [],
        log_path=tmp_path / "repair_log.jsonl",
        journal=journal,
    )

    assert controller is not None
    assert controller.journal is journal


def test_journal_defaults_to_none_when_not_supplied(tmp_path):
    controller = build_repair_controller(
        [],
        log_path=tmp_path / "repair_log.jsonl",
    )

    assert controller is not None
    assert controller.journal is None
