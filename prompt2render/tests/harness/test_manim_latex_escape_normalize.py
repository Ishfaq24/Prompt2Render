"""_normalize_manim19's LaTeX-escape fixup must never touch raw strings, and
must be idempotent on the non-raw strings it does touch.

Regression, traced from a real crash: a generated scene had
``MathTex(r"\\mathbb{Z}_{23} = \\{0, 1, 2, \\dots, 22\\}")`` -- a RAW string,
where a single backslash before ``{``/``}`` is already the correct LaTeX
escape for a literal brace. The old normalizer matched ``\\{``/``\\}``
anywhere in the file text (raw or not) and doubled the backslash, so LaTeX
saw ``\\`` (its own line-break command) followed by a bare brace instead of
an escaped one, breaking the ``align*`` environment and crashing the render
with "latex error converting to dvi". The same unconditional regex was also
not idempotent even for the non-raw strings it was meant for: reapplying it
to its own prior output (e.g. every time a cached scene gets re-normalized
across harness runs) kept adding one more backslash each time.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.plugins.renderer_manim import _normalize_manim19


def test_raw_string_latex_brace_escape_is_untouched():
    code = (
        'bounds_text = MathTex(r"\\mathbb{Z}_{23} = \\{0, 1, 2, \\dots, 22\\}")'
    )
    assert _normalize_manim19(code) == code


def test_raw_string_with_already_correct_escapes_stays_correct():
    # The exact real-world crash case, with the correct (single-backslash)
    # escaping a human or a good generation would produce.
    good = r'MathTex(r"\mathbb{Z}_{23} = \{0, 1, 2, 3, \dots, 22\}")'
    assert _normalize_manim19(good) == good


def test_non_raw_string_escape_still_gets_doubled():
    code = r'Text("Apples \& Oranges")'
    assert _normalize_manim19(code) == r'Text("Apples \\& Oranges")'


def test_non_raw_string_normalize_is_idempotent():
    code = r'Text("Apples \& Oranges")'
    once = _normalize_manim19(code)
    twice = _normalize_manim19(once)
    assert twice == once


def test_mixed_raw_and_non_raw_strings_in_same_file():
    code = (
        'a = MathTex(r"\\{1, 2\\}")\n'
        'b = Text("cost \\% off")\n'
    )
    fixed = _normalize_manim19(code)
    # Raw string: untouched.
    assert 'MathTex(r"\\{1, 2\\}")' in fixed
    # Non-raw string: backslash doubled, as before.
    assert 'Text("cost \\\\% off")' in fixed
