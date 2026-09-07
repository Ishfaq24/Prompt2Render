"""Data structure visual components for Manim."""

from __future__ import annotations

from typing import Any

try:
    from manim import Circle, Line, Text, VGroup, VMobject
except ImportError:
    class VMobject:  # type: ignore
        pass
    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            self.submobjects = list(args)
        def add(self, *items: Any) -> Any:
            self.submobjects.extend(items)
            return self
    class Circle(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class Line(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class Text(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass


class BinaryTreeMobject(VGroup):
    """Hierarchical binary tree visual component."""

    def __init__(
        self,
        levels: int = 3,
        node_radius: float = 0.35,
        node_color: str = "#1f6feb",
        edge_color: str = "#8b949e",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.levels = levels
        self.node_radius = node_radius
        self.node_color = node_color
        self.edge_color = edge_color
        self.nodes: list[Any] = []
        self.edges: list[Any] = []

        # Recursively construct tree nodes and layout
        self._build_tree(level=0, max_levels=levels, x=0, y=1.5, x_offset=2.0)

    def _build_tree(
        self, level: int, max_levels: int, x: float, y: float, x_offset: float
    ) -> None:
        if level >= max_levels:
            return

        node = Circle(
            radius=self.node_radius,
            color=self.node_color,
            fill_opacity=0.9,
        )
        if hasattr(node, "move_to"):
            node.move_to((x, y, 0))
        self.nodes.append(node)
        self.add(node)

        if level + 1 < max_levels:
            child_y = y - 1.2
            left_x = x - x_offset
            right_x = x + x_offset

            edge_left = Line((x, y, 0), (left_x, child_y, 0), color=self.edge_color)
            edge_right = Line((x, y, 0), (right_x, child_y, 0), color=self.edge_color)
            self.edges.extend([edge_left, edge_right])
            self.add(edge_left, edge_right)

            self._build_tree(level + 1, max_levels, left_x, child_y, x_offset / 2.0)
            self._build_tree(level + 1, max_levels, right_x, child_y, x_offset / 2.0)
