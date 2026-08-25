"""Tier 2 Phase 7: retrieved patterns injected into GeneratorManimPlugin's
three prompt builders (freehand, Phase 4 compiler-backed, Phase 6 DSL).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import prompt2render.align as align_module
from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin
from prompt2render.harness.semantic_plan import annotate


@pytest.fixture(autouse=True)
def _no_alignment_file(monkeypatch):
    monkeypatch.setattr(align_module, "load", lambda proj, stem: {})


def _ctx_and_section(tmp_path, *, with_pattern=True):
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
            }
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
            }
        ]
    }
    semantic_ir = annotate(animation_ir, raw)

    ctx = SceneContext(
        project_dir=tmp_path,
        animation_ir=animation_ir,
        semantic_ir=semantic_ir,
    )

    if with_pattern:
        ctx.retrieval_context = {
            "01": [
                {
                    "snippet_id": "array_basic",
                    "text": "Manim pattern: arrange uniform boxes horizontally.",
                    "matched_keywords": ["array"],
                    "score": 11,
                }
            ]
        }

    section = ScenePlanEntry(index=1, stem="01", title="Intro", anim="Show a circle.")
    return ctx, section


_PATTERN_MARKER = "Manim pattern: arrange uniform boxes horizontally."


def test_freehand_prompt_includes_matched_pattern(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": False})

    generate = MagicMock(
        return_value="class Scene01(Scene):\n    def construct(self):\n        self.wait(1)\n"
    )
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    prompt = generate.call_args.args[0]
    assert "RELEVANT PATTERNS" in prompt
    assert _PATTERN_MARKER in prompt


def test_compiler_backed_prompt_includes_matched_pattern(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True})

    generate = MagicMock(
        return_value="class Scene01(Scene):\n    def _state_introduce(self):\n        self.circle = Circle()\n"
    )
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    prompt = generate.call_args.args[0]
    assert "RELEVANT PATTERNS" in prompt
    assert _PATTERN_MARKER in prompt


def test_construction_dsl_prompt_includes_matched_pattern(tmp_path):
    import json

    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True, "use_construction_dsl": True})

    valid_dsl = json.dumps(
        {
            "nodes": [
                {"id": "title", "kind": "Text", "props": {"content": "Intro"}},
                {"id": "circle", "kind": "Circle", "props": {}},
                {"id": "caption_introduce", "kind": "Text", "props": {"content": "cap"}},
            ]
        }
    )
    generate = MagicMock(return_value=valid_dsl)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    prompt = generate.call_args.args[0]
    assert "RELEVANT PATTERNS" in prompt
    assert _PATTERN_MARKER in prompt


def test_no_retrieval_context_leaves_prompt_without_empty_section(tmp_path):
    ctx, section = _ctx_and_section(tmp_path, with_pattern=False)
    plugin = GeneratorManimPlugin({"use_motion_compiler": False})

    generate = MagicMock(
        return_value="class Scene01(Scene):\n    def construct(self):\n        self.wait(1)\n"
    )
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    prompt = generate.call_args.args[0]
    assert "RELEVANT PATTERNS" not in prompt


def test_unmatched_stem_leaves_prompt_without_pattern_section(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    ctx.retrieval_context = {"99": ctx.retrieval_context["01"]}  # matches a different stem
    plugin = GeneratorManimPlugin({"use_motion_compiler": False})

    generate = MagicMock(
        return_value="class Scene01(Scene):\n    def construct(self):\n        self.wait(1)\n"
    )
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    prompt = generate.call_args.args[0]
    assert "RELEVANT PATTERNS" not in prompt
