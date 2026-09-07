"""Tests for Semantic Embedding retrieval and ablation benchmark evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from prompt2render.assets.loader import load_catalog
from prompt2render.assets.embeddings import SparseSemanticVectorizer
from prompt2render.harness.plugins.retriever_asset_rag import match_assets
from prompt2render.tools.eval_retrieval_ablation import evaluate_mode


def test_sparse_semantic_vectorizer_search():
    """Verify that vectorizer returns relevant matches for semantic concept."""
    catalog = load_catalog()
    vectorizer = SparseSemanticVectorizer(catalog)
    results = vectorizer.search("CPU chip with internal registers and ALU", top_k=3)
    assert len(results) > 0
    top_id = results[0][0]
    assert top_id in ("cpu_core", "alu_unit", "register_file")


def test_hybrid_vs_keyword_retrieval():
    """Ensure hybrid retrieval catches terms not in exact keywords."""
    catalog = load_catalog()
    vectorizer = SparseSemanticVectorizer(catalog)

    query = "the microprocessor fetches data from primary storage"
    matches_kw = match_assets(query, catalog, max_matches=3, mode="keyword", vectorizer=vectorizer)
    matches_hyb = match_assets(query, catalog, max_matches=3, mode="hybrid", vectorizer=vectorizer)

    # Hybrid should leverage subwords/vector similarity
    assert len(matches_hyb) >= 1
    hyb_ids = [m.id for m in matches_hyb]
    assert "cpu_core" in hyb_ids or "memory_bank" in hyb_ids


def test_eval_retrieval_ablation_metrics():
    """Verify that evaluate_mode computes valid Precision, Recall, and MRR metrics."""
    catalog = load_catalog()
    vectorizer = SparseSemanticVectorizer(catalog)

    for mode in ("keyword", "embedding", "hybrid"):
        metrics = evaluate_mode(mode, catalog, vectorizer, top_k=3)
        assert 0.0 <= metrics["P@1"] <= 1.0
        assert 0.0 <= metrics["P@3"] <= 1.0
        assert 0.0 <= metrics["R@3"] <= 1.0
        assert 0.0 <= metrics["MRR"] <= 1.0
        assert metrics["latency_ms"] >= 0.0
