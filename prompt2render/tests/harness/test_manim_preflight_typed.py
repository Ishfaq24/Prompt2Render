"""Typed Manim preflight: undefined identifiers, invalid API arguments
(Phase 18), and their finding-type classification."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.plugins.verifier_execution import _classify_manim_error
from prompt2render.scenes import validate_manim_source

manim = pytest.importorskip("manim", reason="deterministic preflight tests need manim installed")


VALID_SCENE = """
from manim import *

class Scene06(Scene):
    def construct(self):
        CAPTION_Y = -3.2
        caption = Text("hello", font_size=24)
        caption.move_to([0, CAPTION_Y, 0])
        self.play(Write(caption))
        self.wait(1)
"""


def test_valid_scene_passes_preflight():
    errors = validate_manim_source(VALID_SCENE)
    assert errors == []


def test_undefined_identifier_detected_before_render():
    """CAPPTION_Y (typo of CAPTION_Y) must be caught statically."""

    broken = VALID_SCENE.replace("CAPTION_Y, 0", "CAPPTION_Y, 0")

    errors = validate_manim_source(broken)

    assert any("CAPPTION_Y" in e and "not defined" in e for e in errors), errors


def test_align_to_buff_rejected():
    """align_to() has no buff= argument; next_to() does."""

    broken = """
from manim import *

class Scene07(Scene):
    def construct(self):
        a = Square()
        b = Circle()
        b.align_to(a, DOWN)
        b.align_to(a, buff=0.5)
        self.play(Create(a), Create(b))
        self.wait(1)
"""

    errors = validate_manim_source(broken)

    assert any(
        "align_to" in e and "buff" in e for e in errors
    ), errors


def test_next_to_buff_still_valid():
    """The fix suggestion itself must not be flagged: next_to accepts buff."""

    fine = """
from manim import *

class Scene08(Scene):
    def construct(self):
        a = Square()
        b = Circle()
        b.next_to(a, DOWN, buff=0.5)
        self.play(Create(a), Create(b))
        self.wait(1)
"""

    errors = validate_manim_source(fine)

    assert not any("buff" in e for e in errors), errors


# ------------------------------------------------------- classification ---

def test_classify_undefined_identifier():
    assert (
        _classify_manim_error("'CAPPTION_Y' is not defined (line 676)")
        == "undefined_identifier"
    )


def test_classify_invalid_api():
    assert (
        _classify_manim_error("align_to() does not accept 'buff=' (line 61)")
        == "invalid_manim_api"
    )


def test_classify_generic_execution_failure():
    assert _classify_manim_error("syntax error at line 4") == "execution_failure"


def test_preflight_findings_are_typed(tmp_path):
    """check_scene_artifact emits typed finding_types for Manim sources."""

    from prompt2render.harness.context import CodeArtifact, SceneContext, ScenePlanEntry
    from prompt2render.harness.plugins.verifier_execution import check_scene_artifact

    broken = VALID_SCENE.replace("CAPTION_Y, 0", "CAPPTION_Y, 0")

    source = tmp_path / "scene_06.py"
    source.write_text(broken, encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path)
    ctx.code_artifacts["06"] = CodeArtifact(stem="06", path=source)
    entry = ScenePlanEntry(index=6, stem="06", title="T")

    findings = check_scene_artifact(ctx, entry, gate=True)

    types = {f.get("finding_type") for f in findings}
    assert "undefined_identifier" in types


# ------------------------------------------- hallucinated MathTex methods ---

MATHTEX_METHOD_SCENE = """
from manim import *

class Scene02(Scene):
    def construct(self):
        vec_init = MathTex(r"psi")
        self.play(Write(vec_init))
        zeros = VGroup(*vec_init.get_parts_by_tex("0"))
        self.play(Indicate(zeros))
        self.wait(1)
"""


def test_hallucinated_mathtex_method_detected():
    """get_parts_by_tex is a Tex method; on MathTex it crashes mid-render
    with the cryptic Mobject.__getattr__ getter TypeError."""

    errors = validate_manim_source(MATHTEX_METHOD_SCENE)

    assert any(
        "get_parts_by_tex" in e and "does not exist" in e for e in errors
    ), errors


def test_real_mathtex_method_not_flagged():
    fine = MATHTEX_METHOD_SCENE.replace(
        "VGroup(*vec_init.get_parts_by_tex(\"0\"))",
        "vec_init.get_part_by_tex(\"0\")",
    )

    errors = validate_manim_source(fine)

    assert not any("get_part_by_tex" in e for e in errors), errors


def test_text_weight_stays_valid():
    """weight= is legitimate on Text -- only MathTex/Tex reject it."""

    fine = """
from manim import *

class Scene03(Scene):
    def construct(self):
        t = Text("emphasis", weight=BOLD)
        self.play(Write(t))
        self.wait(1)
"""

    assert validate_manim_source(fine) == []


def test_mathtex_weight_kwarg_rejected():
    """MathTex(..., weight=BOLD) crashes in Mobject.__init__ at render."""

    broken = """
from manim import *

class Scene04(Scene):
    def construct(self):
        label = MathTex(r"P=100", font_size=22, color=GREEN_B, weight=BOLD)
        self.play(Write(label))
        self.wait(1)
"""

    errors = validate_manim_source(broken)

    assert any(
        "weight" in e and "Text-only" in e for e in errors
    ), errors


def test_classify_undefined_method_and_routing():
    assert (
        _classify_manim_error(
            "MathTex.get_parts_by_tex() does not exist in the installed manim (line 8)"
        )
        == "undefined_method"
    )

    from prompt2render.harness.plugins.repair_router.policy import (
        StaticTableRoutingPolicy,
    )

    policy = StaticTableRoutingPolicy()
    assert policy.decide({"finding_type": "undefined_method"}) == ["generator_code"]

    from prompt2render.harness.evidence import REPAIR_TYPE_BY_FINDING_TYPE

    assert REPAIR_TYPE_BY_FINDING_TYPE["undefined_method"] == "manim_api_repair"


def test_preflight_emits_typed_findings_for_both_crash_classes(tmp_path):
    from prompt2render.harness.context import CodeArtifact, SceneContext, ScenePlanEntry
    from prompt2render.harness.plugins.verifier_execution import check_scene_artifact

    source = tmp_path / "scene_02.py"
    source.write_text(MATHTEX_METHOD_SCENE, encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path)
    ctx.code_artifacts["02"] = CodeArtifact(stem="02", path=source)
    entry = ScenePlanEntry(index=2, stem="02", title="T")

    findings = check_scene_artifact(ctx, entry, gate=True)

    types = {f.get("finding_type") for f in findings}
    assert "undefined_method" in types
