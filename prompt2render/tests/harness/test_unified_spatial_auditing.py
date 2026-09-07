"""Tests for unified spatial auditing and bounding-box collision detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render.harness.spatial_units import BoundingBox, check_layout_collisions
from prompt2render import scenekit as k


def test_bounding_box_geometry():
    """Verify BoundingBox coordinate calculation and intersection."""
    box_a = BoundingBox(x=5.0, y=5.0, w=2.0, h=2.0, label="CPU")
    assert box_a.x0 == 4.0
    assert box_a.x1 == 6.0
    assert box_a.y0 == 4.0
    assert box_a.y1 == 6.0
    assert box_a.area == 4.0

    # Non-overlapping box
    box_b = BoundingBox(x=10.0, y=5.0, w=2.0, h=2.0, label="RAM")
    assert box_a.intersection(box_b) == 0.0
    assert box_a.overlap_ratio(box_b) == 0.0

    # Overlapping box
    box_c = BoundingBox(x=5.5, y=5.0, w=2.0, h=2.0, label="Overlapping_ALU")
    assert box_a.intersection(box_c) > 0.0
    assert box_a.overlap_ratio(box_c) > 0.5


def test_check_layout_collisions():
    """Ensure check_layout_collisions flags overlapping components."""
    box_a = BoundingBox(x=4.0, y=4.0, w=3.0, h=2.0, label="BoxA")
    box_b = BoundingBox(x=5.0, y=4.0, w=3.0, h=2.0, label="BoxB")  # Overlaps BoxA
    box_c = BoundingBox(x=12.0, y=8.0, w=2.0, h=1.0, label="BoxC") # Far away

    collisions = check_layout_collisions([box_a, box_b, box_c], overlap_threshold=0.10)
    assert len(collisions) == 1
    assert collisions[0][0].label == "BoxA"
    assert collisions[0][1].label == "BoxB"


def test_scenekit_draw_asset_renders_and_audits():
    """Verify that k.draw_asset draws cleanly on canvas and passes scenekit.audit."""
    fig, ax = k.canvas()
    k.title(ax, "Hardware Datapath")
    anchors = k.draw_asset(ax, "cpu_core", x=4.0, y=4.5, width=3.0)
    assert "left" in anchors
    assert "right" in anchors
    assert anchors["center"] == (4.0, 4.5)

    problems = k.audit(fig, ax, name="s01")
    for p in problems:
        print(f"PROBLEM: {p}")
    fatal = [p for p in problems if p.level == "fail"]
    assert len(fatal) == 0
    k.close(fig)
