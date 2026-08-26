"""Tier 4: shared HITL support (harness/hitl.py).

Covers read_feedback's defensive parsing, status_sets' accept/reject
split, write_review_draft's grouping/inertness, and (regression coverage
for the refactor) that renderer_manim.hitl_status_sets and
FeedbackHitlPlugin still behave identically now that both delegate to this
shared module instead of parsing hitl_feedback.json independently.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness import hitl
from prompt2render.harness.context import RenderArtifact, SceneContext
from prompt2render.harness.plugins.feedback_hitl import FeedbackHitlPlugin
from prompt2render.harness.plugins.renderer_manim import hitl_status_sets


def _write_feedback(tmp_path: Path, data: dict) -> None:
    (tmp_path / "hitl_feedback.json").write_text(json.dumps(data), encoding="utf-8")


# ----------------------------------------------------------------- read_feedback

def test_read_feedback_missing_file_returns_empty(tmp_path):
    assert hitl.read_feedback(tmp_path) == {}


def test_read_feedback_without_project_dir_returns_empty():
    assert hitl.read_feedback(None) == {}


def test_read_feedback_parses_valid_entries(tmp_path):
    _write_feedback(tmp_path, {"01": {"status": "reject", "reason": "bad overlap"}})
    assert hitl.read_feedback(tmp_path) == {"01": {"status": "reject", "reason": "bad overlap"}}


def test_read_feedback_malformed_json_returns_empty(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text("not valid json", encoding="utf-8")
    assert hitl.read_feedback(tmp_path) == {}


def test_read_feedback_non_dict_top_level_returns_empty(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
    assert hitl.read_feedback(tmp_path) == {}


def test_read_feedback_skips_non_dict_entries(tmp_path):
    _write_feedback(tmp_path, {"01": "not a dict", "02": {"status": "accept"}})
    assert hitl.read_feedback(tmp_path) == {"02": {"status": "accept"}}


def test_read_feedback_empty_file_returns_empty(tmp_path):
    (tmp_path / "hitl_feedback.json").write_text("", encoding="utf-8")
    assert hitl.read_feedback(tmp_path) == {}


# ------------------------------------------------------------------- status_sets

def test_status_sets_splits_accept_and_reject(tmp_path):
    _write_feedback(
        tmp_path,
        {
            "01": {"status": "reject", "reason": "x"},
            "02": {"status": "accept"},
            "03": {"status": "something_else"},
        },
    )
    rejected, locked = hitl.status_sets(tmp_path)
    assert rejected == {"01"}
    assert locked == {"02"}


def test_status_sets_no_file(tmp_path):
    assert hitl.status_sets(tmp_path) == (set(), set())


# ---------------------------------------------------- renderer_manim regression

def test_hitl_status_sets_delegates_identically(tmp_path):
    """Same input/output as before the Tier 4 refactor extracted the shared
    reader -- proves the delegation didn't change behavior."""

    _write_feedback(
        tmp_path,
        {"04": {"status": "reject"}, "07": {"status": "accept"}},
    )
    assert hitl_status_sets(tmp_path) == ({"04"}, {"07"})


# --------------------------------------------------- feedback_hitl regression

def test_feedback_hitl_plugin_still_emits_blocking_finding_for_reject(tmp_path):
    _write_feedback(tmp_path, {"04": {"status": "reject", "reason": "fix the overlap"}})

    ctx = SceneContext(project_dir=tmp_path)
    ctx.render_artifacts["04"] = RenderArtifact(stem="04")

    FeedbackHitlPlugin().run(ctx)

    results = ctx.check_results["feedback_hitl"]
    assert len(results) == 1
    assert results[0]["finding_type"] == "feedback_hitl"
    assert results[0]["severity"] == "BLOCKING"
    assert "fix the overlap" in results[0]["detail"]
    assert ctx.hitl_annotations == [{"stem": "04", "reason": "fix the overlap"}]


def test_feedback_hitl_plugin_ignores_accept(tmp_path):
    _write_feedback(tmp_path, {"04": {"status": "accept"}})

    ctx = SceneContext(project_dir=tmp_path)
    FeedbackHitlPlugin().run(ctx)

    assert ctx.check_results["feedback_hitl"] == []


# -------------------------------------------------------------- write_review_draft

def test_write_review_draft_groups_by_stem(tmp_path):
    findings = [
        {"stem": "04", "detail": "overlap"},
        {"stem": "04", "detail": "overlap"},  # duplicate, must not repeat
        {"stem": "07", "message": "wrong shape"},
    ]
    path = hitl.write_review_draft(tmp_path, findings)

    assert path == tmp_path / "hitl_review_needed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "04": {"status": "needs_review", "reason": "overlap"},
        "07": {"status": "needs_review", "reason": "wrong shape"},
    }


def test_write_review_draft_uses_needs_review_not_reject(tmp_path):
    """The draft must be inert to feedback_hitl's own parser (only "reject"
    is actionable) -- otherwise it would auto-trigger repair without a
    human ever reviewing it."""

    path = hitl.write_review_draft(tmp_path, [{"stem": "01", "detail": "x"}])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["01"]["status"] == "needs_review"

    ctx = SceneContext(project_dir=tmp_path)
    # Rename it into place to prove it's inert as-is, without a human edit.
    (tmp_path / "hitl_review_needed.json").rename(tmp_path / "hitl_feedback.json")
    FeedbackHitlPlugin().run(ctx)
    assert ctx.check_results["feedback_hitl"] == []


def test_write_review_draft_no_stems_returns_none(tmp_path):
    assert hitl.write_review_draft(tmp_path, [{"detail": "no stem here"}]) is None
    assert hitl.write_review_draft(tmp_path, []) is None


def test_write_review_draft_without_project_dir_returns_none():
    assert hitl.write_review_draft(None, [{"stem": "01", "detail": "x"}]) is None
