"""Network, cloud, and distributed system architecture widgets for cinematic Manim explainers."""

from __future__ import annotations

from typing import Any

# Color design tokens
CYAN = "#00F0FF"
AMBER = "#FFB703"
EMERALD = "#10B981"
ROSE = "#EF4444"
PURPLE = "#A855F7"
SLATE_BG = "#0F172A"
SLATE_BORDER = "#1E293B"
TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"

try:
    from manim import (
        DOWN,
        LEFT,
        ORIGIN,
        RIGHT,
        UP,
        Circle,
        Dot,
        Line,
        Rectangle,
        RoundedRectangle,
        Text,
        VGroup,
        VMobject,
    )
except ImportError:
    DOWN = (0, -1, 0)
    LEFT = (-1, 0, 0)
    RIGHT = (1, 0, 0)
    UP = (0, 1, 0)
    ORIGIN = (0, 0, 0)

    class VMobject:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            self.submobjects: list[Any] = []
            self.width = 1.0
            self.height = 1.0

        def move_to(self, point: Any) -> Any:
            return self

        def next_to(self, target: Any, direction: Any = None, buff: float = 0.25) -> Any:
            return self

        def set_color(self, color: Any) -> Any:
            return self

        def set_fill(self, *args: Any, **kwargs: Any) -> Any:
            return self

    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.submobjects = list(args)

        def add(self, *items: Any) -> Any:
            self.submobjects.extend(items)
            return self

        def arrange(self, direction: Any = DOWN, buff: float = 0.25) -> Any:
            return self

    class RoundedRectangle(VMobject):  # type: ignore
        pass

    class Rectangle(VMobject):  # type: ignore
        pass

    class Circle(VMobject):  # type: ignore
        pass

    class Dot(VMobject):  # type: ignore
        pass

    class Text(VMobject):  # type: ignore
        pass

    class Line(VMobject):  # type: ignore
        pass


class ServerNode(VGroup):
    """A glassmorphic server container node with title, subtitle, and glowing status dot."""

    def __init__(
        self,
        name: str = "Server",
        subtext: str = "",
        width: float = 2.8,
        height: float = 1.6,
        status: str = "active",
        accent_color: str = CYAN,
        bg_color: str = SLATE_BG,
        stroke_color: str = SLATE_BORDER,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.accent_color = accent_color
        status_colors = {
            "active": EMERALD,
            "warning": AMBER,
            "error": ROSE,
            "idle": "#64748B",
        }
        dot_color = status_colors.get(status.lower(), accent_color)

        # Glassmorphic card body
        self.card = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.15,
            stroke_color=stroke_color,
            stroke_width=2.5,
            fill_color=bg_color,
            fill_opacity=0.85,
        )

        # Status indicator dot on top-right
        self.status_dot = Dot(
            point=(width / 2.0 - 0.25, height / 2.0 - 0.25, 0),
            radius=0.08,
            color=dot_color,
        )

        # Title and subtext
        if subtext:
            self.title_label = Text(
                name,
                font_size=18,
                weight="BOLD",
                color=TEXT_PRIMARY,
            ).move_to((0, 0.2, 0))
            self.sub_label = Text(
                subtext,
                font_size=13,
                color=TEXT_MUTED,
            ).move_to((0, -0.25, 0))
            self.labels = VGroup(self.title_label, self.sub_label)
        else:
            self.title_label = Text(
                name,
                font_size=20,
                weight="BOLD",
                color=TEXT_PRIMARY,
            ).move_to((0, 0, 0))
            self.labels = VGroup(self.title_label)

        self.add(self.card, self.status_dot, self.labels)

    def set_status(self, status: str) -> None:
        colors = {
            "active": EMERALD,
            "warning": AMBER,
            "error": ROSE,
            "idle": "#64748B",
        }
        if hasattr(self.status_dot, "set_color"):
            self.status_dot.set_color(colors.get(status.lower(), CYAN))


class ClientCluster(VGroup):
    """Cluster of client browsers or user nodes."""

    def __init__(
        self,
        count: int = 3,
        label: str = "Web Clients",
        color: str = CYAN,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.nodes = []
        for _ in range(count):
            c_outer = Circle(radius=0.25, stroke_color=color, stroke_width=2.0)
            c_inner = Dot(radius=0.08, color=color)
            node = VGroup(c_outer, c_inner)
            self.nodes.append(node)

        self.node_group = VGroup(*self.nodes).arrange(DOWN, buff=0.35)
        self.label_text = Text(label, font_size=15, color=TEXT_MUTED).next_to(
            self.node_group, DOWN, buff=0.25
        )
        self.add(self.node_group, self.label_text)


class DatabaseNode(VGroup):
    """A stylized multi-tier database storage cylinder."""

    def __init__(
        self,
        name: str = "Database",
        width: float = 2.0,
        height: float = 1.8,
        color: str = PURPLE,
        bg_color: str = SLATE_BG,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.body = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.2,
            stroke_color=color,
            stroke_width=2.5,
            fill_color=bg_color,
            fill_opacity=0.85,
        )

        # Storage disk dividers
        h_third = height / 3.0
        line1 = Line(
            start=(-width / 2.0 + 0.15, h_third / 2.0, 0),
            end=(width / 2.0 - 0.15, h_third / 2.0, 0),
            stroke_color=color,
            stroke_width=1.5,
            stroke_opacity=0.5,
        )
        line2 = Line(
            start=(-width / 2.0 + 0.15, -h_third / 2.0, 0),
            end=(width / 2.0 - 0.15, -h_third / 2.0, 0),
            stroke_color=color,
            stroke_width=1.5,
            stroke_opacity=0.5,
        )

        self.label = Text(name, font_size=16, weight="BOLD", color=TEXT_PRIMARY).move_to(
            (0, 0, 0)
        )
        self.add(self.body, line1, line2, self.label)


class ConfigCodeCard(VGroup):
    """A polished macOS/Linux terminal-styled code window."""

    def __init__(
        self,
        code_lines: list[str],
        title: str = "nginx.conf",
        width: float = 5.5,
        font_size: int = 14,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        num_lines = max(1, len(code_lines))
        line_height = 0.32
        height = max(1.5, num_lines * line_height + 0.8)

        # Main window frame
        self.frame = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.15,
            stroke_color="#334155",
            stroke_width=2.0,
            fill_color="#090D16",
            fill_opacity=0.95,
        )

        # Header bar
        header_y = height / 2.0 - 0.2
        dot_red = Dot(point=(-width / 2.0 + 0.35, header_y, 0), radius=0.06, color=ROSE)
        dot_yellow = Dot(point=(-width / 2.0 + 0.55, header_y, 0), radius=0.06, color=AMBER)
        dot_green = Dot(point=(-width / 2.0 + 0.75, header_y, 0), radius=0.06, color=EMERALD)
        header_title = Text(title, font_size=12, color="#64748B").move_to((0, header_y, 0))
        header = VGroup(dot_red, dot_yellow, dot_green, header_title)

        # Code content lines
        rendered_lines = []
        for i, line_str in enumerate(code_lines):
            c_line = Text(
                line_str,
                font="Consolas" if font_size > 0 else "Courier",
                font_size=font_size,
                color="#38BDF8" if "{" in line_str or "}" in line_str else "#E2E8F0",
            )
            c_line.move_to((-width / 2.0 + 0.4 + c_line.width / 2.0, header_y - 0.35 - i * line_height, 0))
            rendered_lines.append(c_line)

        self.code_group = VGroup(*rendered_lines)
        self.add(self.frame, header, self.code_group)


class MetricBadge(VGroup):
    """Pill-shaped metric badge with auto-fitted value and label."""

    def __init__(
        self,
        label: str = "Throughput",
        value: str = "10K req/s",
        status: str = "good",
        font_size: int = 14,
        max_width: float = 4.8,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        colors = {
            "good": EMERALD,
            "warn": AMBER,
            "bad": ROSE,
            "error": ROSE,
            "active": CYAN,
            "info": CYAN,
            "warning": AMBER,
        }
        color = colors.get(status.lower(), CYAN)

        self.val_text = Text(value, font_size=font_size, weight="BOLD", color=color)
        self.lbl_text = Text(label, font_size=max(9, font_size - 4), color=TEXT_MUTED)

        # Ensure text is not excessively wide
        if hasattr(self.val_text, "width") and self.val_text.width > max_width - 0.4:
            self.val_text.scale_to_fit_width(max_width - 0.4)
        if hasattr(self.lbl_text, "width") and self.lbl_text.width > max_width - 0.4:
            self.lbl_text.scale_to_fit_width(max_width - 0.4)

        # Arrange label below value with clean vertical spacing
        text_group = VGroup(self.val_text, self.lbl_text).arrange(DOWN, buff=0.1)

        # Compute required pill dimensions dynamically
        req_width = max(2.6, text_group.width + 0.5)
        req_height = max(0.75, text_group.height + 0.28)

        self.pill = RoundedRectangle(
            width=req_width,
            height=req_height,
            corner_radius=min(0.25, req_height / 2.0),
            stroke_color=color,
            stroke_width=1.5,
            fill_color=SLATE_BG,
            fill_opacity=0.92,
        )

        text_group.move_to(self.pill.get_center())
        self.add(self.pill, text_group)

