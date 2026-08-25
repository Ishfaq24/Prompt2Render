"""Phase 3: the planner_semantic plugin.

Covers: success path with a mocked LLM response, the silent deterministic
fallback when the LLM is unavailable, a BLOCKING semantic_plan_failure
Finding when the LLM responds with invalid content, DAG ordering, repair
routing through the new routing-table entry, and targeted single-section
repair via regenerate_one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.context import SceneContext
from prompt2render.harness.loader import build_plugins, load_config
from prompt2render.harness.plugins.repair_router.policy import (
    StaticTableRoutingPolicy,
)
import prompt2render.harness.plugins.planner_semantic as ps


def _storyboard_plan():
    return {
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
                    {
                        "name": "explain",
                        "cue": 1,
                        "visual": "Turn it into a square.",
                        "transition": "morph",
                        "values": [],
                        "motion": [
                            {"op": "Transform", "target": "circle", "into": "square"}
                        ],
                    },
                ],
            }
        ],
    }


def _valid_llm_response():
    return json.dumps(
        {
            "sections": [
                {
                    "index": 1,
                    "states": [
                        {
                            "name": "introduce",
                            "hold": False,
                            "beats": [
                                {"phase": "ACTION", "op": "Create", "target": "circle"},
                            ],
                        },
                        {
                            "name": "explain",
                            "hold": False,
                            "beats": [
                                {
                                    "phase": "ANTICIPATION",
                                    "op": "Circumscribe",
                                    "target": "circle",
                                },
                                {
                                    "phase": "ACTION",
                                    "op": "Transform",
                                    "target": "circle",
                                    "into": "square",
                                },
                            ],
                        },
                    ],
                }
            ]
        }
    )


def _ctx_with_ir(tmp_path=None):
    ctx = SceneContext(storyboard_plan=_storyboard_plan(), project_dir=tmp_path)
    ctx.animation_ir = from_storyboard_plan(ctx.storyboard_plan)
    return ctx


# ------------------------------------------------------------- success -----

def test_success_populates_semantic_ir(monkeypatch):
    ctx = _ctx_with_ir()
    monkeypatch.setattr(ps.llm, "keys", lambda: ["fake_key"])
    complete = MagicMock(return_value=_valid_llm_response())
    monkeypatch.setattr(ps.llm, "complete", complete)

    ps.PlannerSemanticPlugin().run(ctx)

    complete.assert_called_once()
    assert ctx.semantic_ir is not None
    assert ctx.check_results["planner_semantic"] == []
    assert ctx.semantic_ir.sections[0].states[1].beats[1].phase == "ACTION"


def test_prompt_advertises_known_identifiers_and_existing_ops(monkeypatch):
    ctx = _ctx_with_ir()
    monkeypatch.setattr(ps.llm, "keys", lambda: ["fake_key"])
    complete = MagicMock(return_value=_valid_llm_response())
    monkeypatch.setattr(ps.llm, "complete", complete)

    ps.PlannerSemanticPlugin().run(ctx)

    prompt = complete.call_args.args[0]
    assert "circle" in prompt
    assert "square" in prompt
    assert "Circumscribe" in prompt  # new Phase 3 op advertised in the vocabulary list


# --------------------------------------------------- llm unavailable -------

def test_llm_unavailable_falls_back_silently(monkeypatch):
    ctx = _ctx_with_ir()
    monkeypatch.setattr(ps.llm, "keys", lambda: [])

    ps.PlannerSemanticPlugin().run(ctx)

    assert ctx.semantic_ir is not None
    assert ctx.check_results["planner_semantic"] == []
    # deterministic fallback tags every existing op ACTION
    for section in ctx.semantic_ir.sections:
        for state in section.states:
            assert all(beat.phase == "ACTION" for beat in state.beats)


# --------------------------------------------------- invalid llm output ----

def test_invalid_llm_response_raises_blocking_finding(monkeypatch):
    ctx = _ctx_with_ir()
    monkeypatch.setattr(ps.llm, "keys", lambda: ["fake_key"])
    bad_response = json.dumps(
        {
            "sections": [
                {
                    "index": 1,
                    "states": [
                        {
                            "name": "introduce",
                            "hold": False,
                            "beats": [
                                {"phase": "CLIMAX", "op": "Create", "target": "circle"}
                            ],
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(ps.llm, "complete", MagicMock(return_value=bad_response))

    ps.PlannerSemanticPlugin().run(ctx)

    # semantic_ir is still populated -- the deterministic fallback --
    # because generator_code hard-requires it regardless of whether its
    # content was ever consumed; only the finding records that enrichment
    # failed. The gate itself is advisory (see PlannerSemanticPlugin.
    # _default_gate), so this finding alone can't halt the pipeline.
    assert ctx.semantic_ir is not None
    for section in ctx.semantic_ir.sections:
        for state in section.states:
            assert all(beat.phase == "ACTION" for beat in state.beats)
    results = ctx.check_results["planner_semantic"]
    assert len(results) == 1
    finding = results[0]
    assert finding["finding_type"] == "semantic_plan_failure"
    assert finding["severity"] == "BLOCKING"
    assert finding["status"] == "fail"


def test_finding_routes_to_planner_semantic_via_new_table_entry(monkeypatch):
    ctx = _ctx_with_ir()
    monkeypatch.setattr(ps.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(
        ps.llm,
        "complete",
        MagicMock(
            return_value=json.dumps(
                {
                    "sections": [
                        {
                            "index": 1,
                            "states": [
                                {"name": "introduce", "hold": False, "beats": []}
                            ],
                        }
                    ]
                }
            )
        ),
    )

    ps.PlannerSemanticPlugin().run(ctx)
    finding = ctx.check_results["planner_semantic"][0]

    assert StaticTableRoutingPolicy().decide(finding) == ["planner_semantic"]


def test_gate_is_advisory_by_default():
    """Fixed after a production run: a hard gate here could halt the
    default stills path over content nothing on that path even reads. See
    the plugin's module docstring."""

    assert ps.PlannerSemanticPlugin()._default_gate() is False


# ------------------------------------------------------------ DAG order ----

def test_dag_places_planner_semantic_between_gate_and_generator_code():
    names = [p.name for p in build_plugins(load_config())]
    i_gate = names.index("verifier_animation_ir")
    i_sem = names.index("planner_semantic")
    i_generator = names.index("generator_code")
    assert i_gate < i_sem < i_generator


# -------------------------------------------------------- targeted repair --

def test_regenerate_one_repairs_a_single_section(monkeypatch, tmp_path):
    ctx = _ctx_with_ir(tmp_path)
    monkeypatch.setattr(ps.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(ps.llm, "complete", MagicMock(return_value=_valid_llm_response()))

    plugin = ps.PlannerSemanticPlugin()
    plugin.run(ctx)
    assert ctx.semantic_ir is not None

    # Now simulate a targeted repair call with fresh, still-valid content.
    ctx.repair_context["01"] = ["fix the anticipation beat"]
    monkeypatch.setattr(
        ps.llm,
        "complete",
        MagicMock(
            return_value=json.dumps(
                {
                    "sections": [
                        {
                            "index": 1,
                            "states": [
                                {
                                    "name": "introduce",
                                    "hold": False,
                                    "beats": [
                                        {"phase": "ACTION", "op": "Create", "target": "circle"}
                                    ],
                                },
                                {
                                    "name": "explain",
                                    "hold": True,
                                    "beats": [],
                                },
                            ],
                        }
                    ]
                }
            )
        ),
    )

    plugin.regenerate_one(ctx, "01")

    assert ctx.semantic_ir.sections[0].states[1].hold is True
    assert (tmp_path / "build" / "harness" / "semantic_plan.json").exists()
