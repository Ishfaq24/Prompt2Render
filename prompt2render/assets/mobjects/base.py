"""Base classes and utilities for reusable Manim Mobjects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from manim import SVGMobject, VMobject, VGroup, Rectangle, Text, config
except ImportError:
    # Graceful stub when running in an environment without Manim installed
    class VMobject:  # type: ignore
        pass
    class VGroup(VMobject):  # type: ignore
        pass
    class SVGMobject(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class Rectangle(VMobject):  # type: ignore
        pass
    class Text(VMobject):  # type: ignore
        pass


class P2RSVGMobject(SVGMobject):
    """SVGMobject with automatic aspect-ratio normalization and palette tinting."""

    def __init__(
        self,
        file_path: str | Path,
        target_width: float = 2.0,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        path_str = str(file_path)
        super().__init__(path_str, **kwargs)
        if hasattr(self, "set_width"):
            self.set_width(target_width)
        if color and hasattr(self, "set_color"):
            self.set_color(color)
