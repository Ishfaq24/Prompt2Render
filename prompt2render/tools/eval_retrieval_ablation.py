"""Evaluation tool for Asset Retrieval Ablation Study (Keyword vs Embedding vs Hybrid).

Run:
    python -m prompt2render.tools.eval_retrieval_ablation
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.assets.loader import load_catalog
from prompt2render.assets.embeddings import SparseSemanticVectorizer
from prompt2render.harness.plugins.retriever_asset_rag import match_assets

# Standard pedagogical evaluation benchmark queries with ground truth target asset IDs
BENCHMARK_DATASET = [
    {
        "query": "The CPU pulls data from cache into registers",
        "targets": {"cpu_core", "memory_bank", "register_file"},
    },
    {
        "query": "Arithmetic logic unit adds two 32-bit operands from the accumulator",
        "targets": {"alu_unit", "register_file"},
    },
    {
        "query": "Signals travel across the system interconnect to address RAM",
        "targets": {"bus_line", "memory_bank"},
    },
    {
        "query": "Recursive binary search tree node traversal visiting left and right children",
        "targets": {"binary_tree"},
    },
    {
        "query": "2D Cartesian coordinate plane plotting activation curve functions",
        "targets": {"coordinate_grid"},
    },
    {
        "query": "Microprocessor instruction cycle decode step reading opcode",
        "targets": {"cpu_core", "register_file"},
    },
]


def evaluate_mode(
    mode: str,
    catalog: dict,
    vectorizer: SparseSemanticVectorizer,
    top_k: int = 3,
) -> dict[str, float]:
    total_p1 = 0.0
    total_p_k = 0.0
    total_r_k = 0.0
    total_mrr = 0.0
    start_time = time.perf_counter()

    for item in BENCHMARK_DATASET:
        query = item["query"]
        targets = set(item["targets"])

        results = match_assets(
            query,
            catalog,
            max_matches=top_k,
            mode=mode,
            vectorizer=vectorizer,
        )
        pred_ids = [a.id for a in results]

        # Precision@1
        p1 = 1.0 if (pred_ids and pred_ids[0] in targets) else 0.0
        total_p1 += p1

        # Precision@K
        hits = sum(1 for pid in pred_ids if pid in targets)
        p_k = hits / float(len(pred_ids)) if pred_ids else 0.0
        total_p_k += p_k

        # Recall@K
        r_k = hits / float(len(targets)) if targets else 0.0
        total_r_k += r_k

        # MRR
        rr = 0.0
        for rank, pid in enumerate(pred_ids, start=1):
            if pid in targets:
                rr = 1.0 / rank
                break
        total_mrr += rr

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0 / len(BENCHMARK_DATASET)
    n = float(len(BENCHMARK_DATASET))

    return {
        "mode": mode,
        "P@1": total_p1 / n,
        f"P@{top_k}": total_p_k / n,
        f"R@{top_k}": total_r_k / n,
        "MRR": total_mrr / n,
        "latency_ms": elapsed_ms,
    }


def main():
    catalog = load_catalog()
    vectorizer = SparseSemanticVectorizer(catalog)

    print("=" * 70)
    print("PROMPT2RENDER ASSET RETRIEVAL ABLATION BENCHMARK")
    print("=" * 70)

    modes = ["keyword", "embedding", "hybrid"]
    rows = []
    for m in modes:
        res = evaluate_mode(m, catalog, vectorizer, top_k=3)
        rows.append(res)

    print(f"{'Retrieval Mode':<15} | {'P@1':<8} | {'P@3':<8} | {'R@3':<8} | {'MRR':<8} | {'Latency (ms)':<12}")
    print("-" * 70)
    for r in rows:
        print(f"{r['mode'].upper():<15} | {r['P@1']:.3f}    | {r['P@3']:.3f}    | {r['R@3']:.3f}    | {r['MRR']:.3f}    | {r['latency_ms']:.3f} ms")
    print("=" * 70)


if __name__ == "__main__":
    main()
