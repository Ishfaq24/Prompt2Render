"""Tests for the source-level Manim layout nudger."""
from prompt2render.manim_nudge import nudge_source


def test_parallel_down_anchoring_fixed():
    code = """
item1 = Text("A")
item2 = Text("B")
item1.next_to(box, DOWN, buff=0.2)
item2.next_to(box, DOWN, buff=0.4)
"""
    result, n = nudge_source(code)
    assert n > 0
    assert "item2.next_to(item1, DOWN" in result


def test_no_false_positive_different_anchors():
    code = """
item1.next_to(box_a, DOWN, buff=0.3)
item2.next_to(box_b, DOWN, buff=0.3)
"""
    result, n = nudge_source(code)
    # Different anchors — no fix should be applied
    assert n == 0
    assert result == code


def test_caption_zone_trespass_clamped():
    code = "element.move_to((3.0, -3.5, 0))"
    result, n = nudge_source(code)
    assert n > 0
    assert "-2.2" in result


def test_caption_not_clamped():
    code = "caption.move_to((0, -3.2, 0))"
    result, n = nudge_source(code)
    # 'caption' in varname — must NOT be clamped
    assert n == 0


def test_clean_source_unchanged():
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        t = Text("Hello")
        t.move_to((0, 1.5, 0))
        self.add(t)
        self.wait(2)
"""
    result, n = nudge_source(code)
    assert n == 0
    assert result == code


def test_idempotent():
    code = """
item1.next_to(box, DOWN, buff=0.2)
item2.next_to(box, DOWN, buff=0.4)
"""
    result1, _ = nudge_source(code)
    result2, n2 = nudge_source(result1)
    # Second pass should apply zero additional fixes
    assert n2 == 0
