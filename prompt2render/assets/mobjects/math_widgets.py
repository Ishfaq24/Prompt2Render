"""Math and grid visual components for Manim."""

from __future__ import annotations

from typing import Any

try:
    from manim import Axes, NumberPlane, VGroup, VMobject
except ImportError:
    class VMobject:  # type: ignore
        pass
    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            self.submobjects = list(args)
    class NumberPlane(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass


class CoordinateGridMobject(VGroup):
    """Clean 2D Cartesian coordinate grid."""

    def __init__(
        self,
        x_range: list[float] | tuple[float, ...] = (-5, 5, 1),
        y_range: list[float] | tuple[float, ...] = (-3, 3, 1),
        axis_color: str = "#8b949e",
        grid_color: str = "#30363d",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.x_range = x_range
        self.y_range = y_range
        plane = NumberPlane(
            x_range=x_range,
            y_range=y_range,
            axis_config={"color": axis_color},
            background_line_style={"stroke_color": grid_color, "stroke_width": 1},
        )
        if hasattr(self, "add"):
            self.add(plane)


class AnimatedCurveMobject(VGroup):
    """A function curve on coordinate axes with animated drawing and tangent.

    Usage::

        curve = AnimatedCurveMobject(lambda x: x**2, x_range=(-3, 3))
        self.add(curve.axes)
        self.play(curve.draw_curve())
        self.play(curve.show_tangent(x=1.0))
    """

    def __init__(
        self,
        func,
        x_range: tuple[float, float] = (-4.0, 4.0),
        *,
        curve_color: Any = None,
        axes_color: Any = None,
        width: float = 6.0,
        height: float = 4.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        try:
            from manim import Axes, ParametricFunction
            curve_color = curve_color or BLUE
            axes_color = axes_color or GRAY
            self._func = func
            self._x_range = x_range
            self._width = width
            self._height = height
            x_len = width
            y_len = height
            self.axes = Axes(
                x_range=[x_range[0], x_range[1], 1],
                y_range=[-height / 2, height / 2, 1],
                x_length=x_len,
                y_length=y_len,
                axis_config={"color": axes_color, "stroke_width": 2},
                tips=False,
            )
            self._curve_mob = self.axes.plot(
                func,
                x_range=list(x_range),
                color=curve_color,
                stroke_width=3,
            )
            self.add(self.axes)
            self._curve_color = curve_color
        except Exception:
            self.axes = VGroup()
            self._curve_mob = VGroup()
            self._curve_color = BLUE

    def draw_curve(self, run_time: float = 2.0) -> Any:
        """Return a Create animation that draws the curve onto the axes."""
        try:
            from manim import Create, rate_functions
            return Create(self._curve_mob, run_time=run_time,
                          rate_func=rate_functions.ease_in_out_sine)
        except Exception:
            from manim import FadeIn
            return FadeIn(self._curve_mob, run_time=run_time)

    def show_tangent(self, x: float, run_time: float = 0.8) -> Any:
        """Return a FadeIn animation for a tangent line at x."""
        try:
            from manim import TangentLine, Create, YELLOW
            tangent = TangentLine(
                self._curve_mob, alpha=(x - self._x_range[0]) / (self._x_range[1] - self._x_range[0]),
                length=2.5,
                color=YELLOW,
                stroke_width=3,
            )
            self.add(tangent)
            return Create(tangent, run_time=run_time)
        except Exception:
            from manim import FadeIn
            return FadeIn(VGroup(), run_time=run_time)
