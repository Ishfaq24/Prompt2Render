"""No retrieval/RAG of any kind exists anywhere in prompt2render (confirmed by grepping prompt2render/ for
embedding|vector.?store|retrieval|RAG|faiss|chroma|pinecone|similarity_search — no real matches,
docs/MIGRATION_INVENTORY.md §3). True no-op. Disabled by default in config.yaml; its spec'd "soft
gate, fall back to generating without retrieved context" is trivially satisfied since there is
never any retrieved context to fall back from.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin


class RetrieverManimRagPlugin(Plugin):
    name = "retriever_manim_rag"

    def declare_dependencies(self) -> list[str]:
        return []

    def declare_effects(self) -> list[str]:
        return []

    def run(self, context: SceneContext) -> SceneContext:
        return context

    def _default_gate(self) -> bool:
        return False
