"""Semantic vector embedding and nearest-neighbor search for the Asset Catalog."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence
from .loader import AssetDefinition


STOPWORDS = frozenset({
    "the", "and", "a", "an", "in", "on", "of", "to", "for", "with",
    "is", "was", "are", "by", "at", "it", "from", "as", "about",
    "this", "that", "these", "those", "have", "has", "had", "not",
})


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alpha-numeric words filtering common stopwords."""
    clean = re.sub(r"[^\w\s-]", " ", text.lower())
    words = [w for w in clean.split() if len(w) > 2 and w not in STOPWORDS]
    return words


class SparseSemanticVectorizer:
    """Deterministic, zero-dependency TF-IDF semantic vectorizer for asset retrieval."""

    def __init__(self, catalog: dict[str, AssetDefinition]) -> None:
        self.catalog = catalog
        self.asset_ids = list(catalog.keys())
        self.doc_freqs: Counter[str] = Counter()
        self.asset_vectors: dict[str, dict[str, float]] = {}
        self.num_docs = len(self.asset_ids)

        # Build vocabulary and doc frequencies
        for aid, asset in catalog.items():
            doc_text = f"{asset.name} {asset.category} {asset.description} {' '.join(asset.keywords)}"
            tokens = set(_tokenize(doc_text))
            for t in tokens:
                self.doc_freqs[t] += 1

        # Compute normalized TF-IDF vector per asset
        for aid, asset in catalog.items():
            doc_text = f"{asset.name} {asset.category} {asset.description} {' '.join(asset.keywords)}"
            tokens = _tokenize(doc_text)
            counts = Counter(tokens)
            vec: dict[str, float] = {}
            for t, count in counts.items():
                idf = math.log((self.num_docs + 1.0) / (self.doc_freqs[t] + 1.0)) + 1.0
                vec[t] = count * idf
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.asset_vectors[aid] = {t: v / norm for t, v in vec.items()}

    def search(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        """Search catalog for query text using cosine similarity.

        Returns list of (asset_id, similarity_score).
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        q_counts = Counter(query_tokens)
        q_vec: dict[str, float] = {}
        for t, count in q_counts.items():
            if t in self.doc_freqs:
                idf = math.log((self.num_docs + 1.0) / (self.doc_freqs[t] + 1.0)) + 1.0
                q_vec[t] = count * idf

        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm <= 0:
            return []
        q_norm_vec = {t: v / q_norm for t, v in q_vec.items()}

        scores: list[tuple[str, float]] = []
        for aid, a_vec in self.asset_vectors.items():
            dot = sum(val * a_vec[t] for t, val in q_norm_vec.items() if t in a_vec)
            if dot > 0.22:
                scores.append((aid, dot))

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:top_k]
