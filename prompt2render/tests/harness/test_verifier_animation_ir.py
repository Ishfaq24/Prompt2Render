"""Phase 2: storyboard -> AnimationIR bridge and validation gate.

Covers the new ``verifier_animation_ir`` plugin: it builds an AnimationIR
from ``context.storyboard_plan`` (success path), turns a conversion failure
into exactly one BLOCKING ``storyboard_failure`` finding (failure path, no
new routing-table entry needed -- reuses the existing
``storyboard_failure -> ["planner_llm"]`` route), sits between
``verifier_storyboard`` and ``generator_code`` in the resolved DAG, and that
``generator_code`` now fails closed if ``animation_ir`` is unset even when
``storyboard_verified`` is True.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import SceneContext
from prompt2render.harness.loader import build_plugins, load_config
from prompt2render.harness.plugins.generator_code import GeneratorCodePlugin
from prompt2render.harness.plugins.repair_router.policy import (
    StaticTableRoutingPolicy,
)
from prompt2render.harness.plugins.verifier_animation_ir import (
    VerifierAnimationIrPlugin,
)


def _valid_storyboard_plan() -> dict:
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
                        "visual": "Highlight it.",
                        "transition": "preserve established state",
                        "values": [],
                        "motion": [{"op": "Highlight", "target": "circle"}],
                    },
                ],
            }
        ],
    }


# ------------------------------------------------------------- success -----

def test_success_populates_animation_ir_and_no_blocking_findings():
    ctx = SceneContext(storyboard_plan=_valid_storyboard_plan())
    VerifierAnimationIrPlugin().run(ctx)

    assert ctx.animation_ir is not None
    assert ctx.check_results["verifier_animation_ir"] == []
    assert len(ctx.animation_ir.sections) == 1
    assert ctx.animation_ir.sections[0].stem == "01"


# ------------------------------------------------------------- failure -----

def test_failure_produces_exactly_one_blocking_finding():
    plan = _valid_storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [{"op": "Spin", "target": "x"}]
    ctx = SceneContext(storyboard_plan=plan)

    VerifierAnimationIrPlugin().run(ctx)

    assert ctx.animation_ir is None
    results = ctx.check_results["verifier_animation_ir"]
    assert len(results) == 1
    finding = results[0]
    assert finding["status"] == "fail"
    assert finding["finding_type"] == "storyboard_failure"
    assert finding["category"] == "STORYBOARD"
    assert finding["severity"] == "BLOCKING"
    assert finding["stem"] == "01"
    assert "unknown op" in finding["detail"]


def test_failure_without_a_resolvable_stem_falls_back_to_dunder_all():
    ctx = SceneContext(storyboard_plan={"sections": "not-a-list"})

    VerifierAnimationIrPlugin().run(ctx)

    assert ctx.animation_ir is None
    finding = ctx.check_results["verifier_animation_ir"][0]
    assert finding["stem"] == "__all__"


# ------------------------------------------------------- repair routing ----

def test_finding_routes_to_planner_llm_via_the_existing_table():
    plan = _valid_storyboard_plan()
    plan["sections"][0]["states"][0]["motion"] = [{"op": "Spin", "target": "x"}]
    ctx = SceneContext(storyboard_plan=plan)

    VerifierAnimationIrPlugin().run(ctx)
    finding = ctx.check_results["verifier_animation_ir"][0]

    assert StaticTableRoutingPolicy().decide(finding) == ["planner_llm"]


# ------------------------------------------------------------ DAG order ----

def test_dag_places_the_gate_between_verifier_storyboard_and_generator_code():
    plugins = build_plugins(load_config())
    names = [p.name for p in plugins]

    assert "verifier_animation_ir" in names
    i_storyboard = names.index("verifier_storyboard")
    i_gate = names.index("verifier_animation_ir")
    i_generator = names.index("generator_code")

    assert i_storyboard < i_gate < i_generator


# ------------------------------------------------- generator_code gating ---

def test_generator_code_requires_animation_ir_even_if_storyboard_verified():
    ctx = SceneContext(
        pedagogy_verified=True,
        storyboard_verified=True,
        animation_ir=None,
    )

    try:
        GeneratorCodePlugin()._assert_prerequisites(ctx)
    except RuntimeError as exc:
        assert "animation_ir" in str(exc)
    else:
        raise AssertionError(
            "expected RuntimeError when animation_ir is unset"
        )


def test_generator_code_prerequisites_pass_once_animation_ir_is_set():
    ctx = SceneContext(storyboard_plan=_valid_storyboard_plan())
    VerifierAnimationIrPlugin().run(ctx)
    ctx.storyboard_verified = True
    ctx.pedagogy_verified = True
    from prompt2render.harness.context import ScenePlanEntry
    from prompt2render.harness.semantic_plan import default_semantic_plan

    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]
    # Phase 3: generator_code also requires semantic_ir now.
    ctx.semantic_ir = default_semantic_plan(ctx.animation_ir)

    # Must not raise.
    GeneratorCodePlugin()._assert_prerequisites(ctx)
