"""Tier 2 Phase 5: the planner_temporal plugin.

Covers: populating context.temporal_ir from a real semantic_ir + real
alignment files on disk; missing alignment for a section degrades gracefully
(no SystemExit propagates -- align.load's sys.exit landmine, avoided by
checking file existence first); semantic_ir absent leaves temporal_ir as
None without error; DAG ordering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.context import SceneContext
from prompt2render.harness.loader import build_plugins, load_config
from prompt2render.harness.plugins.planner_temporal import PlannerTemporalPlugin
from prompt2render.harness.semantic_plan import annotate


def _semantic_ir_fixture():
    plan = {
        "version": "2.0",
        "prompt_sha256": "deadbeef",
        "sections": [
            {
                "index": 1,
                "stem": "01",
                "title": "Intro",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a circle.",
                        "transition": "progressive reveal",
                        "values": [],
                        "motion": [{"op": "Create", "target": "circle"}],
                    },
                ],
            },
            {
                "index": 2,
                "stem": "02",
                "title": "Next",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a square.",
                        "transition": "progressive reveal",
                        "values": [],
                        "motion": [{"op": "Create", "target": "square"}],
                    },
                ],
            },
        ],
    }
    animation_ir = from_storyboard_plan(plan)
    raw = {
        "sections": [
            {
                "index": 1,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [{"phase": "ACTION", "op": "Create", "target": "circle"}],
                    }
                ],
            },
            {
                "index": 2,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [{"phase": "ACTION", "op": "Create", "target": "square"}],
                    }
                ],
            },
        ]
    }
    return annotate(animation_ir, raw)


def _write_alignment(project_dir: Path, stem: str, sentences: list[dict]) -> None:
    align_dir = project_dir / "build" / "align"
    align_dir.mkdir(parents=True, exist_ok=True)
    (align_dir / f"{stem}.json").write_text(
        json.dumps({"version": 2, "source": "test", "confidence": 1.0, "sentences": sentences}),
        encoding="utf-8",
    )


# ------------------------------------------------------------- success -----

def test_populates_temporal_ir_from_real_alignment_files(tmp_path):
    semantic_ir = _semantic_ir_fixture()
    _write_alignment(tmp_path, "01", [{"i": 0, "text": "x", "start": 0.0, "end": 5.0}])
    _write_alignment(tmp_path, "02", [{"i": 0, "text": "y", "start": 0.0, "end": 3.0}])

    ctx = SceneContext(project_dir=tmp_path, semantic_ir=semantic_ir)
    PlannerTemporalPlugin().run(ctx)

    assert ctx.temporal_ir is not None
    assert len(ctx.temporal_ir.sections) == 2
    assert ctx.temporal_ir.sections[0].target_duration == 5.0
    assert ctx.temporal_ir.sections[1].target_duration == 3.0


# ------------------------------------------------ missing alignment ----

def test_missing_alignment_for_one_section_degrades_gracefully(tmp_path):
    semantic_ir = _semantic_ir_fixture()
    _write_alignment(tmp_path, "01", [{"i": 0, "text": "x", "start": 0.0, "end": 5.0}])
    # "02" has no alignment file on disk at all -- must not raise SystemExit.

    ctx = SceneContext(project_dir=tmp_path, semantic_ir=semantic_ir)
    PlannerTemporalPlugin().run(ctx)

    assert ctx.temporal_ir is not None
    assert ctx.temporal_ir.sections[0].target_duration == 5.0
    assert ctx.temporal_ir.sections[1].target_duration == 0.0


def test_no_project_dir_degrades_gracefully():
    semantic_ir = _semantic_ir_fixture()
    ctx = SceneContext(project_dir=None, semantic_ir=semantic_ir)
    PlannerTemporalPlugin().run(ctx)
    assert ctx.temporal_ir is not None
    assert all(s.target_duration == 0.0 for s in ctx.temporal_ir.sections)


# --------------------------------------------------- semantic_ir absent ----

def test_semantic_ir_absent_leaves_temporal_ir_none(tmp_path):
    ctx = SceneContext(project_dir=tmp_path, semantic_ir=None)
    PlannerTemporalPlugin().run(ctx)
    assert ctx.temporal_ir is None


# ------------------------------------------------------------ DAG order ----

def test_dag_places_planner_temporal_after_planner_semantic():
    names = [p.name for p in build_plugins(load_config())]
    assert names.index("planner_semantic") < names.index("planner_temporal")
