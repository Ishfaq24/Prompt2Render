"""Cinematic Camera Choreography & Visual Polish Engine for Manim.

Elevates Prompt2Render video production value from flat slide-like animations to
dynamic, cinematic visual storytelling (3Blue1Brown & Kurzgesagt quality).
"""

from __future__ import annotations

from typing import Any, Sequence

try:
    from manim import (
        BLUE,
        DEGREES,
        DOWN,
        GRAY,
        GREEN,
        LEFT,
        ORIGIN,
        PI,
        RIGHT,
        UP,
        WHITE,
        YELLOW,
        Animation,
        Circle,
        Dot,
        FadeIn,
        FadeOut,
        Group,
        Line,
        Mobject,
        Rectangle,
        RoundedRectangle,
        SurroundingRectangle,
        Text,
        VGroup,
        VMobject,
        rate_functions,
    )
except ImportError:
    # Allow headless usage/tests without manim runtime
    Mobject = object
    VMobject = object
    VGroup = object
    Line = object
    DEGREES = 3.141592653589793 / 180.0
    PI = 3.141592653589793
    ORIGIN = (0.0, 0.0, 0.0)
    UP = (0.0, 1.0, 0.0)
    DOWN = (0.0, -1.0, 0.0)
    LEFT = (-1.0, 0.0, 0.0)
    RIGHT = (1.0, 0.0, 0.0)
    WHITE = "#ffffff"
    GRAY = "#888888"
    BLUE = "#58c4dd"
    YELLOW = "#ffff00"


# ---------------------------------------------------------------------------
# 1. Camera Choreography Helpers (for MovingCameraScene)
# ---------------------------------------------------------------------------

def focus_on(
    camera_frame: Any,
    target: Any,
    *,
    scale: float = 0.65,
    buff: float = 0.5,
    run_time: float = 1.2,
    rate_func: Any = None,
) -> Any:
    """Generate camera animation to smoothly zoom in on and frame a target Mobject.
    
    Usage in MovingCameraScene:
        self.play(focus_on(self.camera.frame, hero_node))
    """
    if rate_func is None:
        try:
            rate_func = rate_functions.smooth
        except Exception:
            rate_func = None

    target_center = target.get_center()
    target_width = getattr(target, "width", 4.0) + buff * 2.0
    # Manim standard 16:9 width is ~14.22
    target_frame_width = max(target_width * (1.0 / scale), 5.0)

    anim = camera_frame.animate(run_time=run_time, rate_func=rate_func).set(
        width=target_frame_width
    ).move_to(target_center)
    return anim


def pan_to(
    camera_frame: Any,
    target: Any,
    *,
    run_time: float = 1.0,
    rate_func: Any = None,
) -> Any:
    """Translate the camera frame center to target while maintaining current zoom level."""
    if rate_func is None:
        try:
            rate_func = rate_functions.smooth
        except Exception:
            rate_func = None

    target_center = target.get_center()
    return camera_frame.animate(run_time=run_time, rate_func=rate_func).move_to(target_center)


def reset_frame(
    camera_frame: Any,
    *,
    default_width: float = 14.22,
    run_time: float = 1.2,
    rate_func: Any = None,
) -> Any:
    """Restore the camera frame back to the global 16:9 overview position."""
    if rate_func is None:
        try:
            rate_func = rate_functions.smooth
        except Exception:
            rate_func = None

    return camera_frame.animate(run_time=run_time, rate_func=rate_func).set(
        width=default_width
    ).move_to(ORIGIN)


def subtle_drift(
    camera_frame: Any,
    direction: Any = RIGHT,
    distance: float = 0.35,
    run_time: float = 4.0,
) -> Any:
    """Subtle continuous camera drift to keep long explanatory pauses dynamic."""
    try:
        rf = rate_functions.linear
    except Exception:
        rf = None
    shift_vector = direction * distance
    return camera_frame.animate(run_time=run_time, rate_func=rf).shift(shift_vector)


# ---------------------------------------------------------------------------
# 2. Visual Polish Mobjects: Glow, Spotlight & Hero Badges
# ---------------------------------------------------------------------------

class GlowAura(VGroup):
    """Soft glowing concentric halo surrounding a target element."""

    def __init__(
        self,
        target: Any,
        color: Any = YELLOW,
        num_layers: int = 4,
        max_buff: float = 0.35,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        for i in range(num_layers):
            progress = (i + 1) / num_layers
            buff = max_buff * progress
            opacity = 0.25 * (1.0 - progress) + 0.05
            ring = SurroundingRectangle(
                target,
                color=color,
                buff=buff,
                corner_radius=0.15,
                stroke_width=2.5,
                stroke_opacity=opacity,
            )
            self.add(ring)


class HeroMetricBadge(VGroup):
    """Sleek cinematic KPI/metric badge with high-contrast label and value."""

    def __init__(
        self,
        label: str,
        value: str,
        unit: str = "",
        color: Any = BLUE,
        width: float = 3.2,
        height: float = 1.3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        bg = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.15,
            fill_color="#121826",
            fill_opacity=0.92,
            stroke_color=color,
            stroke_width=2.0,
        )

        full_val = f"{value} {unit}".strip()
        val_text = Text(full_val, font_size=26, color=WHITE, weight="BOLD")
        lbl_text = Text(label.upper(), font_size=13, color=GRAY)

        val_text.move_to(bg.get_center() + UP * 0.15)
        lbl_text.move_to(bg.get_center() + DOWN * 0.3)

        self.add(bg, val_text, lbl_text)
        self.bg = bg
        self.val_text = val_text
        self.lbl_text = lbl_text


# ---------------------------------------------------------------------------
# 3. 3D Camera & Orientation Helpers (for ThreeDScene)
# ---------------------------------------------------------------------------

def orbit_3d_camera(
    scene: Any,
    *,
    delta_theta: float = 45.0,
    phi: float | None = None,
    zoom: float | None = None,
    run_time: float = 2.5,
    rate_func: Any = None,
) -> None:
    """Smoothly rotate 3D camera around the target azimuth in degrees.
    
    Usage in ThreeDScene:
        orbit_3d_camera(self, delta_theta=60.0, run_time=3.0)
    """
    if rate_func is None:
        try:
            rate_func = rate_functions.smooth
        except Exception:
            rate_func = None

    curr_theta = getattr(scene.camera, "theta", 0.0) if hasattr(scene, "camera") else 0.0
    new_theta = curr_theta + delta_theta * DEGREES

    kwargs: dict[str, Any] = {
        "theta": new_theta,
        "run_time": run_time,
    }
    if rate_func is not None:
        kwargs["rate_func"] = rate_func
    if phi is not None:
        kwargs["phi"] = phi * DEGREES
    if zoom is not None:
        kwargs["zoom"] = zoom

    if hasattr(scene, "move_camera"):
        scene.move_camera(**kwargs)


def cinematic_3d_pitch_yaw(
    scene: Any,
    *,
    phi: float = 75.0,
    theta: float = -45.0,
    zoom: float = 1.0,
    run_time: float = 2.0,
    rate_func: Any = None,
) -> None:
    """Transition the 3D camera to a cinematic isometric/oblique perspective.
    
    Usage in ThreeDScene:
        cinematic_3d_pitch_yaw(self, phi=70, theta=-45, zoom=1.1, run_time=2.0)
    """
    if rate_func is None:
        try:
            rate_func = rate_functions.smooth
        except Exception:
            rate_func = None

    kwargs: dict[str, Any] = {
        "phi": phi * DEGREES,
        "theta": theta * DEGREES,
        "zoom": zoom,
        "run_time": run_time,
    }
    if rate_func is not None:
        kwargs["rate_func"] = rate_func

    if hasattr(scene, "move_camera"):
        scene.move_camera(**kwargs)


def create_3d_grid_plane(
    *,
    size: float = 6.0,
    step: float = 1.0,
    color: str = "#30363d",
    stroke_width: float = 1.5,
) -> VGroup:
    """Generate a stylized 3D coordinate ground grid in the xy-plane (z=0)."""
    grid = VGroup()
    half = size / 2.0
    steps = int(size / step) + 1

    try:
        import numpy as np
    except ImportError:
        np = None

    for i in range(steps):
        coord = -half + i * step
        if np is not None:
            line_x = Line(
                start=np.array([-half, coord, 0.0]),
                end=np.array([half, coord, 0.0]),
                color=color,
                stroke_width=stroke_width,
            )
            line_y = Line(
                start=np.array([coord, -half, 0.0]),
                end=np.array([coord, half, 0.0]),
                color=color,
                stroke_width=stroke_width,
            )
        else:
            line_x = Line(start=[-half, coord, 0.0], end=[half, coord, 0.0], color=color, stroke_width=stroke_width)
            line_y = Line(start=[coord, -half, 0.0], end=[coord, half, 0.0], color=color, stroke_width=stroke_width)
        grid.add(line_x, line_y)

    return grid

