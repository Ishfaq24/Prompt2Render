"""Deterministic cross-scene lifecycle verifier.

This verifier checks continuity of persistent visual objects across adjacent
scenes. It is intentionally conservative: a change is reported only when the
verifier can identify a comparable object in both scenes.

The original implementation used a single global ``last_arrays`` heuristic.
This version makes the comparison scene-aware, handles literal and variable-
based array declarations, avoids false positives for unrelated arrays, and
records explicit lifecycle findings that the repair router can consume.

It does NOT attempt to prove subject-matter correctness. Its purpose is visual
state continuity between adjacent scenes.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_JUSTIFICATION_TERMS = (
    "split",
    "merge",
    "add",
    "adds",
    "added",
    "remove",
    "removes",
    "removed",
    "append",
    "appends",
    "appended",
    "pop",
    "insert",
    "inserts",
    "inserted",
    "delete",
    "deletes",
    "deleted",
    "expand",
    "expands",
    "expanded",
    "shrink",
    "shrinks",
    "shrunk",
    "resize",
    "resized",
    "length",
    "size",
    "element",
    "elements",
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArrayObservation:
    """One statically observable array."""

    name: str | None
    length: int
    literal_values: tuple[str, ...]
    source: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_text(
    text: str,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(text or "").lower(),
    ).strip()


def _has_explicit_change_justification(
    narration: str,
    terms: tuple[str, ...],
) -> bool:
    """Return whether narration explicitly discusses a state change."""

    text = _normalize_text(
        narration
    )

    return any(
        re.search(
            rf"(?<!\w){re.escape(term)}(?!\w)",
            text,
        )
        for term in terms
    )


def _literal_array_values(
    node: ast.AST,
) -> tuple[str, ...] | None:
    """Extract literal array/list values when statically available."""

    if not isinstance(
        node,
        (ast.List, ast.Tuple),
    ):
        return None

    values: list[str] = []

    for element in node.elts:
        try:
            values.append(
                ast.unparse(element)
            )
        except Exception:
            values.append(
                ast.dump(element)
            )

    return tuple(values)


def _extract_scenekit_arrays(
    source: str,
) -> list[ArrayObservation]:
    """Extract k.array(...) calls using the Python AST.

    This is substantially safer than a regular expression because nested
    expressions, strings, and function calls cannot accidentally break the
    parser.
    """

    try:
        tree = ast.parse(
            source
        )
    except SyntaxError:
        return []

    observations: list[
        ArrayObservation
    ] = []

    # First collect simple assignments such as:
    #
    #   values = [2, 6, 1]
    #
    # This lets us resolve:
    #
    #   k.array(values)
    #
    variables: dict[
        str,
        tuple[str, ...],
    ] = {}

    for node in ast.walk(tree):

        if not isinstance(
            node,
            ast.Assign,
        ):
            continue

        values = _literal_array_values(
            node.value
        )

        if values is None:
            continue

        for target in node.targets:
            if isinstance(
                target,
                ast.Name,
            ):
                variables[
                    target.id
                ] = values

    for node in ast.walk(tree):

        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        # Match:
        #
        #   k.array(...)
        #
        if not (
            isinstance(
                node.func,
                ast.Attribute,
            )
            and node.func.attr == "array"
            and isinstance(
                node.func.value,
                ast.Name,
            )
            and node.func.value.id == "k"
        ):
            continue

        if not node.args:
            continue

        argument = node.args[0]

        values = _literal_array_values(
            argument
        )

        if values is None and isinstance(
            argument,
            ast.Name,
        ):
            values = variables.get(
                argument.id
            )

        if values is None:
            # We know that an array call exists but cannot statically prove
            # its length. Do not guess.
            continue

        try:
            source_text = ast.unparse(
                node
            )
        except Exception:
            source_text = "k.array(...)"

        observations.append(
            ArrayObservation(
                name=(
                    argument.id
                    if isinstance(
                        argument,
                        ast.Name,
                    )
                    else None
                ),
                length=len(values),
                literal_values=values,
                source=source_text,
            )
        )

    return observations


def _select_primary_array(
    arrays: list[ArrayObservation],
) -> ArrayObservation | None:
    """Select a stable primary array without inventing identity.

    Prefer a named array because its identity can be compared across scenes.
    Otherwise use the first literal array, matching the original plugin's
    primary-array behaviour.
    """

    if not arrays:
        return None

    named = [
        array
        for array in arrays
        if array.name
    ]

    return (
        named[0]
        if named
        else arrays[0]
    )


def _same_array_identity(
    previous: ArrayObservation,
    current: ArrayObservation,
) -> bool:
    """Determine whether two observations plausibly represent one array."""

    # Named variables give us the strongest static identity.
    if (
        previous.name
        and current.name
    ):
        return previous.name == current.name

    # If neither has a name, preserve the original "primary array" heuristic.
    if (
        not previous.name
        and not current.name
    ):
        return True

    # One named and one literal array is ambiguous. Do not report a mismatch.
    return False


def _finding(
    *,
    stem: str,
    message: str,
    severity: Severity,
) -> dict[str, Any]:
    result = Finding(
        finding_id=next_finding_id(
            "life"
        ),
        scene_id=stem,
        category=Category.SEMANTIC,
        severity=severity,
        message=message,
    ).as_check_result()

    result["finding_type"] = (
        "lifecycle_violation"
    )

    # Deliberately no ``mismatch_subtype``. This finding used to carry
    # ``mismatch_subtype="temporal_mismatch"``, which is doubly wrong: a
    # lifecycle violation is not a temporal one, and the router only ever
    # reads that key for ``finding_type == "audio_visual_mismatch"``
    # (see repair_router/policy.py:decide), so it routed identically with
    # or without it. Harmless today, but a live trap the moment
    # lifecycle_violation gains a subtype table -- it would then silently
    # route every lifecycle defect down the temporal branch.

    return result


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class VerifierLifecyclePlugin(Plugin):
    """Verify continuity of persistent visual state across adjacent scenes."""

    name = "verifier_lifecycle"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
            "scene_plan",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        findings: list[
            dict[str, Any]
        ] = []

        justification_terms = tuple(
            self.config.get(
                "justification_terms",
                DEFAULT_JUSTIFICATION_TERMS,
            )
        )

        previous_entry = None
        previous_array = None

        for entry in context.scene_plan:

            artifact = (
                context.code_artifacts.get(
                    entry.stem
                )
            )

            if (
                artifact is None
                or artifact.path is None
                or not artifact.path.exists()
            ):
                # Missing source is handled by verifier_execution.
                previous_entry = None
                previous_array = None
                continue

            try:
                source = artifact.path.read_text(
                    encoding="utf-8"
                )
            except Exception:
                previous_entry = None
                previous_array = None
                continue

            current_arrays = (
                _extract_scenekit_arrays(
                    source
                )
            )

            current_array = (
                _select_primary_array(
                    current_arrays
                )
            )

            if (
                previous_entry is not None
                and previous_array is not None
                and current_array is not None
                and _same_array_identity(
                    previous_array,
                    current_array,
                )
            ):
                if (
                    previous_array.length
                    != current_array.length
                ):
                    narration = getattr(
                        entry,
                        "narration_text",
                        "",
                    )

                    justified = (
                        _has_explicit_change_justification(
                            narration,
                            justification_terms,
                        )
                    )

                    if not justified:
                        severity = (
                            Severity.BLOCKING
                            if self.is_gate()
                            else Severity.WARNING
                        )

                        findings.append(
                            _finding(
                                stem=entry.stem,
                                severity=severity,
                                message=(
                                    "Lifecycle mismatch: "
                                    f"array length changed from "
                                    f"{previous_array.length} to "
                                    f"{current_array.length} "
                                    "between adjacent scenes "
                                    "without explicit narration "
                                    "justification."
                                ),
                            )
                        )

            # Only advance lifecycle state when an array was actually
            # observed. This prevents an unrelated scene with no array from
            # destroying continuity information.
            if current_array is not None:
                previous_entry = entry
                previous_array = current_array

        context.check_results[
            self.name
        ] = findings

        return context

    def _default_gate(self) -> bool:
        """Lifecycle checks are advisory by default."""

        return False