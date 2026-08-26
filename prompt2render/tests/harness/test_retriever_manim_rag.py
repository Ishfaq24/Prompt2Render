"""Tier 2 Phase 7: retriever_manim_rag -- pattern RAG (replacing F14).

No existing tests covered this plugin at all before this phase. Covers:
keyword matching/scoring/ordering behavior (unchanged mechanism), that no
snippet text still says "SceneKit" (the whole point of this phase), the new
linked_list_basic snippet, and the plugin's end-to-end run() behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.retriever_manim_rag import (
    SNIPPETS,
    RetrieverManimRagPlugin,
    _retrieve,
)


# ------------------------------------------------------------- vocabulary --

def test_no_snippet_mentions_scenekit():
    for snippet in SNIPPETS:
        assert "SceneKit" not in snippet.text, snippet.snippet_id
        assert "scenekit" not in snippet.text.lower(), snippet.snippet_id


def test_every_snippet_mentions_manim_or_is_generic_layout_guidance():
    # Not every snippet needs the literal word "Manim" (some guidance is
    # purely structural/layout advice), but every one should read as
    # concrete Manim-relevant guidance, not the old "documented primitive"
    # hand-wave.
    for snippet in SNIPPETS:
        assert "documented" not in snippet.text.lower(), snippet.snippet_id


def test_snippet_ids_are_unique():
    ids = [s.snippet_id for s in SNIPPETS]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------- retrieval

def test_array_keyword_matches_array_basic():
    results = _retrieve("This section shows an array of five elements.", max_snippets=3)
    assert results
    assert results[0]["snippet_id"] == "array_basic"


def test_linked_list_matches_new_snippet_and_ranks_above_tree():
    results = _retrieve(
        "This section explains a linked list with a next pointer connecting each node.",
        max_snippets=5,
    )
    ids = [r["snippet_id"] for r in results]
    assert "linked_list_basic" in ids
    assert ids.index("linked_list_basic") == 0
    if "tree_basic" in ids:
        assert ids.index("linked_list_basic") < ids.index("tree_basic")


def test_pure_tree_description_still_matches_tree_basic():
    results = _retrieve(
        "This section builds a binary tree and shows the parent-child relationship.",
        max_snippets=3,
    )
    ids = [r["snippet_id"] for r in results]
    assert "tree_basic" in ids
    assert "linked_list_basic" not in ids


def test_no_match_returns_empty():
    assert _retrieve("An entirely unrelated topic about weather patterns.", max_snippets=3) == []


def test_max_snippets_caps_results():
    results = _retrieve(
        "array list index element tree node pointer reference code function",
        max_snippets=2,
    )
    assert len(results) <= 2


# ----------------------------------------------------------------- plugin --

def test_plugin_populates_retrieval_context_per_stem():
    ctx = SceneContext()
    ctx.scene_plan = [
        ScenePlanEntry(
            index=1,
            stem="01",
            title="T",
            anim="Show a linked list with a next pointer.",
            narration_text="",
        ),
        ScenePlanEntry(index=2, stem="02", title="T2", anim="", narration_text=""),
    ]

    RetrieverManimRagPlugin().run(ctx)

    assert "linked_list_basic" in [r["snippet_id"] for r in ctx.retrieval_context["01"]]
    assert ctx.retrieval_context["02"] == []


def test_plugin_gate_is_advisory():
    assert RetrieverManimRagPlugin()._default_gate() is False
