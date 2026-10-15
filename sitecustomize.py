"""Prompt2Render Python startup hooks.

Automatically initializes typography enhancements and patches Manim Text kerning
when running any Python command or Manim rendering subprocess within Prompt2Render.
"""

from __future__ import annotations
import sys

try:
    from prompt2render.assets.mobjects.base import apply_text_patches
    apply_text_patches()
except Exception:
    # Graceful degradation if prompt2render is not yet on path or manim not installed
    pass
