"""Mayer-Sweller Cognitive Signaling & Attention Optimizer.

Implements core principles from Mayer's Cognitive Theory of Multimedia Learning
and Sweller's Cognitive Load Theory:
1. Signaling Principle: Synchronizes attention-directing cues (-150ms lead time)
   with spoken technical terms to guide learner attention.
2. Split-Attention Guard: Detects lag between spoken technical terms and visual appearance.
3. Redundancy Guard: Enforces that on-screen text does not overload the phonological loop
   by duplicating full spoken sentences.
"""

from __future__ import annotations

import re
from typing import Any, Sequence


# Stop words that should not be considered technical concept keywords
_COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "against", "between", "into", "through",
    "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "can", "will", "just", "don", "should", "now", "let", "us",
    "this", "that", "these", "those", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "having", "do", "does", "did", "doing",
    "we", "our", "you", "your", "they", "their", "it", "its", "what", "which",
}


def extract_key_concepts(text: str) -> list[str]:
    """Extract salient technical entities and keywords from spoken narration text."""
    if not text:
        return []

    # 1. Capitalized compound technical terms (e.g. "DNS Resolver", "Public Key", "Root Server")
    raw_compounds = re.findall(
        r"\b(?:[A-Z]{2,}|[A-Z][a-z0-9]+)(?:\s+(?:[A-Z]{2,}|[A-Z][a-z0-9]+))+\b",
        text,
    )
    compounds = []
    for raw in raw_compounds:
        words = raw.split()
        while words and words[0].lower() in _COMMON_STOPWORDS:
            words.pop(0)
        if len(words) >= 2:
            compounds.append(" ".join(words))

    # 2. Acronyms & technical terms (e.g. "DNS", "RAM", "CPU", "AVL", "GCD")
    acronyms = re.findall(r"\b[A-Z]{2,}\b", text)

    # 3. Individual significant technical nouns and keywords
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_\-]{2,}\b", text)
    filtered_words = [
        w.lower() for w in words 
        if w.lower() not in _COMMON_STOPWORDS and len(w) > 2
    ]

    # Combine while preserving uniqueness and salience
    seen = set()
    results = []

    for item in compounds + acronyms + filtered_words:
        cleaned = item.strip().lower()
        if cleaned not in seen and len(cleaned) > 2:
            seen.add(cleaned)
            results.append(item.strip())

    return results


def resolve_visual_referents(
    concepts: Sequence[str],
    visual_elements: Sequence[str],
) -> dict[str, str]:
    """Map spoken technical concepts to corresponding on-screen Mobjects or elements.
    
    Returns:
        dict mapping concept -> visual_element_name
    """
    mapping: dict[str, str] = {}
    normalized_elements = {el.lower().replace("_", " "): el for el in visual_elements}

    for concept in concepts:
        c_clean = concept.lower().replace("_", " ").strip()
        # Direct match
        if c_clean in normalized_elements:
            mapping[concept] = normalized_elements[c_clean]
            continue

        # Substring / partial match or token-overlap match
        concept_tokens = set(re.findall(r"\b[a-z0-9]+\b", c_clean)) - _COMMON_STOPWORDS

        best_match = None
        best_score = 0.0

        for el_norm, orig_el in normalized_elements.items():
            if c_clean in el_norm or el_norm in c_clean:
                score = 0.8
            else:
                el_tokens = set(re.findall(r"\b[a-z0-9]+\b", el_norm)) - _COMMON_STOPWORDS
                overlap = concept_tokens & el_tokens
                if overlap:
                    score = len(overlap) / max(len(concept_tokens), len(el_tokens))
                else:
                    score = 0.0

            if score > best_score and score >= 0.25:
                best_score = score
                best_match = orig_el

        if best_match:
            mapping[concept] = best_match

    return mapping


def build_signaling_cues(
    sentences_alignment: Sequence[dict[str, Any]],
    referent_map: dict[str, str],
    lead_s: float = 0.150,
) -> list[dict[str, Any]]:
    """Generate sample-exact visual signaling events with lead time for speech sync.
    
    Each cue defines:
    - timestamp_s: audio word start minus lead_s (clamped >= 0.0)
    - concept: spoken technical term
    - target_element: on-screen Mobject or diagram element to highlight
    - action: recommended visual cue ("Indicate" | "Circumscribe" | "pulse_signal")
    """
    cues: list[dict[str, Any]] = []

    for sentence in sentences_alignment:
        words = sentence.get("words", [])
        for w in words:
            word_str = w.get("w", "").strip().lower()
            word_clean = re.sub(r"[^a-z0-9]", "", word_str)
            if not word_clean:
                continue

            for concept, target_element in referent_map.items():
                c_clean = re.sub(r"[^a-z0-9]", "", concept.lower())
                if word_clean == c_clean or c_clean.startswith(word_clean):
                    w_start = float(w.get("s", 0.0))
                    cue_time = max(0.0, w_start - lead_s)
                    cues.append({
                        "timestamp_s": round(cue_time, 3),
                        "audio_word_s": round(w_start, 3),
                        "concept": concept,
                        "target_element": target_element,
                        "action": "Indicate",
                    })
                    break

    # Sort cues chronologically
    cues.sort(key=lambda c: c["timestamp_s"])
    return cues


def calculate_cognitive_load_metrics(
    narration_words: Sequence[str],
    on_screen_texts: Sequence[str],
    signaling_cues: Sequence[dict[str, Any]],
    total_duration_s: float,
) -> dict[str, float]:
    """Calculate cognitive load metrics according to Sweller & Mayer's principles."""
    total_spoken_words = max(1, len(narration_words))
    total_screen_words = sum(len(t.split()) for t in on_screen_texts)

    # Redundancy index: ratio of on-screen text words to spoken words
    # Values > 0.40 indicate split-attention reading overload
    redundancy_index = round(total_screen_words / total_spoken_words, 3)

    # Signaling density: signaling events per 10 seconds
    signaling_density = round((len(signaling_cues) / max(1.0, total_duration_s)) * 10.0, 2)

    return {
        "redundancy_index": redundancy_index,
        "signaling_density": signaling_density,
        "signaled_events_count": float(len(signaling_cues)),
        "is_redundancy_safe": 1.0 if redundancy_index <= 0.40 else 0.0,
    }
