"""Asset catalog retriever and idempotent staging plugin for Prompt2Render.

This plugin bridges the asset catalog to the scene generation pipeline:
1. Matches scene narration/animation briefs against the sharded asset catalog.
2. Gracefully falls back to an empty match list if no asset matches (no blocking).
3. Safely and idempotently stages matching asset files to `<project_dir>/build/assets/`.
4. Injects typed asset metadata and prompt hints into `context.retrieval_context`.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...plugin import Plugin
from ....assets.loader import AssetDefinition, load_catalog


def _normalize(text: str) -> str:
    """Normalize text for keyword matching: lowercase, strip punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_term(haystack_norm: str, term: str) -> bool:
    """Check if normalized term matches within normalized text with word boundary semantics."""
    term_norm = _normalize(term)
    if not term_norm:
        return False
    pattern = r"(?:\b|_)" + re.escape(term_norm).replace(r"\ ", r"\s+") + r"(?:\b|_)"
    return re.search(pattern, haystack_norm) is not None


_STAGING_LOCK = threading.Lock()


def stage_asset_safe(src_path: Path, dest_dir: Path) -> Path:
    """Idempotently and atomically copy an asset to the target destination directory.

    Safe under multi-threaded scene generation across Windows, Linux, and macOS.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / src_path.name

    if dest_file.is_file():
        try:
            if dest_file.stat().st_size == src_path.stat().st_size:
                return dest_file
        except OSError:
            pass

    with _STAGING_LOCK:
        if dest_file.is_file():
            try:
                if dest_file.stat().st_size == src_path.stat().st_size:
                    return dest_file
            except OSError:
                pass
        tmp_file = dest_dir / f".tmp_{os.getpid()}_{threading.get_ident()}_{src_path.name}"
        shutil.copy2(src_path, tmp_file)
        try:
            tmp_file.replace(dest_file)
        except OSError:
            if dest_file.is_file():
                try:
                    tmp_file.unlink(missing_ok=True)
                except OSError:
                    pass
        return dest_file


def match_assets(
    text: str,
    catalog: dict[str, AssetDefinition],
    max_matches: int = 3,
    mode: str = "hybrid",
    vectorizer: Any = None,
    min_score: float = 0.0,
) -> list[AssetDefinition]:
    """Find matching catalog assets for given text using keyword, embedding, or hybrid matching."""
    norm_text = _normalize(text)
    if not norm_text:
        return []

    if mode == "embedding":
        if vectorizer is None:
            from ....assets.embeddings import SparseSemanticVectorizer
            vectorizer = SparseSemanticVectorizer(catalog)
        hits = vectorizer.search(text, top_k=max_matches)
        return [catalog[aid] for aid, _ in hits if aid in catalog]

    # Keyword scoring
    scored_matches: dict[str, float] = {}

    for asset in catalog.values():
        score = 0.0
        if _contains_term(norm_text, asset.id):
            score += 20.0
        if _contains_term(norm_text, asset.name):
            score += 15.0
        for kw in asset.keywords:
            if _contains_term(norm_text, kw):
                score += 10.0
        if score > 0:
            scored_matches[asset.id] = score

    if mode == "hybrid":
        if vectorizer is None:
            from ....assets.embeddings import SparseSemanticVectorizer
            vectorizer = SparseSemanticVectorizer(catalog)
        emb_hits = vectorizer.search(text, top_k=max_matches * 2)
        for aid, sim in emb_hits:
            scored_matches[aid] = scored_matches.get(aid, 0.0) + (sim * 15.0)

    ranked = [(aid, sc) for aid, sc in sorted(scored_matches.items(), key=lambda item: item[1], reverse=True) if sc >= min_score]
    return [catalog[aid] for aid, _ in ranked[:max_matches] if aid in catalog]


def format_asset_hint(asset: AssetDefinition, staged_name: str | None = None) -> str:
    """Create concise generation hint for Coder/Generator prompts."""
    if asset.type == "svg" and staged_name:
        return f"Asset '{asset.id}': vector icon available at 'assets/{staged_name}' for k.draw_asset or SVGMobject."
    elif asset.type == "manim_component" and asset.module and asset.class_name:
        return f"Mobject '{asset.class_name}': from {asset.module} import {asset.class_name} (params: {list(asset.parameter_schema.get('properties', {}).keys())})"
    return f"Asset '{asset.id}': {asset.description}"


class RetrieverAssetRagPlugin(Plugin):
    """Deterministic asset catalog retriever and stage-gated asset stager."""

    name = "retriever_asset_rag"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["retrieval_context"]

    def run(self, context: SceneContext) -> SceneContext:
        catalog_dir = self.config.get("catalog_dir")
        custom_path = Path(catalog_dir) if catalog_dir else None
        catalog = load_catalog(custom_path)

        max_matches = int(self.config.get("max_matches_per_scene", 3))
        mode = str(self.config.get("retrieval_mode", "hybrid")).lower()

        project_dir = context.project_dir
        dest_assets_dir = (project_dir / "build" / "assets") if project_dir else None

        from ....assets.embeddings import SparseSemanticVectorizer
        vectorizer = SparseSemanticVectorizer(catalog)

        # Ensure retrieval_context exists on context
        if not hasattr(context, "retrieval_context") or context.retrieval_context is None:
            context.retrieval_context = {}

        for entry in context.scene_plan:
            stem = str(entry.stem)
            anim_text = getattr(entry, "anim", "") or ""
            narr_text = getattr(entry, "narration_text", "") or ""
            combined_text = f"{anim_text}\n{narr_text}"

            matched = match_assets(
                combined_text,
                catalog,
                max_matches=max_matches,
                mode=mode,
                vectorizer=vectorizer,
            )
            asset_records: list[dict[str, Any]] = []

            for asset in matched:
                staged_name: str | None = None
                if asset.type == "svg" and dest_assets_dir:
                    src_file = asset.resolved_file_path(custom_path)
                    if src_file and src_file.is_file():
                        staged_path = stage_asset_safe(src_file, dest_assets_dir)
                        staged_name = staged_path.name

                record = {
                    "id": asset.id,
                    "name": asset.name,
                    "category": asset.category,
                    "type": asset.type,
                    "backends": list(asset.backends),
                    "staged_path": f"assets/{staged_name}" if staged_name else None,
                    "module": asset.module,
                    "class_name": asset.class_name,
                    "parameter_schema": asset.parameter_schema,
                    "description": asset.description,
                    "hint": format_asset_hint(asset, staged_name),
                }
                asset_records.append(record)

            # Merge or set into retrieval_context
            existing = context.retrieval_context.get(stem, [])
            # Append asset records avoiding duplicates
            existing_ids = {r.get("id") for r in existing if isinstance(r, dict)}
            for r in asset_records:
                if r["id"] not in existing_ids:
                    existing.append(r)
            context.retrieval_context[stem] = existing

        return context

    def _default_gate(self) -> bool:
        return False
