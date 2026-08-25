"""Shared narration-timing definitions.

Three call sites independently answered the question "how long is this
section?" and gave three different answers:

* ``renderer_manim._load_timing``      -- sum of per-sentence durations
* ``verifier_temporal._target_duration`` -- sum of per-sentence durations
* ``verifier_execution._safe_narration_duration`` -- last sentence's ``end``

The sum form silently **excludes every inter-sentence silence**, so it is
strictly smaller than the real span. Measured on a live 6-section project
that gap totalled 13.50s across 342.08s of narration (3.9%), and because
``renderer_manim``'s prompt asserts "the total animation duration MUST equal
{duration}", every generated Manim scene was being instructed to finish
early by exactly the accumulated silence in its section.

This module defines both quantities once, with unambiguous names, so a
caller has to choose deliberately:

``narration_span``          -- wall-clock length of the section (authoritative)
``narration_speech_total``  -- time spent actually speaking (excludes gaps)

Anything that must line up with rendered video wants ``narration_span``.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

__all__ = [
    "sentence_duration",
    "narration_span",
    "narration_speech_total",
]


def sentence_duration(sentence: Any) -> float | None:
    """One sentence's spoken duration, or ``None`` when undeterminable.

    Handles both alignment formats: the current one stores ``start``/``end``
    (see ``align.reconcile``), the historical one stored ``dur``.
    """

    if not isinstance(sentence, dict):
        return None

    raw = sentence.get("dur")

    if raw is None:
        try:
            start = float(sentence.get("start", 0.0))
            end = float(sentence.get("end", start))
        except (TypeError, ValueError):
            return None
        raw = end - start

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value) or value < 0:
        return None

    return value


def _sentence_end(sentence: Any) -> float | None:
    """A sentence's absolute end timestamp, when it carries one."""

    if not isinstance(sentence, dict):
        return None

    raw = sentence.get("end")

    if raw is None:
        return None

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    return value if math.isfinite(value) and value >= 0 else None


def narration_span(sentences: Iterable[Any]) -> float:
    """Wall-clock length of a section, **including** inter-sentence silence.

    This is the authoritative length for anything that has to line up with a
    rendered clip: the video must cover the silence between sentences too.

    Uses the last sentence's ``end``. Degrades to
    :func:`narration_speech_total` when the data carries no absolute
    timestamps at all (the historical ``dur``-only format), because a sum is
    then the best available estimate. Returns ``0.0`` for empty input.
    """

    items = [s for s in sentences if isinstance(s, dict)]

    if not items:
        return 0.0

    ends = [end for end in (_sentence_end(s) for s in items) if end is not None]

    if ends:
        # max() rather than [-1]: alignment is normally monotonic, but a
        # single out-of-order sentence must not shorten the whole section.
        return max(ends)

    return narration_speech_total(items)


def narration_speech_total(sentences: Iterable[Any]) -> float:
    """Total time spent speaking, **excluding** inter-sentence silence.

    Use only when the question really is "how much speech is there" — not
    for anything that must match a rendered clip's duration.
    """

    total = 0.0

    for sentence in sentences:
        value = sentence_duration(sentence)

        if value is not None:
            total += value

    return total
