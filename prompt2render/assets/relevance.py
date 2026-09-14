"""Semantic relevance gating and cross-domain contamination validation for visual assets.

Guarantees that assets retrieved from external providers (Pixabay, Unsplash, Pexels)
genuinely correspond to the scene's conceptual domain before staging or embedding.
"""

from __future__ import annotations

import re
from typing import Any

from .providers.base import AssetHit

# Common English stop words
_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "scene", "show", "diagram",
    "macro", "real", "high", "resolution", "into", "from", "over", "each",
    "more", "when", "then", "under", "both", "such", "down", "upon", "about",
    "after", "before", "while", "during", "which", "where", "what", "their",
    "there", "here", "have", "been", "will", "would", "could", "should", "some",
    "image", "photo", "picture", "stock", "view", "close", "look", "using",
})

# Domain indicators to classify scene context
_DOMAIN_PATTERNS = {
    "medical_biology": re.compile(
        r"\b(heart|cardiac|myocardium|coronary|artery|arterial|vascular|blood|lumen|"
        r"plaque|stenosis|atherosclerosis|thrombus|thrombosis|infarction|ischemia|"
        r"vein|capillary|endothelial|endothelium|macrophage|leukocyte|cell|cells|"
        r"tissue|lung|lungs|pulmonary|alveoli|bronchi|trachea|pneumonia|infection|"
        r"bacteria|virus|pathogen|immune|immunology|antibody|ecg|ekg|anatomy|"
        r"organ|histology|medical|disease|patient|clinical|stethoscope)\b",
        re.IGNORECASE,
    ),
    "computing_it": re.compile(
        r"\b(computer|server|database|network|packet|routing|switch|router|dns|"
        r"ethernet|ip|cables|datacenter|tcp|udp|http|ssl|tls|ssh|encryption|"
        r"cpu|processor|memory|ram|cache|register|hardware|software|code|"
        r"algorithm|array|binary|tree|graph|sorting|compiler)\b",
        re.IGNORECASE,
    ),
}

# Negative tags that indicate cross-domain contamination
_CONTAMINATION_TAGS = {
    "medical_biology": frozenset({
        "server", "servers", "cable", "cables", "country cable", "ethernet",
        "datacenter", "data center", "laptop", "motherboard", "microchip",
        "circuit board", "patch panel", "switch", "router", "plug", "lan",
        "fruit", "kiwi", "vegetable", "kitchen", "furniture", "automobile",
        "car", "traffic", "palace", "fashion",
    }),
    "computing_it": frozenset({
        "stethoscope", "surgery", "surgeon", "hospital bed", "pills",
        "medication", "syringe", "injection", "stethoscope", "bandage",
    }),
}


def _normalize_word(w: str) -> str:
    """Normalize word to base form (simple suffix stemming)."""
    w = w.lower().strip()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _extract_content_words(text: str) -> set[str]:
    """Extract lowercase alpha-numeric content words (3+ chars) excluding stop words."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    content = set()
    for w in words:
        if w not in _STOP_WORDS:
            content.add(w)
            content.add(_normalize_word(w))
    return content


def detect_domain(scene_text: str) -> str | None:
    """Detect primary conceptual domain from scene narrative / animation brief."""
    med_matches = len(_DOMAIN_PATTERNS["medical_biology"].findall(scene_text))
    it_matches = len(_DOMAIN_PATTERNS["computing_it"].findall(scene_text))

    # If medical terms dominate (e.g. vascular network in biology)
    if med_matches > 0 and med_matches >= it_matches:
        return "medical_biology"
    elif it_matches > 0:
        return "computing_it"
    return None


def is_asset_relevant(
    hit: AssetHit,
    scene_text: str,
    domain: str | None = None,
    min_overlap: int = 1,
) -> tuple[bool, float, str]:
    """Validate whether an external AssetHit is semantically relevant to the scene.

    Args:
        hit: Discovered AssetHit from an external provider (e.g. Pixabay).
        scene_text: Combined scene animation brief and narration text.
        domain: Optional override for the scene domain.
        min_overlap: Minimum number of shared content keywords required.

    Returns:
        tuple of (is_relevant: bool, score: float, reason: str)
    """
    if not domain:
        domain = detect_domain(scene_text)

    hit_tags_lower = {t.lower().strip() for t in hit.tags}
    hit_title_words = _extract_content_words(hit.title)
    all_hit_words = set(hit_tags_lower) | hit_title_words
    # Also break multi-word tags into individual normalized words
    for t in hit_tags_lower:
        for w in re.findall(r"\b[a-z]{3,}\b", t):
            all_hit_words.add(w)
            all_hit_words.add(_normalize_word(w))

    # 1. Check for cross-domain contamination
    if domain and domain in _CONTAMINATION_TAGS:
        bad_tags = _CONTAMINATION_TAGS[domain]
        found_contaminants = bad_tags.intersection(all_hit_words)
        if found_contaminants:
            return (
                False,
                0.0,
                f"Cross-domain contamination detected: found {found_contaminants} in asset for {domain} scene.",
            )

    # 2. Extract scene content keywords
    scene_words = _extract_content_words(scene_text)
    if not scene_words:
        return False, 0.0, "Empty scene content keywords."

    # 3. Calculate keyword / tag overlap (including stem & compound subword matches)
    overlap = scene_words.intersection(all_hit_words)

    # If no direct token intersection, check compound subword matches
    if not overlap:
        for sw in scene_words:
            if len(sw) >= 4:
                for hw in all_hit_words:
                    if len(hw) >= 4 and (sw in hw or hw in sw):
                        overlap.add(f"{sw}~{hw}")

    overlap_count = len(overlap)

    if overlap_count < min_overlap:
        return (
            False,
            0.0,
            f"Insufficient semantic overlap: {overlap_count} matches (minimum {min_overlap} required).",
        )

    # Calculate confidence score based on overlap and specific domain alignment
    base_score = min(1.0, overlap_count / max(3, len(scene_words) * 0.25))
    if domain == "medical_biology":
        # Check if any strong medical terms overlapped
        strong_med_terms = {"heart", "cardiac", "artery", "arterial", "blood", "lumen", "plaque", "thrombus", "lungs", "cells"}
        if any(sm in str(overlap) for sm in strong_med_terms):
            base_score = min(1.0, base_score + 0.3)

    return True, round(base_score, 2), f"Relevant with {overlap_count} overlapping terms: {sorted(overlap)}."
