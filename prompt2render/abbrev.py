"""Single source of truth for abbreviation -> spoken-form expansion.

Two call sites need this and previously kept their own, disagreeing tables:
`mathspeech.speech_text()` (what Kokoro actually synthesizes) and
`textseg.normalise_token()` (the ASR-alignment/caption-drift comparison form).
When the two tables differ on an entry (e.g. one spells out "JSON" and the
other doesn't), the synthesized audio and what alignment/caption-drift QC
expects it to say silently diverge. Both call sites now derive from the table
below so they can't drift apart again.
"""
from __future__ import annotations

import re

#: (match_form, spoken_form). match_form is matched case-insensitively with a
#: word boundary before it, and after it too unless match_form already ends in
#: punctuation (a trailing period already terminates the match).
ABBREVIATIONS: list[tuple[str, str]] = [
    # Latin / discourse.
    ("i.e.", "that is"),
    ("e.g.", "for example"),
    ("etc.", "etcetera"),
    ("vs.", "versus"),
    ("vs", "versus"),
    ("cf.", "compare"),
    ("et al.", "and others"),
    ("approx.", "approximately"),
    ("fig.", "figure"),
    ("eq.", "equation"),
    ("no.", "number"),
    # Titles.
    ("Dr.", "Doctor"),
    ("Mr.", "Mister"),
    ("Mrs.", "Missus"),
    ("Ms.", "Miss"),
    ("Prof.", "Professor"),
    ("St.", "Saint"),
    ("Jr.", "Junior"),
    ("Sr.", "Senior"),
    # Units.
    ("km", "kilometers"),
    ("kg", "kilograms"),
    ("cm", "centimeters"),
    ("mm", "millimeters"),
    ("kHz", "kilohertz"),
    ("MHz", "megahertz"),
    ("GHz", "gigahertz"),
    ("Hz", "hertz"),
    ("GB", "gigabytes"),
    ("MB", "megabytes"),
    ("KB", "kilobytes"),
    ("TB", "terabytes"),
    # Tech acronyms that should NOT be letter-spelled by the generic fallback
    # below (RAM is pronounced as a word, not "R A M").
    ("RAM", "ram"),
]

# Longer/more specific patterns must be tried before shorter ones that could
# be a prefix of them (e.g. "vs." before "vs").
_ORDERED = sorted(ABBREVIATIONS, key=lambda pair: -len(pair[0]))

_COMPILED = [
    (
        re.compile(
            (r"\b" if match[0].isalnum() else "")
            + re.escape(match)
            + (r"\b" if match[-1].isalnum() else ""),
            re.IGNORECASE,
        ),
        spoken,
    )
    for match, spoken in _ORDERED
]

#: Fallback for acronyms not in the explicit table above: any standalone
#: run of 2-5 uppercase letters is treated as an initialism and letter-spelled
#: (e.g. "JSON" -> "J S O N", "NASA" -> "N A S A"). Mirrors the equivalent
#: heuristic in textseg.normalise_token() so unlisted acronyms still agree
#: between synthesis and alignment.
_GENERIC_ACRONYM = re.compile(r"\b[A-Z]{2,5}\b")


def expand_for_speech(text: str) -> str:
    """Expand abbreviations in `text` into a form suitable for TTS."""
    out = text
    for pattern, spoken in _COMPILED:
        out = pattern.sub(spoken, out)
    out = _GENERIC_ACRONYM.sub(lambda m: " ".join(m.group(0)), out)
    return out


def alignment_lexicon() -> dict[str, str]:
    """The dict-shaped view `textseg.normalise_token()` looks up by exact,
    lowercased, punctuation-stripped SINGLE token — so multi-word entries
    (e.g. "et al.") are skipped here; they still expand correctly for speech
    via `expand_for_speech()`, which matches over raw text, not per-token."""
    lexicon: dict[str, str] = {}
    for match, spoken in ABBREVIATIONS:
        key = match.rstrip(".").lower()
        if " " in key:
            continue
        lexicon[key] = spoken.lower()
    return lexicon
