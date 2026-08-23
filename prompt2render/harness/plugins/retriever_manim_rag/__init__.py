"""Deterministic local snippet retriever for Prompt2Render.

This plugin provides lightweight, dependency-free retrieval of vetted SceneKit
patterns. It deliberately does NOT perform embedding-based RAG and does not
make an LLM request.

Design goals
------------
* Retrieve only from a local, explicitly curated snippet library.
* Match concepts using normalized keywords/aliases rather than brittle exact
  single-word checks.
* Keep retrieval deterministic and auditable.
* Do not permanently contaminate the authored animation brief with retrieval
  text.
* Expose retrieved snippets as a separate ``retrieval_context`` artifact when
  the SceneContext supports it, while retaining a compatibility fallback for
  older ScenePlanEntry implementations.
* Never claim that a retrieved snippet is authoritative; the visual contract
  and scene plan remain authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ...context import SceneContext
from ...plugin import Plugin


# ---------------------------------------------------------------------------
# Curated snippet library
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snippet:
    """One vetted SceneKit retrieval item."""

    snippet_id: str
    keywords: tuple[str, ...]
    text: str
    priority: int = 0


SNIPPETS: tuple[Snippet, ...] = (
    Snippet(
        snippet_id="array_basic",
        keywords=(
            "array",
            "arrays",
            "list",
            "index",
            "indices",
            "element",
        ),
        text=(
            "SceneKit pattern: use the documented array primitive for a "
            "contiguous sequence of elements; keep index labels aligned with "
            "the corresponding element."
        ),
        priority=10,
    ),
    Snippet(
        snippet_id="tree_basic",
        keywords=(
            "tree",
            "trees",
            "binary tree",
            "bst",
            "node",
            "nodes",
            "parent",
            "child",
        ),
        text=(
            "SceneKit pattern: construct tree diagrams from explicit nodes "
            "and edges/arrows; preserve stable node coordinates between "
            "successive states."
        ),
        priority=10,
    ),
    Snippet(
        snippet_id="pointer_basic",
        keywords=(
            "pointer",
            "pointers",
            "reference",
            "address",
            "index pointer",
        ),
        text=(
            "SceneKit pattern: represent a pointer/reference with a clearly "
            "anchored label or arrow and keep its target explicit."
        ),
        priority=10,
    ),
    Snippet(
        snippet_id="code_block",
        keywords=(
            "code",
            "program",
            "programming",
            "source code",
            "snippet",
            "algorithm",
            "function",
            "python",
            "java",
            "c",
            "cpp",
        ),
        text=(
            "SceneKit pattern: use the documented code-block primitive for "
            "syntax-highlighted source; keep code within the frame and reveal "
            "important lines progressively."
        ),
        priority=8,
    ),
    Snippet(
        snippet_id="comparison_layout",
        keywords=(
            "compare",
            "comparison",
            "versus",
            "vs",
            "before after",
            "side by side",
            "difference",
        ),
        text=(
            "SceneKit pattern: place comparison subjects in stable left/right "
            "zones with a clear visual separator and matched baselines."
        ),
        priority=8,
    ),
    Snippet(
        snippet_id="flow_diagram",
        keywords=(
            "flow",
            "workflow",
            "pipeline",
            "process",
            "step",
            "steps",
            "sequence",
        ),
        text=(
            "SceneKit pattern: represent sequential processes with explicit "
            "states and directional connectors; reveal one major transition "
            "at a time."
        ),
        priority=7,
    ),
    Snippet(
        snippet_id="graph_basic",
        keywords=(
            "graph",
            "graphs",
            "vertex",
            "vertices",
            "edge",
            "edges",
        ),
        text=(
            "SceneKit pattern: represent graph vertices as stable objects and "
            "edges as explicit connections; do not infer edge direction from "
            "layout alone."
        ),
        priority=7,
    ),
    Snippet(
        snippet_id="timeline",
        keywords=(
            "timeline",
            "time",
            "temporal",
            "duration",
            "sequence over time",
        ),
        text=(
            "SceneKit pattern: use a stable horizontal time axis and reveal "
            "events in temporal order without moving already established "
            "events unnecessarily."
        ),
        priority=6,
    ),
    Snippet(
        snippet_id="equation",
        keywords=(
            "equation",
            "formula",
            "mathematical",
            "math",
            "theorem",
            "proof",
            "expression",
        ),
        text=(
            "SceneKit pattern: keep mathematical expressions centered and "
            "separate from explanatory labels; transform equivalent "
            "expressions rather than replacing them abruptly."
        ),
        priority=6,
    ),
)


# ---------------------------------------------------------------------------
# Normalization/tokenization
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize text for deterministic matching."""

    text = str(text or "").lower()

    # Treat common separators as spaces.
    text = re.sub(
        r"[_/\\\-]+",
        " ",
        text,
    )

    # Collapse whitespace.
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _contains_term(
    text: str,
    term: str,
) -> bool:
    """Match a keyword as a phrase/word, not a substring."""

    normalized_term = _normalize(
        term
    )

    if not normalized_term:
        return False

    # Escape the term and permit ordinary whitespace variation.
    pattern = re.escape(
        normalized_term
    ).replace(
        r"\ ",
        r"\s+",
    )

    return bool(
        re.search(
            rf"(?<!\w){pattern}(?!\w)",
            text,
        )
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _retrieve(
    text: str,
    *,
    max_snippets: int,
) -> list[dict[str, Any]]:
    """Retrieve the highest-scoring deterministic snippets."""

    normalized = _normalize(
        text
    )

    scored: list[
        tuple[int, int, Snippet, list[str]]
    ] = []

    for snippet in SNIPPETS:

        matched = [
            keyword
            for keyword in snippet.keywords
            if _contains_term(
                normalized,
                keyword,
            )
        ]

        if not matched:
            continue

        # Long/multi-word concepts are more informative than generic terms.
        score = (
            snippet.priority
            + sum(
                2 if " " in keyword else 1
                for keyword in matched
            )
        )

        scored.append(
            (
                score,
                len(matched),
                snippet,
                matched,
            )
        )

    # Stable deterministic ordering:
    # score ↓, number of matched keywords ↓, snippet id ↑.
    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            item[2].snippet_id,
        )
    )

    results: list[dict[str, Any]] = []

    for score, _, snippet, matched in scored[
        :max_snippets
    ]:
        results.append(
            {
                "snippet_id": snippet.snippet_id,
                "text": snippet.text,
                "matched_keywords": matched,
                "score": score,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Context compatibility
# ---------------------------------------------------------------------------

def _store_retrieval(
    context: SceneContext,
    results: dict[str, list[dict[str, Any]]],
) -> None:
    """Store retrieval results without changing authored scene briefs."""

    # Preferred structured context field.
    context.retrieval_context = results

    # Also expose a compatibility alias if downstream code expects a
    # scene-level retrieval artifact.
    context.retriever_manim_rag = results


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class RetrieverManimRagPlugin(Plugin):
    """Retrieve vetted SceneKit implementation patterns deterministically."""

    name = "retriever_manim_rag"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "retrieval_context",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        max_snippets = _safe_max_snippets(
            self.config.get(
                "max_snippets",
                3,
            )
        )

        retrieval: dict[
            str,
            list[dict[str, Any]]
        ] = {}

        for entry in context.scene_plan:

            animation = (
                getattr(
                    entry,
                    "anim",
                    "",
                )
                or ""
            )

            narration = (
                getattr(
                    entry,
                    "narration_text",
                    "",
                )
                or ""
            )

            # Search the semantic content, but NEVER rewrite it.
            search_text = (
                f"{animation}\n{narration}"
            )

            results = _retrieve(
                search_text,
                max_snippets=max_snippets,
            )

            retrieval[str(entry.stem)] = results

        _store_retrieval(
            context,
            retrieval,
        )

        return context

    def _default_gate(self) -> bool:
        return False


def _safe_max_snippets(
    value: Any,
) -> int:
    """Normalize retrieval result count."""

    try:
        value = int(value)
    except (TypeError, ValueError):
        return 3

    return min(
        max(value, 0),
        10,
    )