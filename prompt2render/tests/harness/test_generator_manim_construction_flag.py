"""Tier 2 Phase 6: the ``use_construction_dsl`` config flag on
``GeneratorManimPlugin``.

No real LLM/Manim invoked -- ``_generate_code`` is mocked directly on the
plugin instance, same seam ``test_generator_manim_compiler_flag.py`` uses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import prompt2render.align as align_module
import prompt2render.cfg as cfg_module
from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin
from prompt2render.harness.semantic_plan import annotate


@pytest.fixture(autouse=True)
def _no_alignment_file(monkeypatch):
    """See test_generator_manim_compiler_flag.py's identical fixture --
    align.load() sys.exit()s on a missing file, a SystemExit that would
    otherwise kill these tests."""

    monkeypatch.setattr(align_module, "load", lambda proj, stem: {})


def _ctx_and_section(tmp_path):
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
                        "beats": [
                            {"phase": "ACTION", "op": "Create", "target": "circle"},
                        ],
                    },
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
    section = ScenePlanEntry(index=1, stem="01", title="Intro", anim="Show a circle.")
    return ctx, section


_VALID_DSL_RESPONSE = json.dumps(
    {
        "nodes": [
            {"id": "title", "kind": "Text", "props": {"content": "Intro"}},
            {"id": "circle", "kind": "Circle", "props": {"color": "BLUE"}},
            {"id": "caption_introduce", "kind": "Text", "props": {"content": "cap"}},
        ]
    }
)


def test_dsl_off_leaves_phase4_behavior_untouched(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True, "use_construction_dsl": False})

    setup_only_code = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
    )
    generate = MagicMock(return_value=setup_only_code)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    generate.assert_called_once()
    prompt = generate.call_args.args[0]
    assert "compiled separately" in prompt  # Phase 4's freehand setup prompt, unchanged
    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert "def construct(self):" in written


def test_dsl_ignored_when_motion_compiler_off(tmp_path):
    """use_construction_dsl without use_motion_compiler must have no effect
    -- there's no setup_source concept to fill in without the compiler."""

    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": False, "use_construction_dsl": True})

    freehand_code = "class Scene01(Scene):\n    def construct(self):\n        self.wait(1)\n"
    generate = MagicMock(return_value=freehand_code)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    generate.assert_called_once()
    prompt = generate.call_args.args[0]
    assert "REFERENCE PATTERN" in prompt  # the fully-freehand prompt, not the DSL one


def test_dsl_on_compiles_valid_response(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True, "use_construction_dsl": True})

    generate = MagicMock(return_value=_VALID_DSL_RESPONSE)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    # Only the DSL prompt is requested -- valid on the first attempt.
    generate.assert_called_once()
    prompt = generate.call_args.args[0]
    assert "do NOT write Python" in prompt

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert "self.circle = Circle(color=BLUE)" in written
    assert "self.title = Text('Intro')" in written
    assert "def construct(self):" in written
    assert "Create(self.circle)" in written


def test_invalid_dsl_falls_back_to_freehand_setup_prompt(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True, "use_construction_dsl": True})

    invalid_dsl = json.dumps({"nodes": [{"id": "circle", "kind": "Nonagon", "props": {}}]})
    freehand_setup_only = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
    )
    generate = MagicMock(side_effect=[invalid_dsl, freehand_setup_only])
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    assert generate.call_count == 2
    first_prompt = generate.call_args_list[0].args[0]
    second_prompt = generate.call_args_list[1].args[0]
    assert "do NOT write Python" in first_prompt
    assert "compiled separately" in second_prompt  # fell back to Phase 4's freehand setup prompt

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert "Create(self.circle)" in written  # compiler still spliced choreography onto it


def test_invalid_dsl_logs_a_warning(tmp_path, monkeypatch):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True, "use_construction_dsl": True})

    invalid_dsl = "not json at all {{{"
    freehand_setup_only = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
    )
    plugin._generate_code = MagicMock(side_effect=[invalid_dsl, freehand_setup_only])

    warnings: list[str] = []
    monkeypatch.setattr(cfg_module, "warn", lambda msg: warnings.append(msg))

    plugin._generate_one(ctx, section)

    assert any("construction DSL failed" in w for w in warnings)
