"""Unit tests for Manim dynamic spatial layout containers (AutoVStack, AutoHStack, SafeCaptionZone)."""

import pytest
from manim import VMobject, UP, DOWN, LEFT, RIGHT, Rectangle
from prompt2render.assets.mobjects.stages import (
    AutoVStack,
    AutoHStack,
    SafeCaptionZone,
    AnnotatedCard,
)


def make_box(width: float = 2.0, height: float = 1.0, y: float = 0.0) -> Rectangle:
    """Helper to create a concrete Manim Rectangle for layout testing."""
    r = Rectangle(width=width, height=height)
    r.move_to([0.0, y, 0.0])
    return r


def test_autovstack_spacing():
    m1 = make_box(width=3.0, height=1.0, y=2.0)
    m2 = make_box(width=3.0, height=1.0, y=0.0)
    m3 = make_box(width=3.0, height=1.0, y=0.0)

    stack = AutoVStack(m1, m2, m3, buff=0.5)

    assert m1.get_center()[1] == 2.0
    assert pytest.approx(m2.get_center()[1]) == 0.5
    assert pytest.approx(m3.get_center()[1]) == -1.0


def test_autovstack_add_item():
    m1 = make_box(width=2.0, height=1.0, y=1.0)
    stack = AutoVStack(m1, buff=0.4)
    m2 = make_box(width=2.0, height=1.0)
    stack.add_item(m2)

    assert pytest.approx(m2.get_center()[1]) == -0.4


def test_autohstack_spacing():
    m1 = make_box(width=2.0, height=1.0)
    m2 = make_box(width=2.0, height=1.0)
    m3 = make_box(width=2.0, height=1.0)

    stack = AutoHStack(m1, m2, m3, buff=0.5, max_width=12.0)

    assert pytest.approx(m1.get_center()[0]) == 0.0
    assert pytest.approx(m2.get_center()[0]) == 2.5
    assert pytest.approx(m3.get_center()[0]) == 5.0


def test_safe_caption_zone_clamp():
    # mobject bottom is at -3.0 (inside caption zone [-3.8, -2.5])
    mob = make_box(width=4.0, height=1.0, y=-2.5)
    SafeCaptionZone.clamp_above(mob, margin=0.2)
    assert mob.get_bottom()[1] >= -2.301


def test_annotated_card_instantiation():
    card = AnnotatedCard(
        title="Active Connection",
        body=make_box(width=2.0, height=1.0),
        badge_text="ESTABLISHED",
        width=5.0,
        height=3.0,
    )
    assert len(card.elements) >= 3
    assert card.title_text is not None

