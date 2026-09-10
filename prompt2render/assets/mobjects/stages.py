"""Universal Spatial Layout Stages for collision-free Manim animation.

Provides 5 mathematically bounded layout archetypes:
1. FlowStage: Sequential multi-stage pipelines and protocols.
2. SplitStage: Side-by-side comparison, code vs architecture, or before vs after.
3. HeroFocusStage: Central complex visualization with perimeter callout badges.
4. HierarchyStage: Balanced hierarchical trees and graphs.
5. BenchmarkStage: Multi-metric KPI cards and comparison grids.
"""

from __future__ import annotations

from typing import Any

# Global Design Tokens
OBSIDIAN_BG = "#0B0F19"
SLATE_BORDER = "#1E293B"
SLATE_CARD = "#0F172A"
CYAN_ACCENT = "#00F0FF"
AMBER_SPARK = "#FFB703"
EMERALD_GOOD = "#10B981"
ROSE_BAD = "#EF4444"
PURPLE_MATH = "#A855F7"
TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"

try:
    from manim import (
        DOWN,
        LEFT,
        ORIGIN,
        RIGHT,
        UP,
        Arrow,
        CurvedArrow,
        Dot,
        Line,
        Rectangle,
        RoundedRectangle,
        Text,
        Group,
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

        def scale_to_fit_width(self, width: float) -> Any:
            return self

    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.submobjects = list(args)

        def add(self, *items: Any) -> Any:
            self.submobjects.extend(items)
            return self

        def arrange(self, direction: Any = RIGHT, buff: float = 0.4) -> Any:
            return self

    class RoundedRectangle(VMobject):  # type: ignore
        pass

    class Rectangle(VMobject):  # type: ignore
        pass

    class Dot(VMobject):  # type: ignore
        pass

    class Text(VMobject):  # type: ignore
        pass

    class Line(VMobject):  # type: ignore
        pass

    class Arrow(VMobject):  # type: ignore
        pass

    class CurvedArrow(VMobject):  # type: ignore
        pass


class FlowStage(VGroup):
    """Linear pipeline stage connecting sequential process nodes."""

    def __init__(
        self,
        nodes: list[Any],
        labels: list[str] | None = None,
        direction: Any = RIGHT,
        buff: float = 0.6,
        y_offset: float = 0.3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.nodes = list(nodes)
        self.conduits: list[Any] = []

        if not self.nodes:
            return

        # Arrange nodes linearly with bounded width
        self.node_group = VGroup(*self.nodes).arrange(direction, buff=buff)
        if hasattr(self.node_group, "move_to"):
            self.node_group.move_to((0, y_offset, 0))

        # Build connecting arrows / conduits between adjacent nodes
        for i in range(len(self.nodes) - 1):
            n1 = self.nodes[i]
            n2 = self.nodes[i + 1]
            p1 = n1.get_right() if hasattr(n1, "get_right") else (0, 0, 0)
            p2 = n2.get_left() if hasattr(n2, "get_left") else (1, 0, 0)
            arrow = Arrow(
                start=p1,
                end=p2,
                buff=0.15,
                color=CYAN_ACCENT,
                stroke_width=2.5,
                max_tip_length_to_length_ratio=0.25,
            )
            self.conduits.append(arrow)

        self.conduit_group = VGroup(*self.conduits)
        self.add(self.node_group, self.conduit_group)

    def pulse_signal(self, from_index: int, to_index: int, color: str = AMBER_SPARK) -> Any:
        """Returns an animation helper for sending a particle along the conduit."""
        if 0 <= from_index < len(self.nodes) and 0 <= to_index < len(self.nodes):
            n1 = self.nodes[from_index]
            n2 = self.nodes[to_index]
            p1 = n1.get_right() if hasattr(n1, "get_right") else (0, 0, 0)
            p2 = n2.get_left() if hasattr(n2, "get_left") else (1, 0, 0)
            dot = Dot(point=p1, radius=0.09, color=color)
            return dot, p2
        return None


class SplitStage(Group):
    """Mathematically isolated side-by-side comparison stage (Left vs Right)."""

    def __init__(
        self,
        left: Any,
        right: Any,
        left_title: str = "",
        right_title: str = "",
        divider: bool = True,
        y_offset: float = 0.2,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.left_item = left
        self.right_item = right

        # Position left item in the left slot: center around x = -3.4
        if hasattr(self.left_item, "move_to"):
            self.left_item.move_to((-3.4, y_offset, 0))

        # Position right item in the right slot: center around x = 3.4
        if hasattr(self.right_item, "move_to"):
            self.right_item.move_to((3.4, y_offset, 0))

        self.elements = [self.left_item, self.right_item]

        self.left_title = None
        if left_title:
            t_left = Text(left_title, font_size=16, weight="BOLD", color=CYAN_ACCENT)
            if hasattr(t_left, "next_to"):
                t_left.next_to(self.left_item, UP, buff=0.3)
            self.left_title = t_left
            self.elements.append(t_left)

        self.right_title = None
        if right_title:
            t_right = Text(right_title, font_size=16, weight="BOLD", color=PURPLE_MATH)
            if hasattr(t_right, "next_to"):
                t_right.next_to(self.right_item, UP, buff=0.3)
            self.right_title = t_right
            self.elements.append(t_right)

        self.divider = None
        if divider:
            div_line = Line(
                start=(0, 2.2, 0),
                end=(0, -2.2, 0),
                stroke_color=SLATE_BORDER,
                stroke_width=1.5,
                stroke_opacity=0.6,
            )
            self.divider = div_line
            self.elements.append(div_line)

        self.add(*self.elements)


class MediaCard(Group):
    """Photographic / visual media card with stylish border and badge."""

    def __init__(
        self,
        media: Any,
        label: str = "Real-World Reference",
        badge_color: str = CYAN_ACCENT,
        border_color: str = SLATE_BORDER,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.media = media
        self.elements = [self.media]

        if hasattr(media, "width") and hasattr(media, "height"):
            w = getattr(media, "width", 5.0)
            h = getattr(media, "height", 3.2)
            frame = RoundedRectangle(
                width=w + 0.1,
                height=h + 0.1,
                corner_radius=0.1,
                stroke_color=border_color,
                stroke_width=2.0,
            )
            if hasattr(self.media, "get_center"):
                frame.move_to(self.media.get_center())
            self.elements.append(frame)

        if label:
            lbl = Text(label.upper(), font_size=12, weight="BOLD", color=badge_color)
            if hasattr(self.media, "get_critical_point") and hasattr(lbl, "next_to"):
                try:
                    lbl.next_to(self.media, DOWN, buff=0.2)
                except Exception:
                    h = getattr(self.media, "height", 3.0)
                    lbl.move_to(self.media.get_center() + DOWN * (h / 2.0 + 0.25))
            elif hasattr(self.media, "get_center") and hasattr(lbl, "move_to"):
                h = getattr(self.media, "height", 3.0)
                lbl.move_to(self.media.get_center() + DOWN * (h / 2.0 + 0.25))
            self.elements.append(lbl)

        self.add(*self.elements)


class HeroFocusStage(VGroup):
    """Central hero visualization with peripheral callout badges."""

    def __init__(
        self,
        hero: Any,
        badges: list[Any] | None = None,
        title: str = "",
        y_offset: float = 0.2,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.hero = hero
        if hasattr(self.hero, "move_to"):
            self.hero.move_to((0, y_offset, 0))

        self.elements = [self.hero]

        if title:
            t = Text(title, font_size=18, weight="BOLD", color=TEXT_PRIMARY)
            if hasattr(t, "next_to"):
                t.next_to(self.hero, UP, buff=0.4)
            self.elements.append(t)

        if badges:
            # Arrange badges below or to the side of the hero
            badge_group = VGroup(*badges).arrange(RIGHT, buff=0.4)
            if hasattr(badge_group, "next_to"):
                badge_group.next_to(self.hero, DOWN, buff=0.45)
            self.elements.append(badge_group)

        self.add(*self.elements)


class BenchmarkStage(VGroup):
    """Performance & metrics comparison stage with cards arranged in a grid."""

    def __init__(
        self,
        cards: list[Any],
        title: str = "Performance Metrics",
        columns: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.cards = list(cards)

        self.card_group = VGroup(*self.cards).arrange(RIGHT, buff=0.5)
        if hasattr(self.card_group, "move_to"):
            self.card_group.move_to((0, 0.1, 0))

        self.title_label = Text(title, font_size=18, weight="BOLD", color=CYAN_ACCENT)
        if hasattr(self.title_label, "next_to"):
            self.title_label.next_to(self.card_group, UP, buff=0.4)

        self.add(self.title_label, self.card_group)


class AutoVStack(VGroup):
    """Dynamic vertical container that stacks elements with collision-free spacing.
    
    Automatically computes heights, clamps to canvas safe zones (y >= -2.4),
    and arranges children strictly sequentially so no two elements overlap.
    """

    def __init__(
        self,
        *items: Any,
        buff: float = 0.25,
        align: str = "center",  # "center", "left", "right"
        safe_margin_bottom: float = -2.4,
        max_height: float = 6.0,
        max_width: float = 5.2,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.buff = buff
        self.align = align
        self.safe_margin_bottom = safe_margin_bottom
        self.max_height = max_height
        self.max_width = max_width
        self.items_list = list(items)

        if self.items_list:
            self.add(*self.items_list)
            aligned_edge = ORIGIN if align == "center" else (LEFT if align == "left" else RIGHT)
            for i in range(1, len(self.items_list)):
                self.items_list[i].next_to(self.items_list[i - 1], DOWN, buff=self.buff, aligned_edge=aligned_edge)
            # Auto-scale width and height if stack exceeds container limits
            if hasattr(self, "width") and hasattr(self, "scale_to_fit_width"):
                if self.width > self.max_width:
                    self.scale_to_fit_width(self.max_width)
            if hasattr(self, "height") and hasattr(self, "scale_to_fit_height"):
                if self.height > self.max_height:
                    self.scale_to_fit_height(self.max_height)

    def add_item(self, item: Any) -> AutoVStack:
        """Add a new item to the bottom of the stack, maintaining spacing."""
        aligned_edge = ORIGIN if self.align == "center" else (LEFT if self.align == "left" else RIGHT)
        if self.items_list:
            item.next_to(self.items_list[-1], DOWN, buff=self.buff, aligned_edge=aligned_edge)
        self.items_list.append(item)
        self.add(item)
        if hasattr(self, "width") and hasattr(self, "scale_to_fit_width"):
            if self.width > self.max_width:
                self.scale_to_fit_width(self.max_width)
        if hasattr(self, "height") and hasattr(self, "scale_to_fit_height"):
            if self.height > self.max_height:
                self.scale_to_fit_height(self.max_height)
        return self


class AutoHStack(VGroup):
    """Dynamic horizontal container that lays out elements with collision-free spacing.
    
    Automatically clamps total width within canvas bounds (width <= 12.5).
    """

    def __init__(
        self,
        *items: Any,
        buff: float = 0.35,
        max_width: float = 12.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.buff = buff
        self.max_width = max_width
        self.items_list = list(items)

        if self.items_list:
            self.add(*self.items_list)
            for i in range(1, len(self.items_list)):
                self.items_list[i].next_to(self.items_list[i - 1], RIGHT, buff=self.buff)
            if hasattr(self, "width") and hasattr(self, "scale_to_fit_width"):
                if getattr(self, "width", 0) > self.max_width:
                    self.scale_to_fit_width(self.max_width)

    def add_item(self, item: Any) -> AutoHStack:
        """Add a new item to the right of the stack, maintaining spacing."""
        if self.items_list:
            item.next_to(self.items_list[-1], RIGHT, buff=self.buff)
        self.items_list.append(item)
        self.add(item)
        if hasattr(self, "width") and hasattr(self, "scale_to_fit_width"):
            if getattr(self, "width", 0) > self.max_width:
                self.scale_to_fit_width(self.max_width)
        return self


class SafeCaptionZone(VGroup):
    """Safe zone guardian and persistent banner for subtitles and bottom captions.
    
    Enforces that scene elements never enter y in [-3.8, -2.5].
    Provides coordinate helpers and clamping, and can be rendered as a caption banner.
    """
    CEILING_Y = -2.5
    FLOOR_Y = -3.8
    DEFAULT_CAPTION_Y = -3.2

    def __init__(self, text: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if text:
            dock = CaptionDock(initial_text=text)
            self.add(dock)

    @classmethod
    def clamp_above(cls, mobject: Any, margin: float = 0.2) -> Any:
        """Ensure mobject bottom edge stays strictly above the caption ceiling."""
        if hasattr(mobject, "get_bottom") and hasattr(mobject, "shift"):
            bottom_pt = mobject.get_bottom()
            bottom_y = bottom_pt[1] if hasattr(bottom_pt, "__getitem__") else 0.0
            min_allowed = cls.CEILING_Y + margin
            if bottom_y < min_allowed:
                delta = min_allowed - bottom_y
                mobject.shift(UP * delta)
        return mobject


class CaptionDock(VGroup):
    """Safe, persistent caption dock banner positioned at the bottom of the canvas.
    
    Guarantees no caption text ever overflows the screen or card boundaries.
    """

    def __init__(
        self,
        initial_text: str = "",
        width: float = 12.6,
        height: float = 0.95,
        y_pos: float = -3.2,
        corner_radius: float = 0.12,
        fill_color: str = "#0F172A",
        stroke_color: str = "#1E293B",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.dock_width = width
        self.dock_height = height
        self.box = RoundedRectangle(
            corner_radius=corner_radius,
            width=width,
            height=height,
            fill_color=fill_color,
            fill_opacity=0.88,
            stroke_color=stroke_color,
            stroke_width=1.5,
        ).move_to([0, y_pos, 0])
        self.elements = [self.box]

        self.text_mobj = self.create_caption(initial_text) if initial_text else Text("", font_size=12).move_to(self.box.get_center())
        self.elements.append(self.text_mobj)
        self.add(*self.elements)

    def create_caption(self, text: str) -> Any:
        """Create a new formatted Text mobject aligned and scaled to this dock."""
        import textwrap
        chars_per_line = 76 if len(text) > 85 else 92
        wrapped = textwrap.fill(text, width=chars_per_line)
        t = Text(wrapped, font_size=12, color=TEXT_PRIMARY, line_spacing=1.15)
        max_t_w = self.dock_width - 0.6
        max_t_h = self.dock_height - 0.22
        if hasattr(t, "width") and t.width > max_t_w:
            t.scale_to_fit_width(max_t_w)
        if hasattr(t, "height") and t.height > max_t_h:
            t.scale_to_fit_height(max_t_h)
        if hasattr(t, "move_to"):
            t.move_to(self.box.get_center())
        return t


class AnnotatedCard(VGroup):
    """Composite container binding a card background, title, body, and badge.
    
    Guarantees that labels and badges never collide with each other or overflow
    the parent card boundaries.
    """

    def __init__(
        self,
        title: str,
        body: Any = None,
        badge_text: str = "",
        width: float = 5.4,
        height: float = 2.8,
        border_color: str = CYAN_ACCENT,
        card_color: str = SLATE_CARD,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.card_width = width
        self.card_height = height
        self.border_color = border_color
        self.box = RoundedRectangle(
            corner_radius=0.15,
            width=width,
            height=height,
            fill_color=card_color,
            fill_opacity=0.92,
            stroke_color=border_color,
            stroke_width=1.5,
        )
        self.elements = [self.box]

        # Inner header anchor point (near top of the card box)
        header_y = self.box.get_top()[1] - 0.30

        self.title_text = Text(title, font_size=12, weight="BOLD", color=TEXT_PRIMARY)
        if badge_text:
            self.badge = Text(badge_text, font_size=9, weight="BOLD", color=AMBER_SPARK)
            header_row = VGroup(self.title_text, self.badge).arrange(RIGHT, buff=0.25)
            if hasattr(header_row, "width") and header_row.width > width - 0.5:
                header_row.scale_to_fit_width(width - 0.5)
            header_row.move_to([self.box.get_center()[0], header_y, 0])
            self.elements.extend([self.title_text, self.badge])
        else:
            if hasattr(self.title_text, "width") and self.title_text.width > width - 0.5:
                self.title_text.scale_to_fit_width(width - 0.5)
            self.title_text.move_to([self.box.get_center()[0], header_y, 0])
            self.elements.append(self.title_text)

        # Subtle divider below header
        divider_y = header_y - 0.24
        self.divider = Line(
            start=[self.box.get_left()[0] + 0.2, divider_y, 0],
            end=[self.box.get_right()[0] - 0.2, divider_y, 0],
            stroke_color=border_color,
            stroke_width=1.0,
            stroke_opacity=0.4,
        )
        self.elements.append(self.divider)

        # Cavity calculations
        self.divider_y = divider_y
        self.body = None
        self.add(*self.elements)

        if body is not None:
            self.set_body(body)

    def set_body(self, body: Any) -> AnnotatedCard:
        """Position and scale body safely inside the lower card cavity."""
        if self.body is not None and self.body in self.submobjects:
            self.remove(self.body)
        self.body = body

        box_bottom_y = self.box.get_bottom()[1]
        avail_h = max(0.4, (self.divider_y - box_bottom_y) - 0.22)
        avail_w = max(0.4, self.card_width - 0.5)

        if hasattr(self.body, "height") and hasattr(self.body, "scale_to_fit_height"):
            if self.body.height > avail_h:
                self.body.scale_to_fit_height(avail_h)
        if hasattr(self.body, "width") and hasattr(self.body, "scale_to_fit_width"):
            if self.body.width > avail_w:
                self.body.scale_to_fit_width(avail_w)

        cavity_center_y = (self.divider_y + box_bottom_y) / 2.0
        if hasattr(self.body, "move_to"):
            self.body.move_to([self.box.get_center()[0], cavity_center_y, 0])
        self.add(self.body)
        return self



