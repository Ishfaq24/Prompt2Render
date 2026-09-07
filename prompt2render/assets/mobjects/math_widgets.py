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
