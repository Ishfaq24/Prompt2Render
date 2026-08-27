"""Harness-level self-check (P1-3).

The brief's requirement: "The harness must never report success merely
because an LLM said 'fixed.'" These tests build small, deliberately
inconsistent SceneContexts and assert run_self_check actually notices --
no LLM, no render, no real project on disk beyond tmp_path scaffolding.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
from prompt2render.harness.journal import EventJournal
from prompt2render.harness.revision_history import RevisionEntry, record_revision
from prompt2render.harness.selfcheck import run_self_check


def _clean_context(tmp_path: Path) -> SceneContext:
    ctx = SceneContext(project_dir=tmp_path)
    return ctx


def test_clean_context_produces_no_findings(tmp_path):
    ctx = _clean_context(tmp_path)
    assert run_self_check(ctx) == []


def test_missing_accepted_artifact_file_is_blocking(tmp_path):
    ctx = _clean_context(tmp_path)
    ctx.scene_versions["07"] = 1
    ctx.code_artifacts["07"] = CodeArtifact(
        stem="07", path=tmp_path / "does_not_exist.py", generated=True, accepted=True, revision=1,
    )

    findings = run_self_check(ctx)
    blocking = [f for f in findings if f["severity"] == "BLOCKING"]
    assert len(blocking) == 1
    assert "missing on disk" in blocking[0]["detail"]


def test_scene_with_no_code_artifact_at_all_is_blocking(tmp_path):
    ctx = _clean_context(tmp_path)
    ctx.scene_versions["07"] = 1
    # No code_artifacts["07"] entry -- pure bookkeeping loss.

    findings = run_self_check(ctx)
    assert any(f["severity"] == "BLOCKING" and "no code_artifacts entry" in f["detail"] for f in findings)


def test_stale_code_artifact_revision_is_a_warning(tmp_path):
    source = tmp_path / "scene_07.py"
    source.write_text("# ok\n")
    ctx = _clean_context(tmp_path)
    ctx.scene_versions["07"] = 2
    ctx.code_artifacts["07"] = CodeArtifact(stem="07", path=source, generated=True, revision=1)

    findings = run_self_check(ctx)
    assert any("does not match the authoritative" in f["detail"] for f in findings)


def test_missing_manifest_still_is_a_warning(tmp_path):
    outdir = tmp_path / "scenes" / "07"
    outdir.mkdir(parents=True)
    ctx = _clean_context(tmp_path)
    ctx.render_artifacts["07"] = RenderArtifact(
        stem="07", outdir=outdir, manifest=[{"png": "missing.png"}],
    )

    findings = run_self_check(ctx)
    assert any("references missing" in f["detail"] for f in findings)


def test_present_manifest_still_produces_no_finding(tmp_path):
    outdir = tmp_path / "scenes" / "07"
    outdir.mkdir(parents=True)
    (outdir / "present.png").write_bytes(b"\x89PNG")
    ctx = _clean_context(tmp_path)
    ctx.render_artifacts["07"] = RenderArtifact(
        stem="07", outdir=outdir, manifest=[{"png": "present.png"}],
    )

    assert run_self_check(ctx) == []


def test_corrupted_event_journal_seq_is_detected(tmp_path):
    journal_path = tmp_path / "build" / "harness" / "events.jsonl"
    journal_path.parent.mkdir(parents=True)
    journal = EventJournal(journal_path)
    journal.append(event_type="scene.planned", project="demo", scene_id="01")
    journal.append(event_type="scene.generated", project="demo", scene_id="01")

    # Corrupt the second record's seq to duplicate the first, bypassing the
    # journal's own writer (a real corruption scenario, e.g. manual edit
    # or a merge of two processes' output).
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    import json
    second = json.loads(lines[1])
    second["seq"] = 1
    journal_path.write_text(lines[0] + "\n" + json.dumps(second) + "\n", encoding="utf-8")

    ctx = _clean_context(tmp_path)
    findings = run_self_check(ctx)
    assert any("duplicated" in f["detail"] for f in findings)


def test_clean_event_journal_produces_no_journal_findings(tmp_path):
    journal_path = tmp_path / "build" / "harness" / "events.jsonl"
    journal_path.parent.mkdir(parents=True)
    journal = EventJournal(journal_path)
    journal.append(event_type="scene.planned", project="demo", scene_id="01")
    journal.append(event_type="scene.generated", project="demo", scene_id="01")

    ctx = _clean_context(tmp_path)
    assert run_self_check(ctx) == []


def test_revision_history_disagreement_is_detected(tmp_path):
    record_revision(
        tmp_path, "07",
        RevisionEntry(revision=1, parent_revision=0, timestamp="t", reason="", decision="accepted"),
        accepted=True,
    )

    ctx = _clean_context(tmp_path)
    ctx.scene_versions["07"] = 2  # a repair happened that revisions.json never learned about

    findings = run_self_check(ctx)
    assert any("revisions.json reports" in f["detail"] for f in findings)


def test_run_self_check_never_raises_on_a_broken_context():
    class Explodes:
        def items(self):
            raise RuntimeError("boom")

    ctx = SceneContext()
    ctx.scene_versions = Explodes()

    findings = run_self_check(ctx)
    assert any("self-check raised" in f["detail"] for f in findings)
