"""Tests for external asset and pattern prompt injection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render.harness.context import SceneContext
from prompt2render.harness.plugins.renderer_manim import _pattern_hints
from prompt2render.scenes import API_DOC


def test_manim_prompt_hints_injection():
    """Verify that _pattern_hints injects external asset hints."""
    ctx = SceneContext()
    ctx.retrieval_context = {
        "01": [
            {
                "id": "cpu_core",
                "hint": "Asset 'cpu_core': vector icon available at 'assets/hardware_cpu.svg' for SVGMobject.",
            },
            {
                "id": "memory_bank",
                "hint": "Mobject 'MemoryBankMobject': from prompt2render.assets.mobjects.hardware import MemoryBankMobject",
            },
        ]
    }

    hints = _pattern_hints(ctx, "01")
    assert "AVAILABLE EXTERNAL ANIMATION OBJECTS & ASSETS:" in hints
    assert "cpu_core" in hints
    assert "MemoryBankMobject" in hints


def test_scenekit_api_doc_contains_draw_asset():
    """Ensure SceneKit API_DOC documents k.draw_asset for the LLM."""
    assert "k.draw_asset" in API_DOC
    assert "cpu_core" in API_DOC
