"""Unified spatial representation and collision auditing across backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BoundingBox:
    """Canonical 16:9 normalized bounding box in [0..16] x [0..9] canvas space."""

    x: float
    y: float
    w: float
    h: float
    label: str = ""
    backend: str = "generic"

    @property
    def x0(self) -> float:
        return self.x - self.w / 2.0

    @property
    def x1(self) -> float:
        return self.x + self.w / 2.0

    @property
    def y0(self) -> float:
        return self.y - self.h / 2.0

    @property
    def y1(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def intersection(self, other: BoundingBox) -> float:
        """Compute intersection area between two boxes."""
        inter_x = max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))
        inter_y = max(0.0, min(self.y1, other.y1) - max(self.y0, other.y0))
        return inter_x * inter_y

    def overlap_ratio(self, other: BoundingBox) -> float:
        """Return overlap fraction relative to smaller box area."""
        inter = self.intersection(other)
        if inter <= 0:
            return 0.0
        smaller = min(self.area, other.area)
        if smaller <= 0:
            return 0.0
        return inter / smaller


def check_layout_collisions(
    boxes: Sequence[BoundingBox],
    overlap_threshold: float = 0.15,
) -> list[tuple[BoundingBox, BoundingBox, float]]:
    """Detect colliding pairs of bounding boxes above overlap threshold.

    Returns list of (box_a, box_b, overlap_fraction).
    """
    collisions = []
    n = len(boxes)
    for i in range(n):
        for j in range(i + 1, n):
            ratio = boxes[i].overlap_ratio(boxes[j])
            if ratio > overlap_threshold:
                collisions.append((boxes[i], boxes[j], ratio))
    return collisions
