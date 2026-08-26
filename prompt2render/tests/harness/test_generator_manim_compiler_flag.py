"""Tier 2 Phase 4: the ``use_motion_compiler`` config flag on
``GeneratorManimPlugin``.

No real LLM/Manim invoked -- ``_generate_code`` is mocked directly on the
plugin instance (its ``llm`` import is local to the method, not a
module-level name to monkeypatch, matching how this codebase's other
LLM-backed plugins are tested when the seam is a method rather than an
attribute).
"""
from __future__ import annotations

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
from prompt2render.harness.temporal_ir import SectionTiming, StateTiming, TemporalIR


@pytest.fixture(autouse=True)
def _no_alignment_file(monkeypatch):
    """align.load() sys.exit()s when no alignment file exists on disk --
    that's a SystemExit (BaseException), not caught by _load_timing's own
    `except Exception`, so it would kill these tests outright. None of
    these tests care about real narration timing, so short-circuit it to
    the same "no data" shape _load_timing already degrades gracefully from
    when sentences is empty."""

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


# --------------------------------------------------------------- flag off --

def test_flag_off_uses_freehand_prompt_and_writes_code_untouched(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": False})

    freehand_code = "class Scene01(Scene):\n    def construct(self):\n        self.wait(1)\n"
    generate = MagicMock(return_value=freehand_code)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    generate.assert_called_once()
    prompt = generate.call_args.args[0]
    assert "REFERENCE PATTERN" in prompt  # only the freehand prompt has this
    assert "compiled separately" not in prompt

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert written.strip() == freehand_code.strip()


def test_flag_absent_defaults_to_off():
    plugin = GeneratorManimPlugin()
    assert plugin.config.get("use_motion_compiler", False) is False


# ---------------------------------------------------------------- flag on --

def test_flag_on_uses_compiler_prompt_and_splices_construct(tmp_path):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True})

    setup_only_code = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
        "        self.title = Text('Intro')\n"
    )
    generate = MagicMock(return_value=setup_only_code)
    plugin._generate_code = generate

    plugin._generate_one(ctx, section)

    generate.assert_called_once()
    prompt = generate.call_args.args[0]
    assert "compiled separately" in prompt  # only the compiler-backed prompt has this
    assert "Do NOT define `construct(self)`" in prompt

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert written.count("def construct(self):") == 1
    assert "Create(self.circle)" in written
    assert "self.play(" in written

    # The LLM-authored portion (before the spliced construct) never wrote
    # any play/wait calls itself -- proving the compiler, not the LLM,
    # owns choreography.
    setup_portion = written.split("def construct(self):")[0]
    assert "self.play(" not in setup_portion
    assert "self.wait(" not in setup_portion


def test_compiler_failure_falls_back_to_setup_only_code(tmp_path, monkeypatch):
    ctx, section = _ctx_and_section(tmp_path)
    plugin = GeneratorManimPlugin({"use_motion_compiler": True})

    # No class definition at all -- _splice_construct_method raises ValueError.
    broken_code = "x = 1\n"
    generate = MagicMock(return_value=broken_code)
    plugin._generate_code = generate

    warnings: list[str] = []
    monkeypatch.setattr(cfg_module, "warn", lambda msg: warnings.append(msg))

    plugin._generate_one(ctx, section)

    assert any("motion compiler failed" in w for w in warnings)
    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert written.strip() == broken_code.strip()


def test_flag_on_falls_back_to_storyboard_plan_when_semantic_ir_absent(tmp_path):
    """_states_from_semantic_ir returns None without semantic_ir -- the
    compiler path must still work via the older storyboard-based lookup."""

    ctx, section = _ctx_and_section(tmp_path)
    ctx.semantic_ir = None
    ctx.storyboard_plan = {
        "sections": [
            {
                "index": 1,
                "stem": "01",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a circle.",
                        "transition": "progressive reveal",
                        "motion": [{"op": "Create", "target": "circle"}],
                    }
                ],
            }
        ]
    }
    plugin = GeneratorManimPlugin({"use_motion_compiler": True})

    setup_only_code = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
    )
    plugin._generate_code = MagicMock(return_value=setup_only_code)

    plugin._generate_one(ctx, section)

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    assert "Create(self.circle)" in written


def test_flag_on_prefers_context_temporal_ir_over_on_the_fly_computation(tmp_path):
    """Tier 2 Phase 5: when context.temporal_ir already has a SectionTiming
    for this stem, _generate_one must use ITS run_time/wait values, not
    recompute them on-the-fly -- proving the wiring, not just the fallback
    (already covered by the other tests in this file, which run with
    temporal_ir unset)."""

    ctx, section = _ctx_and_section(tmp_path)
    # A deliberately distinctive run_time no on-the-fly computation would
    # ever produce, so its presence in the output is unambiguous evidence
    # context.temporal_ir was actually consumed.
    ctx.temporal_ir = TemporalIR(
        schema_version="1.0",
        source_semantic_hash=ctx.semantic_ir.semantic_hash,
        sections=[
            SectionTiming(
                index=1,
                stem="01",
                target_duration=42.0,
                total_gap_seconds=0.0,
                states=[StateTiming(name="introduce", cue=0, run_time=13.37, wait=0.0)],
            )
        ],
    )

    plugin = GeneratorManimPlugin({"use_motion_compiler": True})
    setup_only_code = (
        "class Scene01(Scene):\n"
        "    def _state_introduce(self):\n"
        "        self.circle = Circle()\n"
    )
    plugin._generate_code = MagicMock(return_value=setup_only_code)

    plugin._generate_one(ctx, section)

    written = (tmp_path / "build" / "manim" / "scene_01.py").read_text(encoding="utf-8")
    # _compile_construct_method caps run_time at Create's natural duration
    # (1.4s) and pushes the rest into wait -- 13.37 - 1.4 = 11.97, so that
    # exact wait value is the unambiguous fingerprint that 13.37 (not some
    # on-the-fly-computed value) flowed all the way through.
    assert "self.wait(11.97)" in written
