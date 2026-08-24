"""Convert display mathematics into text suitable for speech synthesis.

This module deliberately does not replace the source text used for captions or
alignment metadata. It creates a spoken rendering only, so `$...$` delimiters
never become the word "dollar" while the original equation remains available
for the script and captions.
"""
from __future__ import annotations

import re


# Delimiters are handled before general punctuation. Currency such as "$5" is
# not matched and therefore remains available to the ordinary text normalizer.
_DISPLAY_DOLLAR = re.compile(
    r"\$\$(.+?)(?<!\\)\$\$",
    re.S,
)

_INLINE_DOLLAR = re.compile(
    r"\$(?!\s*\d)(.+?)(?<!\\)\$",
    re.S,
)

_PAREN_MATH = re.compile(
    r"\\\((.+?)(?<!\\)\\\)",
    re.S,
)

_BRACKET_MATH = re.compile(
    r"\\\[(.+?)(?<!\\)\\\]",
    re.S,
)


_COMMANDS = {
    r"\mathcal": " order ",
    r"\mathrm": " ",
    r"\mathbf": " ",
    r"\text": " ",
    r"\operatorname": " ",
    r"\cdot": " times ",
    r"\times": " times ",
    r"\div": " divided by ",
    r"\pm": " plus or minus ",
    r"\leq": " less than or equal to ",
    r"\le": " less than or equal to ",
    r"\geq": " greater than or equal to ",
    r"\ge": " greater than or equal to ",
    r"\neq": " not equal to ",
    r"\ne": " not equal to ",
    r"\to": " to ",
    r"\rightarrow": " to ",
    r"\left": " ",
    r"\right": " ",
    r"\infty": " infinity ",
    r"\sum": " sum ",
    r"\prod": " product ",
    r"\log": " log ",
    r"\ln": " natural log ",
    r"\sin": " sine ",
    r"\cos": " cosine ",
    r"\tan": " tangent ",
    r"\alpha": " alpha ",
    r"\beta": " beta ",
    r"\gamma": " gamma ",
    r"\delta": " delta ",
    r"\Delta": " delta ",
    r"\pi": " pi ",
}


_BRACED = re.compile(
    r"\\(frac|dfrac|tfrac|sqrt|text|mathrm|mathbf|mathcal)"
    r"\s*\{([^{}]*)\}"
)

_SUP = re.compile(
    r"\^\s*\{([^{}]*)\}"
    r"|\^\s*([A-Za-z0-9]+)"
)

_SUB = re.compile(
    r"_\s*\{([^{}]*)\}"
    r"|_\s*([A-Za-z0-9]+)"
)


def _braced(match: re.Match[str]) -> str:
    command = match.group(1)
    value = match.group(2).strip()

    if command in {"frac", "dfrac", "tfrac"}:
        return f" {value} "

    if command == "sqrt":
        return f" square root of {value} "

    return f" {value} "


def _fractions(text: str) -> str:
    """Convert common \\frac{numerator}{denominator} expressions."""
    pattern = re.compile(
        r"\\(?:frac|dfrac|tfrac)"
        r"\s*\{([^{}]*)\}"
        r"\s*\{([^{}]*)\}"
    )

    while True:
        new = pattern.sub(
            lambda m: f" {m.group(1)} over {m.group(2)} ",
            text,
        )

        if new == text:
            return new

        text = new


def _power(match: re.Match[str]) -> str:
    value = (
        match.group(1)
        or match.group(2)
        or ""
    ).strip()

    if value == "2":
        return " squared "

    if value == "3":
        return " cubed "

    return f" to the power {value} "


def _subscript(match: re.Match[str]) -> str:
    value = (
        match.group(1)
        or match.group(2)
        or ""
    ).strip()

    return f" sub {value} "


def equation_to_speech(equation: str) -> str:
    """Return a conservative spoken form of a LaTeX-like equation."""
    text = equation.strip()

    # Handle common fractions before commands are expanded.
    text = _fractions(text)

    # Big-O notation.
    text = re.sub(
        r"\bO\s*\(\s*log\s*n\s*\)",
        " oh log n ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\bO\s*\(\s*n\s*\)",
        " oh n ",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\bO\s*\(\s*1\s*\)",
        " oh one ",
        text,
        flags=re.I,
    )

    # Convert commands with braced arguments.
    text = _BRACED.sub(_braced, text)

    # Convert known mathematical commands.
    for command, replacement in _COMMANDS.items():
        text = text.replace(command, replacement)

    # Exponents and subscripts.
    text = _SUP.sub(_power, text)
    text = _SUB.sub(_subscript, text)

    # Math punctuation is verbalized explicitly.
    replacements = {
        "=": " equals ",
        "+": " plus ",
        "-": " minus ",
        "<": " less than ",
        ">": " greater than ",
        "/": " over ",
        "*": " times ",
        "(": " open parenthesis ",
        ")": " close parenthesis ",
        "[": " open bracket ",
        "]": " close bracket ",
        ",": " ",
        ":": " ",
        ";": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Remove remaining LaTeX punctuation/backslash syntax.
    text = re.sub(
        r"\\[,;!: ]",
        " ",
        text,
    )

    # Remaining escaped symbols.
    text = re.sub(
        r"\\+",
        " plus ",
        text,
    )

    # Remove backslash from unknown commands while preserving the name.
    text = re.sub(
        r"\\([A-Za-z]+)",
        r" \1 ",
        text,
    )

    # Remaining braces.
    text = re.sub(
        r"[{}]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def speech_text(text: str) -> str:
    """Convert recognized math spans and common abbreviations for TTS."""

    def replace(match: re.Match[str]) -> str:
        return " " + equation_to_speech(match.group(1)) + " "

    # Convert explicit mathematical delimiters first.
    out = _DISPLAY_DOLLAR.sub(
        replace,
        text,
    )

    out = _INLINE_DOLLAR.sub(
        replace,
        out,
    )

    out = _PAREN_MATH.sub(
        replace,
        out,
    )

    out = _BRACKET_MATH.sub(
        replace,
        out,
    )

    # A bare LaTeX command outside delimiters is still safer spoken as its
    # mathematical name than as a backslash token.
    if "\\" in out:
        out = equation_to_speech(out)

    # Expand common abbreviations so TTS speaks them naturally.
    # Note: the keys are regex patterns.
    abbreviations = {
        r"\bi\.e\.": "that is",
        r"\be\.g\.": "for example",
        r"\betc\.": "etcetera",
        r"\bvs\.": "versus",
        r"\bDr\.": "Doctor",
        r"\bMr\.": "Mister",
        r"\bMrs\.": "Missus",
        r"\bProf\.": "Professor",

        # Technical abbreviations.
        r"\bAPI\b": "A P I",
        r"\bCPU\b": "C P U",
        r"\bGPU\b": "G P U",
        r"\bRAM\b": "ram",
        r"\bURL\b": "U R L",
        r"\bHTML\b": "H T M L",
        r"\bJSON\b": "J SON",
        r"\bASR\b": "A S R",
        r"\bTTS\b": "T T S",
    }

    for pattern, replacement in abbreviations.items():
        out = re.sub(
            pattern,
            replacement,
            out,
            flags=re.IGNORECASE,
        )

    return re.sub(
        r"\s+",
        " ",
        out,
    ).strip()