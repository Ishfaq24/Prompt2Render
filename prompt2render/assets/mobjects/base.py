"""Base classes and utilities for reusable Manim Mobjects."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    from manim import SVGMobject, VMobject, VGroup, Rectangle, Text, config
except ImportError:
    # Graceful stub when running in an environment without Manim installed
    class VMobject:  # type: ignore
        pass
    class VGroup(VMobject):  # type: ignore
        pass
    class SVGMobject(VMobject):  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass
    class Rectangle(VMobject):  # type: ignore
        pass
    class Text(VMobject):  # type: ignore
        pass
    config = {}  # type: ignore


def get_default_font(text: str | None = None) -> str:
    """Return the cleanest available modern font for the OS and script."""
    if text:
        # Check script of text
        for ch in text:
            code = ord(ch)
            if 0x0900 <= code <= 0x097F or 0x1CD0 <= code <= 0x1CFF:
                # Devanagari script (Hindi / Kashmiri Devanagari)
                if sys.platform.startswith("win"):
                    return "Nirmala UI"
                return "Lohit Devanagari"
            elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0x08A0 <= code <= 0x08FF:
                # Arabic / Urdu / Kashmiri Perso-Arabic script
                if sys.platform.startswith("win"):
                    return "Arial"
                return "DejaVu Sans"

    is_windows = sys.platform.startswith("win")
    if is_windows:
        return "Segoe UI"
    return "DejaVu Sans"


def apply_text_patches() -> None:
    """Patch Manim Text to fix Pango small-font kerning bugs and default font."""
    try:
        import manim
        target_cls = getattr(manim, "Text", None)
        if target_cls is None or getattr(target_cls, "_p2r_patched", False):
            return

        orig_init = target_cls.__init__

        def _patched_init(self: Any, text: str, *args: Any, **kwargs: Any) -> None:
            # 1. Default font to script-appropriate modern font if unspecified or empty
            if "font" not in kwargs or not kwargs["font"]:
                kwargs["font"] = get_default_font(text)

            # 2. Fix Pango FreeType small-font kerning rounding errors
            # When font_size < 36, Pango renders at fractional pt sizes (font_size / 4.8)
            # which causes autohinting to insert spaces inside words (e.g. "inte rconnected").
            # Rendering at base resolution 48 and scaling down completely eliminates the bug.
            font_size = kwargs.pop("font_size", 48)
            if font_size < 36:
                orig_init(self, text, *args, font_size=48, **kwargs)
                self.scale(font_size / 48)
            else:
                orig_init(self, text, *args, font_size=font_size, **kwargs)

        target_cls.__init__ = _patched_init
        target_cls._p2r_patched = True

        # Also patch module-level Text in this module
        global Text
        Text = target_cls
    except Exception:
        pass


# Apply patch automatically when module is loaded
apply_text_patches()


class P2RSVGMobject(SVGMobject):
    """SVGMobject with automatic aspect-ratio normalization and palette tinting."""

    def __init__(
        self,
        file_path: str | Path,
        target_width: float = 2.0,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        path_str = str(file_path)
        super().__init__(path_str, **kwargs)
        if hasattr(self, "set_width"):
            self.set_width(target_width)
        if color and hasattr(self, "set_color"):
            self.set_color(color)


class P2RText(Text):
    """Production-grade Text mobject guaranteed to have clean sans-serif typography."""
    pass
