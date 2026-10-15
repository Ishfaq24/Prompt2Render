"""Cross-domain algorithm, math, security, and networking visual widgets."""

from __future__ import annotations

from typing import Any

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
        Arrow,
        Dot,
        MathTex,
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

        def scale_to_fit_width(self, width: float) -> Any:
            return self

    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self.submobjects = list(args)

        def add(self, *items: Any) -> Any:
            self.submobjects.extend(items)
            return self

        def arrange(self, direction: Any = RIGHT, buff: float = 0.2) -> Any:
            return self

    class RoundedRectangle(VMobject):  # type: ignore
        pass

    class Rectangle(VMobject):  # type: ignore
        pass

    class Text(VMobject):  # type: ignore
        pass

    class MathTex(VMobject):  # type: ignore
        pass

    class Arrow(VMobject):  # type: ignore
        pass


class ArrayGrid(VGroup):
    """An interactive array of boxed values with pointers (e.g. for search, sort, DP)."""

    def __init__(
        self,
        values: list[Any],
        cell_size: float = 0.8,
        active_index: int | None = None,
        highlight_color: str = CYAN,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.values = list(values)
        self.cells: list[Any] = []
        self.labels: list[Any] = []

        for i, val in enumerate(self.values):
            is_active = (active_index == i)
            border_c = highlight_color if is_active else SLATE_BORDER
            fill_op = 0.9 if is_active else 0.7

            box = RoundedRectangle(
                width=cell_size,
                height=cell_size,
                corner_radius=0.1,
                stroke_color=border_c,
                stroke_width=2.0 if is_active else 1.5,
                fill_color=SLATE_BG,
                fill_opacity=fill_op,
            )
            txt = Text(str(val), font_size=18, weight="BOLD", color=highlight_color if is_active else TEXT_PRIMARY)
            cell = VGroup(box, txt)
            self.cells.append(cell)

        self.array_group = VGroup(*self.cells).arrange(RIGHT, buff=0.1)
        self.add(self.array_group)

    def get_cell(self, index: int) -> Any:
        if 0 <= index < len(self.cells):
            return self.cells[index]
        raise IndexError(f"Array index {index} out of range (0..{len(self.cells)-1})")


class FormulaCard(VGroup):
    """Glassmorphic card for step-by-step mathematical calculations (e.g. GCD / Modulo)."""

    def __init__(
        self,
        steps: list[str],
        title: str = "Mathematical Step",
        width: float = 5.2,
        highlight_step: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        num_steps = max(1, len(steps))
        step_height = 0.45
        height = max(1.5, num_steps * step_height + 0.8)

        self.card = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.15,
            stroke_color=PURPLE,
            stroke_width=2.0,
            fill_color=SLATE_BG,
            fill_opacity=0.9,
        )

        header = Text(title, font_size=14, weight="BOLD", color=PURPLE).move_to(
            (0, height / 2.0 - 0.25, 0)
        )

        rendered_steps = []
        for i, step_str in enumerate(steps):
            is_hl = (highlight_step == i)
            color = AMBER if is_hl else TEXT_PRIMARY
            has_latex = any(c in step_str for c in (r"\\", r"^", r"_", r"{", r"}", r"=", r"+", r"-", r"\cdot", r"\sum", r"\nabla", r"\sigma", r"\delta"))
            if has_latex:
                try:
                    c_text = MathTex(step_str, font_size=18, color=color)
                except Exception:
                    c_text = Text(step_str, font_size=14, weight="BOLD" if is_hl else "NORMAL", color=color)
            else:
                c_text = Text(
                    step_str,
                    font_size=14,
                    weight="BOLD" if is_hl else "NORMAL",
                    color=color,
                )
            if c_text.width > width - 0.5:
                c_text.scale_to_fit_width(width - 0.5)
            c_text.move_to((0, height / 2.0 - 0.65 - i * step_height, 0))
            rendered_steps.append(c_text)

        self.step_group = VGroup(*rendered_steps)
        self.add(self.card, header, self.step_group)

    def set_highlight(self, index: int) -> None:
        """Highlight a specific step index in AMBER and unhighlight others."""
        for i, elem in enumerate(self.step_group):
            if i == index:
                elem.set_color(AMBER)
            else:
                elem.set_color(TEXT_PRIMARY)


class KeyBadge(VGroup):
    """Cryptographic public/private key badge for SSH / SSL explainers."""

    def __init__(
        self,
        key_type: str = "PUBLIC KEY",
        name: str = "id_ed25519.pub",
        is_private: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        border_color = ROSE if is_private else EMERALD

        self.pill = RoundedRectangle(
            width=3.2,
            height=0.9,
            corner_radius=0.2,
            stroke_color=border_color,
            stroke_width=2.0,
            fill_color=SLATE_BG,
            fill_opacity=0.92,
        )
        tag = Text(key_type.upper(), font_size=11, weight="BOLD", color=border_color).move_to(
            (0, 0.22, 0)
        )
        val = Text(name, font_size=14, color=TEXT_PRIMARY).move_to((0, -0.15, 0))
        self.add(self.pill, tag, val)
