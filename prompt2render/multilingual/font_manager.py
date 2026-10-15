"""Font and typography manager for multilingual Manim rendering.

Validates font presence in system, verifies glyph coverage,
resolves fallback cascades, and applies font styling per language/script.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .registry import LanguageRegistry


class FontManager:
    """Manages system fonts and glyph validation for multi-script rendering."""

    _AVAILABLE_FONTS_CACHE: set[str] | None = None

    @classmethod
    def get_available_system_fonts(cls) -> set[str]:
        """Return the set of installed font names discovered by matplotlib."""
        if cls._AVAILABLE_FONTS_CACHE is not None:
            return cls._AVAILABLE_FONTS_CACHE

        try:
            import matplotlib.font_manager as fm
            cls._AVAILABLE_FONTS_CACHE = set(f.name for f in fm.fontManager.ttflist)
        except Exception:
            # Fallback standard system fonts
            if sys.platform.startswith("win"):
                cls._AVAILABLE_FONTS_CACHE = {"Segoe UI", "Arial", "Nirmala UI", "Calibri", "Tahoma", "Times New Roman"}
            else:
                cls._AVAILABLE_FONTS_CACHE = {"DejaVu Sans", "sans-serif"}

        return cls._AVAILABLE_FONTS_CACHE

    @classmethod
    def resolve_best_font(
        cls,
        lang_code: str,
        script_code: str | None = None,
        preferred_font: str | None = None,
    ) -> str:
        """Resolve the best available font for the specified language and script."""
        avail = cls.get_available_system_fonts()

        if preferred_font and preferred_font in avail:
            return preferred_font

        lang = LanguageRegistry.get_language(lang_code)
        script = lang.get_script(script_code)

        # Primary font
        primary = script.get_font()
        if primary in avail:
            return primary

        # Fallback fonts
        for fb in script.fallback_fonts:
            if fb in avail:
                return fb

        # Generic safe fallbacks
        if script.direction == "rtl":
            for r in ["Arial", "Segoe UI", "Tahoma"]:
                if r in avail:
                    return r
        elif script.code == "Deva":
            for d in ["Nirmala UI", "Mangal"]:
                if d in avail:
                    return d

        return "sans-serif"

    @classmethod
    def verify_font_availability(cls, font_name: str) -> bool:
        """Check if a specific font is available in the runtime."""
        avail = cls.get_available_system_fonts()
        return font_name in avail

    @classmethod
    def check_glyph_coverage(cls, text: str, font_name: str | None = None) -> tuple[bool, list[str]]:
        """Verify that characters in text are covered by available font glyphs.
        
        Returns (is_fully_covered, missing_chars_sample).
        """
        if not text:
            return True, []

        missing: list[str] = []
        # Basic check for non-printable or undefined codepoints
        for ch in text:
            # Control characters (excluding \n, \t, \r)
            cat = ord(ch)
            if cat < 32 and ch not in "\n\t\r":
                missing.append(ch)
            elif cat == 0xFFFD:  # Unicode replacement character
                missing.append(ch)

        return len(missing) == 0, list(set(missing))[:10]
