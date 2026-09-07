"""Unit tests for Mayer-Sweller Cognitive Signaling & Attention Optimizer."""

from __future__ import annotations

from prompt2render.cognitive_signaling import (
    extract_key_concepts,
    resolve_visual_referents,
    build_signaling_cues,
    calculate_cognitive_load_metrics,
)


def test_extract_key_concepts():
    text = (
        "The DNS Resolver contacts the Root Server and transmits the Public Key "
        "to verify the cryptographic signature."
    )
    concepts = extract_key_concepts(text)

    # Must extract compound entities and acronyms
    assert any("DNS Resolver" in c or "dns resolver" in c.lower() for c in concepts)
    assert any("Root Server" in c or "root server" in c.lower() for c in concepts)
    assert any("Public Key" in c or "public key" in c.lower() for c in concepts)
    assert any("DNS" in c for c in concepts)


def test_resolve_visual_referents():
    concepts = ["DNS Resolver", "Public Key", "Database"]
    visual_elements = ["resolver_node", "public_key_badge", "main_database"]

    referent_map = resolve_visual_referents(concepts, visual_elements)
    assert "DNS Resolver" in referent_map
    assert referent_map["DNS Resolver"] == "resolver_node"
    assert referent_map["Public Key"] == "public_key_badge"
    assert referent_map["Database"] == "main_database"


def test_build_signaling_cues_with_lead_time():
    sentences_alignment = [
        {
            "i": 0,
            "text": "The resolver queries the server.",
            "words": [
                {"w": "The", "s": 0.0, "e": 0.2},
                {"w": "resolver", "s": 0.50, "e": 0.90},
                {"w": "queries", "s": 0.95, "e": 1.30},
                {"w": "the", "s": 1.35, "e": 1.45},
                {"w": "server", "s": 1.50, "e": 1.90},
            ],
        }
    ]
    referent_map = {
        "resolver": "resolver_node",
        "server": "server_box",
    }

    # With lead_s = 0.150s:
    # "resolver" starts at 0.50s -> cue timestamp should be 0.35s
    # "server" starts at 1.50s -> cue timestamp should be 1.35s
    cues = build_signaling_cues(sentences_alignment, referent_map, lead_s=0.150)
    assert len(cues) == 2
    assert cues[0]["target_element"] == "resolver_node"
    assert abs(cues[0]["timestamp_s"] - 0.35) < 0.001
    assert cues[1]["target_element"] == "server_box"
    assert abs(cues[1]["timestamp_s"] - 1.35) < 0.001


def test_calculate_cognitive_load_metrics():
    narration_words = ["The", "algorithm", "traverses", "the", "binary", "tree", "node", "by", "node", "efficiently"] # 10 words
    on_screen_texts = ["Binary Tree", "O(n)"] # 3 words: "Binary", "Tree", "O(n)"
    signaling_cues = [{"timestamp_s": 0.5}, {"timestamp_s": 1.5}]

    metrics = calculate_cognitive_load_metrics(
        narration_words=narration_words,
        on_screen_texts=on_screen_texts,
        signaling_cues=signaling_cues,
        total_duration_s=5.0,
    )

    # Redundancy index: 3 / 10 = 0.30 <= 0.40 (safe)
    assert metrics["redundancy_index"] == 0.30
    assert metrics["is_redundancy_safe"] == 1.0
    # Signaling density: (2 cues / 5s) * 10 = 4.0 cues / 10s
    assert metrics["signaling_density"] == 4.0
