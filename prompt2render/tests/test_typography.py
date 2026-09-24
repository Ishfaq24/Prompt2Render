"""Tests for video typography, Manim Text kerning bug mitigation, and CaptionDock."""

import sys
import pytest
from prompt2render import cfg
from prompt2render.assets.mobjects.base import (
    apply_text_patches,
    get_default_font,
    P2RText,
)
from prompt2render.assets.mobjects.stages import CaptionDock


def test_cfg_typography_constants():
    """Verify font and subtitle configuration constants."""
    assert isinstance(cfg.CAPTION_FONT, str)
    assert len(cfg.CAPTION_FONT) > 0
    assert isinstance(cfg.DEFAULT_MANIM_FONT, str)
    assert len(cfg.DEFAULT_MANIM_FONT) > 0
    assert cfg.CAPTION_FONT_SIZE >= 28
    if cfg.IS_WINDOWS:
        assert cfg.CAPTION_FONT in ("Segoe UI", "Arial")
        assert cfg.DEFAULT_MANIM_FONT in ("Segoe UI", "Arial")


def test_default_font_resolution():
    """Verify default font resolution provides modern sans-serif font."""
    font = get_default_font()
    assert isinstance(font, str)
    assert font in ("Segoe UI", "DejaVu Sans", "Arial")


def test_manim_text_patch_applied():
    """Verify that Manim Text is patched with kerning and font defaults."""
    try:
        from manim import Text
    except ImportError:
        pytest.skip("Manim not installed in current environment")

    apply_text_patches()
    assert getattr(Text, "_p2r_patched", False) is True

    # Test small font size instantiation
    t = Text("Contemporary neuroscience has deciphered immense tracts", font_size=16)
    assert t.font in ("Segoe UI", "DejaVu Sans", "Arial", "sans-serif")
    assert round(t.font_size) == 16
    assert t.width > 0
    assert t.height > 0


def test_caption_dock_geometry_and_wrapping():
    """Verify that CaptionDock wraps text cleanly without crashing."""
    try:
        from manim import Text
    except ImportError:
        pytest.skip("Manim not installed in current environment")

    dock = CaptionDock(
        "Weighing roughly three pounds, this biological organ contains eighty-six billion neurons interconnected by over one hundred trillion synaptic junctions."
    )
    assert hasattr(dock, "box")
    assert hasattr(dock, "text_mobj")
    assert dock.dock_width == 12.6
    assert dock.dock_height == 1.0

    # Test updating / creating new caption
    cap = dock.create_caption("A shorter update line.")
    assert cap.width > 0
    assert cap.height > 0
