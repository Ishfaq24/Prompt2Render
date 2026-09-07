"""Tests for k.animate_asset runtime, spatial bounding, and audit integration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render import scenekit as k


def test_scenekit_animate_asset_anchors_and_audit():
    """Verify that k.animate_asset draws cleanly, records overlays, and passes scenekit.audit."""
    fig, ax = k.canvas()
    k.title(ax, "Packet Routing Network")

    # Call k.animate_asset with Lottie packet_stream
    anchors = k.animate_asset(ax, "packet_stream", x=8.0, y=4.5, start_time=1.0, duration=3.0, scale=1.0)
    assert "left" in anchors
    assert "right" in anchors
    assert anchors["center"] == (8.0, 4.5)

    # Check registered overlays on axes
    overlays = getattr(ax, "_p2r_animation_overlays", None)
    assert overlays is not None
    assert len(overlays) == 1
    assert overlays[0]["asset"] == "packet_stream"
    assert overlays[0]["start_time"] == 1.0
    assert overlays[0]["duration"] == 3.0

    problems = k.audit(fig, ax, name="s01")
    fatal = [p for p in problems if p.level == "fail"]
    assert len(fatal) == 0
    k.close(fig)
