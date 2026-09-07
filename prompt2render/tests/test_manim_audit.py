"""Unit tests for ManimLayoutAuditor (AABB collision and bounds checker)."""

import pytest
from manim import Rectangle, Text, UP, DOWN, LEFT, RIGHT
from prompt2render.manim_audit import ManimLayoutAuditor


def test_manim_auditor_detects_overlap():
    # Two overlapping rectangles
    r1 = Rectangle(width=3.0, height=2.0)
    r1.move_to([0.0, 0.0, 0.0])
    setattr(r1, "name", "box_A")

    r2 = Rectangle(width=3.0, height=2.0)
    r2.move_to([0.5, 0.5, 0.0])
    setattr(r2, "name", "box_B")

    warnings = ManimLayoutAuditor.audit_mobjects([r1, r2])
    assert any("WARN [overlap]" in w for w in warnings)
    assert any("box_A" in w and "box_B" in w for w in warnings)


def test_manim_auditor_passes_non_overlapping():
    r1 = Rectangle(width=2.0, height=1.0)
    r1.move_to([-3.0, 0.0, 0.0])
    setattr(r1, "name", "box_left")

    r2 = Rectangle(width=2.0, height=1.0)
    r2.move_to([3.0, 0.0, 0.0])
    setattr(r2, "name", "box_right")

    warnings = ManimLayoutAuditor.audit_mobjects([r1, r2])
    assert len(warnings) == 0


def test_manim_auditor_detects_caption_zone_trespass():
    r1 = Rectangle(width=2.0, height=1.0)
    r1.move_to([0.0, -3.2, 0.0])
    setattr(r1, "name", "intruding_box")

    warnings = ManimLayoutAuditor.audit_mobjects([r1])
    assert any("WARN [caption_collision]" in w for w in warnings)
    assert any("intruding_box" in w for w in warnings)


def test_manim_auditor_detects_offframe():
    r1 = Rectangle(width=4.0, height=2.0)
    r1.move_to([8.0, 0.0, 0.0])
    setattr(r1, "name", "offframe_box")

    warnings = ManimLayoutAuditor.audit_mobjects([r1])
    assert any("WARN [offframe]" in w for w in warnings)


def test_manim_auditor_auto_nudge_resolves_overlap():
    r1 = Rectangle(width=3.0, height=2.0)
    r1.move_to([0.0, 0.0, 0.0])
    setattr(r1, "name", "box_A")

    r2 = Rectangle(width=3.0, height=2.0)
    r2.move_to([0.5, 0.5, 0.0])
    setattr(r2, "name", "box_B")

    # Initial audit detects overlap
    assert len(ManimLayoutAuditor.audit_mobjects([r1, r2])) > 0

    # Auto-nudge resolves the collision
    adj = ManimLayoutAuditor.auto_nudge_mobjects([r1, r2])
    assert adj > 0

    # After nudging, audit reports no overlap warnings
    warnings = ManimLayoutAuditor.audit_mobjects([r1, r2])
    assert not any("WARN [overlap]" in w for w in warnings)


def test_heal_manim_source_cinematic_and_symbolic_imports():
    from prompt2render.scenes import heal_manim_source

    code = """
class Scene01(Scene):
    def construct(self):
        badge = HeroMetricBadge("METRIC", "100")
        steps = trace_sorting([3, 1, 2], "bubble")
        self.play(focus_on(self.camera.frame, badge))
"""
    healed = heal_manim_source(code)
    assert "from prompt2render.cinematic import" in healed
    assert "focus_on" in healed
    assert "HeroMetricBadge" in healed
    assert "from prompt2render.symbolic_engine import" in healed
    assert "trace_sorting" in healed

