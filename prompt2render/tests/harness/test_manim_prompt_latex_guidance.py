"""Both Manim code-generation prompts must teach the model the correct
LaTeX escaping convention for raw-string MathTex/Tex arguments, with a
visibly different one-backslash "correct" example vs. two-backslash "wrong"
examples.

Regression: a first attempt at adding this guidance embedded it inside a
non-raw f-string without doubling every backslash for the "two backslashes
is wrong" examples, so both the correct and incorrect examples collapsed to
the same single backslash in the actual rendered prompt text -- useless (or
actively confusing) guidance for the model, though not something a syntax
check alone would catch.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin


def _assert_has_correct_and_wrong_examples(text: str) -> None:
    assert "MathTex/Tex LaTeX escaping" in text

    # The correct example: single backslash before each LaTeX special char.
    assert r'MathTex(r"\mathbb{Z}_{23} = \{0, 1, \dots, 22\}")' in text

    # The "never do this" examples: exactly two backslashes, visibly
    # different from the correct one-backslash form above.
    for bad in (r"\\{", r"\\}", r"\\_", r"\\%", r"\\$", r"\\#", r"\\&", r"\\~", r"\\^"):
        assert bad in text, f"missing wrong-example {bad!r}"

    # And the wrong examples must not be mistaken for the right one: no
    # THREE-backslash artifact from a bad escape count either.
    assert r"\\\\" not in text


def test_build_prompt_has_correct_latex_escaping_guidance():
    section = SimpleNamespace(title="T", anim="A", stem="01")
    plugin = GeneratorManimPlugin({})
    text = plugin._build_prompt(section, "timing", 10.0, "")
    _assert_has_correct_and_wrong_examples(text)


def test_build_setup_prompt_has_correct_latex_escaping_guidance():
    section = SimpleNamespace(title="T", anim="A", stem="01")
    plugin = GeneratorManimPlugin({})
    text = plugin._build_setup_prompt(section, [], 10.0, "")
    _assert_has_correct_and_wrong_examples(text)
