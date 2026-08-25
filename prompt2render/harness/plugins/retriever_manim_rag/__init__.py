"""Deterministic local pattern retriever for Prompt2Render.

Tier 2 Phase 7 (docs/ARCHITECTURE_AUDIT.md SS17, replacing F14 -- "RAG is a
keyword matcher over ~10 hardcoded SceneKit snippets, disabled by default,
and targets a vocabulary irrelevant to Manim"). Confirmed this session:
before this phase, ``context.retrieval_context`` was never read by any live
plugin (``docs/HARNESS.md``/``docs/MIGRATION_INVENTORY.md`` already
documented it as a "no-op stub"). This module's snippet *text* is now
genuinely Manim-relevant, and ``renderer_manim.GeneratorManimPlugin``
injects retrieved patterns into its prompts (see that module's
``_pattern_hints``) -- the retrieval mechanism itself was already sound and
is unchanged.

This plugin provides lightweight, dependency-free retrieval of vetted Manim
layout/structure patterns. It deliberately does NOT perform embedding-based
RAG and does not make an LLM request -- F14 calls this a deliberate design
choice, not a defect, and nothing here second-guesses it.

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


#: Tier 2 Phase 7 (docs/ARCHITECTURE_AUDIT.md SS17, "pattern RAG", replacing
#: F14): every snippet's ``text`` was originally worded "SceneKit pattern:
#: ..." -- a vocabulary irrelevant to Manim, the harness's actual renderer.
#: Rewritten as syntax-agnostic conceptual guidance grounded in real Manim
#: vocabulary (VGroup, Arrow, MathTex, Code, ...) -- deliberately not raw
#: Python nor construction-DSL JSON, since the retrieved text is injected
#: into three different prompt shapes (renderer_manim's freehand,
#: compiler-backed setup-only, and construction-DSL prompts) and must read
#: naturally in all three. The matching *mechanism* below
#: (_normalize/_contains_term/_retrieve) is unchanged -- F14 itself calls
#: "not embedding-based" a deliberate design choice, not a defect.
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
            "Manim pattern: represent array/list elements as a horizontally "
            "arranged group of uniform boxes (e.g. squares or rectangles), "
            "each with an index or value label; keep spacing consistent "
            "across states."
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
            "Manim pattern: represent tree/BST nodes as circles at stable, "
            "persistent coordinates; connect parent-child pairs with "
            "explicit edges (lines or arrows) rather than implying "
            "structure from proximity alone."
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
            "Manim pattern: represent a pointer/reference as an arrow "
            "anchored to the referenced object's edge, or a label "
            "positioned relative to it -- never an unanchored floating "
            "label."
        ),
        priority=10,
    ),
    Snippet(
        snippet_id="linked_list_basic",
        keywords=(
            "linked list",
            "linked lists",
            "next pointer",
            "singly linked",
            "doubly linked",
        ),
        text=(
            "Manim pattern: represent linked-list nodes as boxes holding a "
            "value and a next-pointer slot; connect consecutive nodes with "
            "an arrow from one node's pointer slot to the next node, kept "
            "in a stable horizontal or vertical sequence -- distinct from a "
            "tree's parent-child hierarchy: a linked list has no branching."
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
            "Manim pattern: use the Code primitive for syntax-highlighted "
            "source; keep it small enough to fit the frame, and reveal or "
            "highlight lines progressively rather than showing the whole "
            "block at once."
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
            "Manim pattern: place comparison subjects in stable left/right "
            "zones with a clear visual separator, sharing a common "
            "baseline."
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
            "Manim pattern: represent sequential steps as nodes connected "
            "by directional arrows; reveal one transition at a time rather "
            "than the whole pipeline at once."
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
            "Manim pattern: represent graph vertices as explicit point "
            "objects and edges as explicit connections between them; never "
            "imply an edge from layout proximity alone."
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
            "Manim pattern: use a stable horizontal axis and reveal events "
            "along it in temporal order without repositioning already-"
            "placed events."
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
            "Manim pattern: center mathematical expressions and show "
            "algebraic steps by transforming one expression into the next "
            "rather than fading one out and a new one in."
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