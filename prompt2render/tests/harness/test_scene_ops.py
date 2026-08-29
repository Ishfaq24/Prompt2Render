"""Scene operations (verify/rollback/revisions) against a synthetic project."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness import evidence, scene_ops

SCRIPT = """# Test Video

## 1 - Intro

> ANIM: title card with a waving figure

Hello world.

## 2 - Body

> ANIM: diagram of the main concept

More narration here.
"""

SCENEKIT_SOURCE = """
def scene(k):
    k.title("Intro")
    k.caption("Hello")
"""

MANIM_SOURCE = """
from manim import *

class Scene01(Scene):
    def construct(self):
        self.wait(1)
"""


def _project(tmp_path: Path, *, manim: bool = False) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "script.md").write_text(SCRIPT, encoding="utf-8")

    subdir = "manim" if manim else "scenes"
    scene_dir = proj / "build" / subdir
    scene_dir.mkdir(parents=True)
    source = scene_dir / "scene_01.py"
    source.write_text(MANIM_SOURCE if manim else SCENEKIT_SOURCE, encoding="utf-8")

    return proj


# ----------------------------------------------------------------- verify ---

def test_verify_reports_missing_scene(tmp_path):
    proj = _project(tmp_path)

    result = scene_ops.verify_scene(proj, "02")

    assert result["status"] == "missing"


def test_verify_writes_report_and_evidence(tmp_path):
    proj = _project(tmp_path)

    result = scene_ops.verify_scene(proj, "01")

    assert result["scene_id"] == "01"
    assert result["status"] in {"pass", "warn", "fail"}
    assert Path(result["report_path"]).exists()
    assert result["evidence_path"] is None or Path(result["evidence_path"]).exists()
    assert isinstance(result["checks"], dict)
    assert "execution" in result["checks"]


def test_verify_flags_broken_scene(tmp_path):
    proj = _project(tmp_path, manim=True)

    # Break the scene with a syntax error.
    source = proj / "build" / "manim" / "scene_01.py"
    source.write_text("from manim import *\nthis is not python", encoding="utf-8")

    result = scene_ops.verify_scene(proj, "01")

    assert result["status"] == "fail"
    assert result["blocking_count"] >= 1
    assert result["checks"]["execution"] == "fail"


# --------------------------------------------------------------- rollback ---

def _archive(proj: Path, stem: str, revision: int, source_text: str, report: str = "{}") -> None:
    rev_dir = evidence.revision_dir(proj, stem, revision)
    rev_dir.mkdir(parents=True, exist_ok=True)
    (rev_dir / f"scene_{stem}.py").write_text(source_text, encoding="utf-8")
    (rev_dir / "report.json").write_text(report, encoding="utf-8")


def test_rollback_restores_archived_source(tmp_path):
    proj = _project(tmp_path)

    old_source = "def scene(k):\n    k.title('Old but accepted')\n"
    _archive(proj, "01", 1, old_source)

    result = scene_ops.rollback_scene(proj, "01", 1)

    canonical = proj / "build" / "scenes" / "scene_01.py"
    assert canonical.read_text(encoding="utf-8") == old_source
    assert result["rolled_back_to"] == 1

    # Revision history records the rollback and moves the accepted pointer.
    from prompt2render.harness.revision_history import load_revision_history

    history = load_revision_history(proj)
    scene = history["scenes"]["01"]
    assert scene["accepted"] == 1
    assert scene["revisions"][-1]["decision"] == "rollback"


def test_rollback_manim_source_lands_in_manim_dir(tmp_path):
    proj = _project(tmp_path)

    _archive(proj, "01", 2, MANIM_SOURCE)

    scene_ops.rollback_scene(proj, "01", 2)

    assert (proj / "build" / "manim" / "scene_01.py").exists()


def test_rollback_missing_revision_raises(tmp_path):
    proj = _project(tmp_path)

    try:
        scene_ops.rollback_scene(proj, "01", 9)
    except FileNotFoundError:
        return

    raise AssertionError("expected FileNotFoundError for a missing archive")


def test_rollback_updates_latest_report(tmp_path):
    proj = _project(tmp_path)

    _archive(proj, "01", 1, SCENEKIT_SOURCE, report='{"status": "pass"}')

    scene_ops.rollback_scene(proj, "01", 1)

    latest = proj / "build" / "reports" / "scenes" / "01.json"
    assert latest.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "pass"


# ----------------------------------------------------- context rebuild ---

def test_reconstruct_context_reads_plan_and_revisions(tmp_path):
    proj = _project(tmp_path)

    from prompt2render.harness.revision_history import RevisionEntry, record_revision

    record_revision(
        proj, "01",
        RevisionEntry(
            revision=1, parent_revision=0, timestamp="t",
            reason="seed", decision="accepted",
        ),
        accepted=True,
    )

    ctx = scene_ops.reconstruct_context(proj)

    assert [e.stem for e in ctx.scene_plan] == ["01", "02"]
    assert ctx.scene_versions["01"] == 1
    assert ctx.code_artifacts["01"].path is not None
