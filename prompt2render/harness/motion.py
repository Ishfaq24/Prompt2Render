"""Shared motion-op vocabulary and storyboard-section lookup.

Single source of truth for the fixed set of Manim motion primitives a
storyboard state may declare (``MOTION_OPS``), the validator over that
vocabulary (``validate_motion_ops``), and the stem-with-index-fallback
storyboard-section lookup used identically by ``renderer_manim`` and
``verifier_execution``. Three call sites (``planner_llm``,
``verifier_storyboard``, ``renderer_manim``) previously would have had to
hand-duplicate this vocabulary; importing it from here instead means they
cannot drift apart.
"""

from __future__ import annotations

import keyword
from typing import Any

from .context import SceneContext

#: Fixed vocabulary of motion primitives a storyboard state may declare.
#: Maps op name -> the set of required string keys on that op's dict.
#: Timing is never part of this vocabulary — it is computed deterministically
#: downstream from the narration cue map, not authored here.
MOTION_OPS: dict[str, frozenset[str]] = {
    "Create": frozenset({"target"}),
    "Write": frozenset({"target"}),
    "FadeIn": frozenset({"target"}),
    "FadeOut": frozenset({"target"}),
    "Transform": frozenset({"target", "into"}),
    "MoveTo": frozenset({"target", "anchor"}),
    "Highlight": frozenset({"target"}),
}


def validate_motion_ops(motion: Any) -> list[str]:
    """Validate one state's ``motion`` list against ``MOTION_OPS``.

    Returns bare error messages (no "Section X, state Y" context) — each
    call site wraps these in its own surrounding context/phrasing.
    """

    if not isinstance(motion, list):
        return ["motion must be a list."]

    errors: list[str] = []

    for op_no, op in enumerate(motion):
        if not isinstance(op, dict):
            errors.append(f"motion {op_no}: invalid motion op.")
            continue

        op_name = op.get("op")

        if op_name not in MOTION_OPS:
            errors.append(
                f"motion {op_no}: unknown op {op_name!r}; "
                f"must be one of {sorted(MOTION_OPS)}."
            )
            continue

        required = MOTION_OPS[op_name]

        missing = sorted(
            key
            for key in required
            if not (isinstance(op.get(key), str) and op.get(key).strip())
        )

        if missing:
            errors.append(
                f"motion {op_no}: {op_name} is missing required key(s) {missing}."
            )
            continue

        for key in required:
            value = op.get(key, "")

            if not (
                isinstance(value, str)
                and value.isidentifier()
                and not keyword.iskeyword(value)
            ):
                errors.append(
                    f"motion {op_no}: {op_name}'s {key!r} value {value!r} "
                    "must be a valid Python identifier (it becomes self.<name> "
                    "in the compiled scene)."
                )

    return errors


def find_storyboard_states(
    context: SceneContext,
    stem: str,
    index: int | None = None,
) -> list[dict[str, Any]] | None:
    """Look up one section's ``states`` list by stem, falling back to index.

    Some deterministic-fallback storyboard sections have historically been
    written without a ``stem`` key (see ``planner_llm._fallback``), so a
    stem-only lookup can silently miss a section that genuinely exists.
    Falling back to a positional ``index`` match keeps the lookup working
    even against those degraded sections.
    """

    storyboard = getattr(context, "storyboard_plan", None)

    if not isinstance(storyboard, dict):
        return None

    sections = storyboard.get("sections")

    if not isinstance(sections, list):
        return None

    for section in sections:
        if isinstance(section, dict) and str(section.get("stem", "")) == str(stem):
            return section.get("states")

    if index is not None:
        for section in sections:
            if isinstance(section, dict) and section.get("index") == index:
                return section.get("states")

    return None
