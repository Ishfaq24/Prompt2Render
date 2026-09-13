"""Algorithm-specific Manim Mobjects for Prompt2Render.

Provides ready-made, animated data structure visualisations so the LLM
doesn't have to construct them from scratch (which produces inconsistent,
often-colliding results).

All Mobjects use the standard Prompt2Render dark theme
(background #0B0F19, accent #00F0FF) and are sized for a 1920x1080
Matplotlib-unit canvas (Manim width ~14.22).
"""
from __future__ import annotations

from typing import Any, Sequence

try:
    from manim import (
        BLUE, DOWN, GRAY, GREEN, LEFT, ORANGE, RED, RIGHT, UP, WHITE, YELLOW,
        AnimationGroup, Arrow, Circle, FadeIn, FadeOut, Flash, Group,
        Indicate, MathTex, Rectangle, RoundedRectangle, Succession,
        SurroundingRectangle, Text, VGroup, VMobject, rate_functions,
    )
    import numpy as np
except ImportError:
    VGroup = object  # type: ignore
    np = None  # type: ignore
    WHITE = "#ffffff"
    GRAY = "#888888"
    BLUE = "#58c4dd"
    GREEN = "#3fb950"
    YELLOW = "#ffff00"
    RED = "#f85149"
    ORANGE = "#d29922"


_BG = "#0B0F19"
_CARD = "#131B2E"
_BORDER = "#1E293B"
_ACCENT = "#00F0FF"
_AMBER = "#FFB703"


class StackMobject(VGroup):
    """Animated stack (LIFO) with push and pop animations.

    Usage::

        stack = StackMobject(initial_values=[1, 2, 3], max_height=5)
        self.add(stack)
        self.play(stack.push(4))
        self.play(stack.pop())
    """

    CELL_WIDTH = 2.2
    CELL_HEIGHT = 0.55

    def __init__(
        self,
        initial_values: Sequence[Any] = (),
        max_height: int = 8,
        *,
        label: str = "Stack",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._values: list[Any] = list(initial_values)[-max_height:]
        self._max = max_height
        self._cells: list[VGroup] = []
        self._label = label
        self._rebuild()

    def _make_cell(self, value: Any) -> VGroup:
        box = RoundedRectangle(
            width=self.CELL_WIDTH, height=self.CELL_HEIGHT,
            corner_radius=0.06,
            fill_color=_CARD, fill_opacity=1.0,
            stroke_color=_ACCENT, stroke_width=2.0,
        )
        txt = Text(str(value), font_size=20, color=WHITE)
        txt.move_to(box.get_center())
        return VGroup(box, txt)

    def _rebuild(self) -> None:
        self.submobjects.clear()
        self._cells = []
        if np is None:
            return
        base_y = 0.0
        for i, val in enumerate(self._values):
            cell = self._make_cell(val)
            cell.move_to(np.array([0.0, base_y + i * (self.CELL_HEIGHT + 0.05), 0.0]))
            self._cells.append(cell)
            self.add(cell)
        lbl = Text(self._label, font_size=16, color=GRAY)
        lbl.next_to(self, DOWN, buff=0.2)
        self.add(lbl)

    def push(self, value: Any, run_time: float = 0.5) -> Any:
        """Return a FadeIn animation for the new top element."""
        self._values.append(value)
        cell = self._make_cell(value)
        if np is not None and self._cells:
            cell.move_to(
                self._cells[-1].get_center() + np.array([0.0, self.CELL_HEIGHT + 0.05, 0.0])
            )
        self._cells.append(cell)
        self.add(cell)
        return FadeIn(cell, shift=UP * 0.3, run_time=run_time)

    def pop(self, run_time: float = 0.5) -> Any:
        """Return a FadeOut animation for the top element."""
        if not self._cells:
            from manim import Wait
            return Wait(0)
        cell = self._cells.pop()
        if self._values:
            self._values.pop()
        return FadeOut(cell, shift=UP * 0.3, run_time=run_time)


class QueueMobject(VGroup):
    """Animated queue (FIFO) with enqueue and dequeue animations.

    Usage::

        q = QueueMobject(initial_values=[10, 20, 30])
        self.add(q)
        self.play(q.enqueue(40))
        self.play(q.dequeue())
    """

    CELL_W = 0.9
    CELL_H = 0.9
    GAP = 0.08

    def __init__(
        self,
        initial_values: Sequence[Any] = (),
        max_len: int = 8,
        *,
        label: str = "Queue",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._values: list[Any] = list(initial_values)[-max_len:]
        self._max = max_len
        self._cells: list[VGroup] = []
        self._label = label
        self._rebuild()

    def _make_cell(self, value: Any) -> VGroup:
        box = RoundedRectangle(
            width=self.CELL_W, height=self.CELL_H,
            corner_radius=0.08,
            fill_color=_CARD, fill_opacity=1.0,
            stroke_color=_AMBER, stroke_width=2.0,
        )
        txt = Text(str(value), font_size=20, color=WHITE)
        txt.move_to(box.get_center())
        return VGroup(box, txt)

    def _rebuild(self) -> None:
        self.submobjects.clear()
        self._cells = []
        if np is None:
            return
        for i, val in enumerate(self._values):
            cell = self._make_cell(val)
            cell.move_to(np.array([i * (self.CELL_W + self.GAP), 0.0, 0.0]))
            self._cells.append(cell)
            self.add(cell)
        lbl = Text(self._label, font_size=16, color=GRAY)
        lbl.next_to(self, DOWN, buff=0.2)
        self.add(lbl)

    def enqueue(self, value: Any, run_time: float = 0.4) -> Any:
        """Return a FadeIn animation for the new rear element."""
        self._values.append(value)
        cell = self._make_cell(value)
        if np is not None and self._cells:
            cell.move_to(
                self._cells[-1].get_center() + np.array([self.CELL_W + self.GAP, 0.0, 0.0])
            )
        self._cells.append(cell)
        self.add(cell)
        return FadeIn(cell, shift=RIGHT * 0.3, run_time=run_time)

    def dequeue(self, run_time: float = 0.4) -> Any:
        """Return a FadeOut animation for the front element."""
        if not self._cells:
            from manim import Wait
            return Wait(0)
        cell = self._cells.pop(0)
        if self._values:
            self._values.pop(0)
        return FadeOut(cell, shift=LEFT * 0.3, run_time=run_time)
