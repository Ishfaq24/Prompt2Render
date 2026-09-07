"""Unit tests for Cinematic Camera Choreography & Visual Polish."""

from __future__ import annotations

from unittest.mock import MagicMock

from prompt2render.cinematic import (
    GlowAura,
    HeroMetricBadge,
    focus_on,
    pan_to,
    reset_frame,
    subtle_drift,
)


def test_hero_metric_badge():
    badge = HeroMetricBadge(
        label="Latency",
        value="12",
        unit="ms",
        width=3.5,
        height=1.4,
    )
    assert hasattr(badge, "bg")
    assert hasattr(badge, "val_text")
    assert hasattr(badge, "lbl_text")
    assert len(badge.submobjects) == 3


def test_glow_aura():
    from manim import Circle
    target = Circle(radius=1.0)
    aura = GlowAura(target, num_layers=3)
    assert len(aura.submobjects) == 3


def test_camera_focus_on():
    frame = MagicMock()
    animate_mock = MagicMock()
    frame.animate.set.return_value = animate_mock
    frame.animate.return_value = frame.animate

    class DummyTarget:
        def get_center(self):
            return (2.0, 1.0, 0.0)
        width = 4.0

    target = DummyTarget()
    focus_on(frame, target, scale=0.5)

    assert frame.animate.called


def test_camera_pan_and_reset():
    frame = MagicMock()
    frame.animate.return_value = frame.animate

    class DummyTarget:
        def get_center(self):
            return (-1.5, 0.5, 0.0)

    pan_to(frame, DummyTarget())
    assert frame.animate.called

    reset_frame(frame, default_width=14.22)
    assert frame.animate.called

    subtle_drift(frame, distance=0.4)
    assert frame.animate.called
