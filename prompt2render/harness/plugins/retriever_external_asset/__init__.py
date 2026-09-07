"""External media asset retriever plugin for Prompt2Render Harness.

Discovers, downloads, conditions, and stages real-world assets from Unsplash,
Pexels, and Pixabay to enhance video realism.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...plugin import Plugin
from ....assets.cache import AssetCache
from ....assets.preprocessor import prepare_scene_asset
from ....assets.providers import (
    AssetHit,
    get_available_providers,
    search_all_providers,
)


def _extract_asset_queries(anim_text: str, narration_text: str) -> list[dict[str, str]]:
    """Derive search queries and visual roles from scene brief and narration."""
    queries: list[dict[str, str]] = []
    combined = f"{anim_text} {narration_text}".lower()

    # Topic-specific visual metaphors checked first for precise scientific relevance
    metaphor_rules = [
        (r"\b(white blood|neutrophil|macrophage|phagocytosis|leukocyte|immune)\b", "blood cells microscope immunology", "card"),
        (r"\b(bacteria|streptococcus|pneumococcal|bacilli|microorganism)\b", "bacteria microscope microbiology", "card"),
        (r"\b(virus|capsid|influenza|coronavirus|virion)\b", "virus microscopic medical", "card"),
        (r"\b(x-ray|ct scan|radiograph|consolidation|opacity|radiology)\b", "lungs xray medical", "card"),
        (r"\b(antibiotic|medicine|oximeter|stethoscope|therapeutics|treatment|recovery)\b", "doctor stethoscope medicine", "card"),
        (r"\b(lung|lungs|pulmonary|alveoli|respiratory|bronchi|trachea)\b", "human lungs anatomy medical", "card"),
        (r"\b(dns|domain name|nameserver)\b", "server network data center", "background"),
        (r"\b(internet|network|packet|routing|switch|router)\b", "computer networking server cables", "background"),
        (r"\b(database|sql|index|query|btree|b-tree)\b", "server storage hard drive digital", "card"),
        (r"\b(security|encryption|ssl|tls|ssh|certificate)\b", "cyber security padlock digital lock", "card"),
        (r"\b(cpu|processor|memory|ram|cache|register)\b", "microchip circuit board motherboard hardware", "card"),
        (r"\b(api|rest|http|client|server architecture)\b", "cloud computing laptop developer", "background"),
    ]

    for pattern, query, role in metaphor_rules:
        if re.search(pattern, combined):
            queries.append({"query": query, "role": role, "type": "photo"})
            if len(queries) >= 2:
                break

    if not queries:
        anim_clean = re.sub(r"^anim:\s*", "", anim_text.strip(), flags=re.IGNORECASE)
        words = [w for w in re.findall(r"\b[a-z]{3,}\b", anim_clean.lower()) if w not in {"the", "and", "for", "with", "this", "that", "scene", "show", "diagram", "macro", "real", "high", "resolution"}]
        if words:
            queries.append({"query": " ".join(words[:3]), "role": "card", "type": "photo"})

    return queries

    return queries


class RetrieverExternalAssetPlugin(Plugin):
    """Discovers and stages external real-world media assets for scenes."""

    name = "retriever_external_asset"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["retrieval_context", "asset_provenance"]

    def run(self, context: SceneContext) -> SceneContext:
        project_dir = context.project_dir
        if not project_dir:
            return context

        build_assets_dir = project_dir / "build" / "assets"
        build_assets_dir.mkdir(parents=True, exist_ok=True)

        cache = AssetCache()
        providers = get_available_providers(allow_mock_fallback=False)
        if not providers:
            # If no API keys are active, allow mock fallback if configured
            allow_mock = bool(self.config.get("allow_mock_fallback", True))
            providers = get_available_providers(allow_mock_fallback=allow_mock)

        if not providers:
            return context

        if not hasattr(context, "retrieval_context") or context.retrieval_context is None:
            context.retrieval_context = {}
        if not hasattr(context, "asset_provenance") or context.asset_provenance is None:
            context.asset_provenance = {}

        max_assets_per_scene = int(self.config.get("max_assets_per_scene", 2))

        for entry in context.scene_plan:
            stem = str(entry.stem)
            anim_text = getattr(entry, "anim", "") or ""
            narr_text = getattr(entry, "narration_text", "") or ""

            derived_queries = _extract_asset_queries(anim_text, narr_text)
            if not derived_queries:
                continue

            scene_hits: list[AssetHit] = []
            for q_info in derived_queries:
                q = q_info["query"]
                asset_type = q_info.get("type", "photo")
                found = search_all_providers(
                    query=q,
                    providers=providers,
                    orientation="landscape",
                    asset_type=asset_type,
                    limit_per_provider=2,
                )
                for f in found:
                    if f.id not in {h.id for h in scene_hits}:
                        scene_hits.append(f)
                    if len(scene_hits) >= max_assets_per_scene:
                        break
                if len(scene_hits) >= max_assets_per_scene:
                    break

            for hit in scene_hits:
                role = derived_queries[0].get("role", "background")
                try:
                    # 1. Fetch raw asset to cache
                    prov = next((p for p in providers if p.name == hit.provider), providers[0])
                    cached_raw = cache.fetch_or_download(hit, prov)

                    # 2. Condition/process asset
                    staged_filename = f"{stem}_{hit.provider}_{hit.id.split('_', 1)[-1]}.png"
                    staged_path = build_assets_dir / staged_filename
                    prepare_scene_asset(
                        cached_raw,
                        staged_path,
                        role=role,
                        target_width=1920 if role == "background" else 960,
                        target_height=1080 if role == "background" else 540,
                    )

                    # 3. Register hint in retrieval_context
                    rel_asset_path = f"assets/{staged_filename}"
                    hint_text = (
                        f"External Asset '{hit.id}': {hit.title} by {hit.author} ({hit.provider.title()}). "
                        f"Staged at '{rel_asset_path}'. Role: {role.upper()}."
                    )

                    record = {
                        "id": hit.id,
                        "name": hit.title or hit.id,
                        "provider": hit.provider,
                        "role": role,
                        "staged_path": rel_asset_path,
                        "hint": hint_text,
                        "author": hit.author,
                        "license": hit.license,
                    }

                    existing = context.retrieval_context.setdefault(stem, [])
                    if not any(isinstance(r, dict) and r.get("id") == hit.id for r in existing):
                        existing.append(record)

                    # 4. Record provenance
                    prov_entry = {
                        "id": hit.id,
                        "provider": hit.provider,
                        "title": hit.title,
                        "author": hit.author,
                        "author_url": hit.author_url,
                        "source_url": hit.url,
                        "license": hit.license,
                        "license_url": hit.license_url,
                        "staged_path": str(staged_path),
                        "role": role,
                    }
                    context.asset_provenance.setdefault(stem, []).append(prov_entry)

                except Exception:
                    continue

        return context

    def _default_gate(self) -> bool:
        return False
