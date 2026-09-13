"""Topic-aware pre-computation of algorithm traces for LLM prompt injection.

Before calling the LLM to generate a scene, detect the algorithmic topic
from the animation brief and narration, run the matching symbolic tracer,
and inject the EXACT computed steps into the prompt as ground truth.

This eliminates the #1 source of factual errors in generated algorithm
animations: the LLM inventing array states, swap sequences, or search
steps that differ from the actual algorithm's behaviour.
"""
from __future__ import annotations

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Topic pattern registry
# ---------------------------------------------------------------------------
# Each entry: pattern (regex) -> (tracer_name, default_data, extra_kwargs)
# tracer_name maps to a function in symbolic_engine
# default_data is used when no literal array is found in the brief

_TOPIC_PATTERNS: list[tuple[str, str, list[Any], dict]] = [
    # Sorting algorithms
    (r"bubble[- ]?sort",   "trace_sorting",       [5, 3, 1, 4, 2], {"algorithm": "bubble"}),
    (r"insertion[- ]?sort","trace_sorting",       [4, 2, 7, 1, 9, 3], {"algorithm": "insertion"}),
    (r"selection[- ]?sort","trace_sorting",       [64, 25, 12, 22, 11], {"algorithm": "selection"}),
    (r"merge[- ]?sort",    "trace_sorting",       [38, 27, 43, 3, 9, 82, 10], {"algorithm": "merge"}),
    (r"quick[- ]?sort",    "trace_sorting",       [10, 7, 8, 9, 1, 5], {"algorithm": "quick"}),
    (r"heap[- ]?sort",     "trace_sorting",       [12, 11, 13, 5, 6, 7], {"algorithm": "heap"}),
    # Search
    (r"binary[- ]?search", "trace_binary_search", [2, 5, 8, 12, 16, 23, 38, 56, 72, 91], {"target": 23}),
    # Math
    (r"\bgcd\b|euclidean algorithm", "trace_euclid_gcd", [], {"a": 252, "b": 105}),
    # Tree
    (r"bst[\s\W]|binary search tree", "trace_bst_insertion", [], {"values": [50, 30, 70, 20, 40]}),
]

# Max steps to include in the prompt (keep tokens bounded)
_MAX_STEPS = 20
_MAX_TOKENS_APPROX = 1800  # rough character budget


# ---------------------------------------------------------------------------
# Array extractor
# ---------------------------------------------------------------------------

def _extract_array(text: str) -> list[int | float] | None:
    """Find the first numeric list literal in text, e.g. [5, 3, 1, 4, 2]."""
    m = re.search(r'\[\s*([\d,\s.]+)\]', text)
    if not m:
        return None
    try:
        values = [float(v.strip()) for v in m.group(1).split(',') if v.strip()]
        if 2 <= len(values) <= 20:
            # Prefer ints when all values are whole numbers
            if all(v == int(v) for v in values):
                return [int(v) for v in values]
            return values
    except ValueError:
        pass
    return None


def _extract_target(text: str) -> int | float | None:
    """Extract a search target from text like 'search for 23' or 'target=23'."""
    m = re.search(r'(?:search\s+for\s+|target[\s=:]*|find\s+)(\d+)', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Tracer runner
# ---------------------------------------------------------------------------

def _run_tracer(tracer_name: str, data: list[Any], kwargs: dict) -> list[dict] | None:
    """Call the named function in symbolic_engine and return its step list."""
    try:
        from prompt2render import symbolic_engine as se
        fn = getattr(se, tracer_name, None)
        if fn is None:
            return None
        if tracer_name == "trace_sorting":
            return fn(data, **kwargs)
        if tracer_name == "trace_binary_search":
            return fn(data, **kwargs)
        if tracer_name == "trace_euclid_gcd":
            a = kwargs.get("a", 252)
            b = kwargs.get("b", 105)
            return fn(a, b)
        if tracer_name == "trace_bst_insertion":
            values = kwargs.get("values", [50, 30, 70, 20, 40])
            return fn(values)
        return fn(data, **kwargs)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_and_trace(anim_brief: str, narration: str) -> str | None:
    """Detect the algorithm topic and return a formatted DATA TRACE block.

    The returned string is injected verbatim into the LLM scene-generation
    prompt, giving the model the exact step-by-step algorithm trace to
    animate. Returns None when no recognised topic is found.

    Args:
        anim_brief: The section's ANIM brief text.
        narration:  The concatenated narration sentences for the section.

    Returns:
        A formatted multi-line string starting with:
        ``PRE-COMPUTED ALGORITHM TRACE ...``
        or None if the topic is not recognised.
    """
    combined = (anim_brief + " " + narration).strip()
    lower = combined.lower()

    matched_pattern = None
    matched_tracer = None
    matched_data: list[Any] = []
    matched_kwargs: dict = {}

    for pattern, tracer_name, default_data, extra_kwargs in _TOPIC_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            matched_pattern = pattern
            matched_tracer = tracer_name
            matched_data = list(default_data)
            matched_kwargs = dict(extra_kwargs)
            break

    if matched_tracer is None:
        return None

    # Try to extract actual data from brief (overrides default)
    extracted = _extract_array(combined)
    if extracted and matched_tracer == "trace_sorting":
        matched_data = extracted
    elif extracted and matched_tracer == "trace_binary_search":
        matched_data = sorted(extracted)  # binary search needs sorted array
        target = _extract_target(combined)
        if target is not None and target in matched_data:
            matched_kwargs["target"] = int(target)
        elif matched_data:
            matched_kwargs["target"] = matched_data[len(matched_data) // 2]

    # Run the tracer
    steps = _run_tracer(matched_tracer, matched_data, matched_kwargs)
    if not steps:
        return None

    # Truncate to token budget
    steps = steps[:_MAX_STEPS]
    try:
        steps_json = json.dumps(steps, indent=2)
    except (TypeError, ValueError):
        return None

    # Truncate if too long
    if len(steps_json) > _MAX_TOKENS_APPROX:
        steps_json = steps_json[:_MAX_TOKENS_APPROX] + "\n  ...  (truncated)"

    # Format the data array / params header
    algo_label = matched_kwargs.get("algorithm", matched_tracer)
    if matched_data:
        data_line = f"Input data: {matched_data}"
    else:
        params_str = ", ".join(f"{k}={v}" for k, v in matched_kwargs.items())
        data_line = f"Input params: {params_str}"

    return (
        "PRE-COMPUTED ALGORITHM TRACE — USE THESE EXACT VALUES (do not invent states):\n"
        f"Algorithm: {matched_tracer} ({algo_label}) | {data_line}\n\n"
        "Each step has: type, indices (active positions), array (full state), description.\n"
        "Animate EXACTLY these states in order. Never skip steps or change values.\n\n"
        f"{steps_json}\n"
    )
