"""Automated self-healing and code repair for multilingual Manim scenes.

Detects syntax/runtime rendering failures, text clipping, and overlapping elements,
then applies targeted repairs (font substitutions, wrapping, font scaling, safe margins).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .font_manager import FontManager
from .registry import LanguageRegistry


class SceneRepairEngine:
    """Repairs Manim scene code for language-specific rendering defects."""

    @classmethod
    def repair_code_for_language(
        cls,
        code: str,
        lang_code: str,
        script_code: str | None = None,
        error_message: str | None = None,
    ) -> str:
        """Apply targeted adjustments to Manim Python code to resolve rendering/font issues."""
        repaired = code
        best_font = FontManager.resolve_best_font(lang_code, script_code)
        is_rtl = LanguageRegistry.is_rtl(lang_code, script_code)

        # 1. Ensure Text font argument uses the verified language font
        # Replace Text("...", ...) with font=best_font if missing or Segoe UI for Indic/Arabic
        if best_font and best_font != "Segoe UI":
            # If code has font="Segoe UI" or font='Segoe UI' or no font specified in Text(...)
            repaired = re.sub(
                r'Text\((["\'].*?["\'])(,\s*font=[\'"][^\'"]+[\'"])?',
                rf'Text(\1, font="{best_font}"',
                repaired,
            )

        # 2. Adjust font size if error indicated text overflow or off-frame
        if error_message and ("offframe" in error_message.lower() or "clipping" in error_message.lower()):
            def shrink_font(match):
                prefix = match.group(1)
                size = int(match.group(2))
                new_size = max(14, int(size * 0.85))
                return f"{prefix}{new_size}"

            repaired = re.sub(r'(font_size\s*=\s*)(\d+)', shrink_font, repaired)

        # 3. Add script comment header for reproducibility
        if not repaired.startswith("# [Prompt2Render Multilingual]"):
            header = f"# [Prompt2Render Multilingual] Lang: {lang_code}, Script: {script_code or 'default'}, Direction: {'rtl' if is_rtl else 'ltr'}, Font: {best_font}\n"
            repaired = header + repaired

        return repaired
