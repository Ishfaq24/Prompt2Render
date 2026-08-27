"""Persisted per-scene revision history (P1-2).

scene_versions is authoritative but in-memory only -- it does not survive
a process restart, and a rejected repair's reasoning is lost the moment
workspace.discard removes its sidecar files. revisions.json is the durable
counterpart. Pure file-based tests, plus one RepairController integration
test proving every decision (not just accepted ones) gets recorded.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, RenderArtifact, SceneContext
from prompt2render.harness.repair_controller import Decision, RepairController
from prompt2render.harness.revision_history import (
    RevisionEntry,
    load_revision_history,
    record_revision,
    save_revision_history,
    seed_from_context,
)


# ------------------------------------------------------------------ pure --

def test_load_on_missing_file_returns_empty_structure(tmp_path):
    data = load_revision_history(tmp_path)
    assert data == {"schema_version": "1.0", "scenes": {}}


def test_load_on_none_project_dir_returns_empty_structure():
    assert load_revision_history(None) == {"schema_version": "1.0", "scenes": {}}


def test_record_revision_appends_and_advances_current(tmp_path):
    entry = RevisionEntry(
        revision=2, parent_revision=1, timestamp="2026-01-01T00:00:00Z",
        reason="repair:layout_violation", decision="accepted",
    )
    record_revision(tmp_path, "07", entry, accepted=True)

    data = load_revision_history(tmp_path)
    scene = data["scenes"]["07"]
    assert scene["current"] == 2
    assert scene["accepted"] == 2
    assert len(scene["revisions"]) == 1
    assert scene["revisions"][0]["decision"] == "accepted"


def test_rejected_attempt_is_recorded_but_does_not_advance_accepted(tmp_path):
    entry = RevisionEntry(
        revision=2, parent_revision=1, timestamp="2026-01-01T00:00:00Z",
        reason="repair:semantic_mismatch", decision="regression_rejected",
    )
    record_revision(tmp_path, "07", entry, accepted=False)

    data = load_revision_history(tmp_path)
    scene = data["scenes"]["07"]
    # current still moves (a candidate revision was attempted at rev 2),
    # but accepted stays at its prior value -- there was none yet, so 0.
    assert scene["current"] == 2
    assert scene["accepted"] == 0
    assert scene["revisions"][0]["decision"] == "regression_rejected"


def test_multiple_attempts_accumulate_in_order(tmp_path):
    for revision, decision, accepted in [
        (2, "regression_rejected", False),
        (2, "accepted", True),
    ]:
        record_revision(
            tmp_path, "07",
            RevisionEntry(
                revision=revision, parent_revision=1, timestamp="t",
                reason="repair:x", decision=decision,
            ),
            accepted=accepted,
        )

    data = load_revision_history(tmp_path)
    scene = data["scenes"]["07"]
    assert len(scene["revisions"]) == 2
    assert scene["accepted"] == 2


def test_record_revision_never_raises_on_bad_project_dir():
    class Unwritable:
        def __truediv__(self, other):
            raise RuntimeError("boom")

    # Must not raise -- persistence failures are observability losses,
    # never build failures.
    record_revision(
        Unwritable(), "07",
        RevisionEntry(revision=1, parent_revision=0, timestamp="t", reason="", decision="accepted"),
        accepted=True,
    )


# -------------------------------------------------------------- seeding --

def test_seed_from_context_creates_synthetic_revision_one(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions["07"] = 3

    seed_from_context(tmp_path, ctx)

    data = load_revision_history(tmp_path)
    scene = data["scenes"]["07"]
    assert scene["current"] == 3
    assert scene["accepted"] == 3
    assert scene["revisions"][0]["decision"] == "accepted"
    assert scene["revisions"][0]["parent_revision"] == 0


def test_seed_from_context_skips_scenes_with_zero_revision(tmp_path):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions["07"] = 0

    seed_from_context(tmp_path, ctx)

    data = load_revision_history(tmp_path)
    assert "07" not in data["scenes"]


def test_seed_from_context_does_not_overwrite_existing_history(tmp_path):
    record_revision(
        tmp_path, "07",
        RevisionEntry(revision=5, parent_revision=4, timestamp="t", reason="real", decision="accepted"),
        accepted=True,
    )

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions["07"] = 3  # stale in-memory value, must not clobber real history

    seed_from_context(tmp_path, ctx)

    data = load_revision_history(tmp_path)
    assert data["scenes"]["07"]["current"] == 5


# --------------------------------------------------- RepairController ----

class _Plan:
    finding_type = "layout_violation"
    targets = ["generator_code"]
    routable = True
    category = "LAYOUT"
    subtype = "CROWDING"
    allowed_changes = ["position"]
    protected_properties = ["values"]
    repair_instruction = "layout-only repair"


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
            {"stem": "07", "status": "pass", "finding_type": "layout_audit", "category": "LAYOUT"}
        ]
        return ctx


def test_repair_controller_records_accepted_cycle_to_revision_history():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        canonical = tmp_path / "build" / "scenes" / "scene_07.py"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_text("# accepted\n")
        render_dir = tmp_path / "build" / "scenes" / "07"
        render_dir.mkdir(parents=True, exist_ok=True)

        ctx = SceneContext(project_dir=tmp_path)
        ctx.scene_versions["07"] = 1
        ctx.code_artifacts["07"] = CodeArtifact(
            stem="07", path=canonical, generated=True, accepted=True, revision=1,
        )
        ctx.render_artifacts["07"] = RenderArtifact(stem="07", outdir=render_dir, manifest=[{"png": "a"}])
        ctx.check_results["verifier_layout"] = [
            {"stem": "07", "status": "fail", "finding_type": "layout_violation",
             "category": "LAYOUT", "severity": "BLOCKING", "detail": "crowding"}
        ]

        def write_candidate(context):
            context.candidate.code_path.write_text("# candidate\n")

        router = _Router(write_candidate)
        verif = _VerifierClean()
        controller = RepairController(
            router=router, plugins_by_name={"verifier_layout": verif}, log_path=None,
        )

        record = controller.repair_scene(
            ctx, "07",
            [{"stem": "07", "status": "fail", "finding_type": "layout_violation",
              "category": "LAYOUT", "severity": "BLOCKING", "detail": "crowding"}],
            "verifier_layout",
        )

        assert record.decision == Decision.ACCEPTED.value

        data = load_revision_history(tmp_path)
        scene = data["scenes"]["07"]
        assert scene["accepted"] == record.candidate_revision
        assert scene["revisions"][-1]["repair_contract"]["allowed_changes"] == ["position"]
