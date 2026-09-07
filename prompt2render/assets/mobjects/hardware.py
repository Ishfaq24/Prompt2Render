"""Hardware Mobjects for computer architecture visual explainers."""

from __future__ import annotations

from typing import Any

try:
    from manim import (
        DOWN,
        LEFT,
        ORIGIN,
        RIGHT,
        UP,
        Rectangle,
        Text,
        VGroup,
        VMobject,
        Write,
    )
except ImportError:
    DOWN = (0, -1, 0)
    LEFT = (-1, 0, 0)
    RIGHT = (1, 0, 0)
    UP = (0, 1, 0)
    ORIGIN = (0, 0, 0)
    class VMobject:  # type: ignore
        pass
    class VGroup(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            self.submobjects = list(args)
        def add(self, *items: Any) -> Any:
            self.submobjects.extend(items)
            return self
    class Rectangle(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class Text(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass


class MemoryBankMobject(VGroup):
    """Addressable memory bank with parametric cell count and highlight animations."""

    def __init__(
        self,
        num_cells: int = 8,
        cell_width: float = 2.0,
        cell_height: float = 0.5,
        highlight_color: str = "#1f6feb",
        border_color: str = "#58a6ff",
        bg_color: str = "#161b22",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.num_cells = num_cells
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.highlight_color = highlight_color
        self.cells: list[Any] = []
        self.labels: list[Any] = []

        total_height = num_cells * cell_height
        start_y = total_height / 2.0 - cell_height / 2.0

        for i in range(num_cells):
            cell = Rectangle(
                width=cell_width,
                height=cell_height,
                color=border_color,
                fill_color=bg_color,
                fill_opacity=0.8,
            )
            # Position cell vertically
            if hasattr(cell, "move_to"):
                cell.move_to((0, start_y - i * cell_height, 0))
            
            addr_text = f"0x{i:02X}"
            label = Text(addr_text, font_size=16, color="#8b949e")
            if hasattr(label, "next_to"):
                label.next_to(cell, LEFT, buff=0.2)

            self.cells.append(cell)
            self.labels.append(label)
            self.add(cell, label)

    def get_cell(self, address: int) -> Any:
        """Retrieve cell rectangle by memory address index."""
        if 0 <= address < len(self.cells):
            return self.cells[address]
        raise IndexError(f"Address {address} out of range (0..{len(self.cells)-1})")
