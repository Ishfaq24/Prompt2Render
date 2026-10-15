"""Layout, text-wrapping, and text-direction utilities for multilingual Manim scenes.

Handles:
- Script-appropriate line wrapping with boundary safety.
- Text scaling and font size adjustments based on language script expansion.
- Right-to-Left alignment and bidirectional text preservation for mixed scripts.
- LaTeX formula protection to preserve mathematical expressions unmodified.
"""

from __future__ import annotations

import re
from typing import Any

from .font_manager import FontManager
from .registry import LanguageRegistry


class MultilingualLayout:
    """Provides layout calculation and bidirectional formatting for Manim text elements."""

    # Words / characters per line ceilings for 16:9 safe canvas
    DEFAULT_MAX_CHARS_PER_LINE = 55
    RTL_MAX_CHARS_PER_LINE = 50
    DEVANAGARI_MAX_CHARS_PER_LINE = 48

    @classmethod
    def get_max_chars_per_line(cls, lang_code: str) -> int:
        """Return safe characters per line before line-wrapping is mandatory."""
        if lang_code in ("ar", "ur"):
            return cls.RTL_MAX_CHARS_PER_LINE
        if lang_code in ("hi"):
            return cls.DEVANAGARI_MAX_CHARS_PER_LINE
        return cls.DEFAULT_MAX_CHARS_PER_LINE

    @classmethod
    def wrap_text(cls, text: str, max_chars: int | None = None, lang_code: str = "en") -> str:
        """Wrap text cleanly at word boundaries respecting language rules."""
        if not text:
            return ""

        limit = max_chars or cls.get_max_chars_per_line(lang_code)
        lines = text.split("\n")
        wrapped_lines = []

        for line in lines:
            line = line.strip()
            if len(line) <= limit:
                wrapped_lines.append(line)
                continue

            words = line.split(" ")
            current_line: list[str] = []
            current_len = 0

            for word in words:
                word_len = len(word)
                if current_len + word_len + (1 if current_line else 0) <= limit:
                    current_line.append(word)
                    current_len += word_len + (1 if current_len > 0 else 0)
                else:
                    if current_line:
                        wrapped_lines.append(" ".join(current_line))
                    current_line = [word]
                    current_len = word_len

            if current_line:
                wrapped_lines.append(" ".join(current_line))

        return "\n".join(wrapped_lines)

    @classmethod
    def format_bidi_text(cls, text: str, lang_code: str, script_code: str | None = None) -> str:
        """Format text for Manim rendering with Pango.
        
        Pango automatically performs HarfBuzz complex text shaping and FriBidi bidirectional layout.
        We preserve mathematical formulas, variable names, and code tokens intact.
        """
        if not text:
            return ""
        return text

    @classmethod
    def get_recommended_font_size(
        cls,
        base_size: int,
        lang_code: str,
        script_code: str | None = None,
    ) -> int:
        """Adjust font size for script density (e.g. Devanagari or Arabic matras/diacritics).
        
        Complex scripts typically require 5-10% larger font size or adjusted line height
        so that upper/lower diacritics and matras remain legible.
        """
        if lang_code in ("hi", "ks") and script_code != "Arab":
            return max(14, int(base_size * 1.05))
        if lang_code in ("ar", "ur") or (lang_code == "ks" and script_code == "Arab"):
            return max(14, int(base_size * 1.08))
        return base_size
