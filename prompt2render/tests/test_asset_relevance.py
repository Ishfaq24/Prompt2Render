"""Unit tests for asset relevance gating, domain collision prevention, and priority inversion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import pytest

from prompt2render.assets.providers.base import AssetHit
from prompt2render.assets.relevance import (
    detect_domain,
    is_asset_relevant,
)
from prompt2render.harness.plugins.retriever_external_asset import _extract_asset_queries
from prompt2render.scenes import stage_external_assets_for_section


def test_vascular_network_does_not_trigger_computer_cables():
    """Verify that 'vascular network' or 'arterial network' does NOT trigger IT server cables."""
    anim = "Macro cardiac anatomy showing coronary arteries branching over the myocardium"
    narration = "The human heart beats over 100,000 times each day, powered by a dedicated vascular network."

    queries = _extract_asset_queries(anim, narration)
    assert len(queries) >= 1

    query_strings = [q["query"].lower() for q in queries]
    # None of the queries should be computer networking or cables!
    assert not any("server" in q or "cable" in q or "networking" in q for q in query_strings)
    # It should match heart/cardiac anatomy
    assert any("heart" in q or "artery" in q for q in query_strings)


def test_cross_domain_contamination_rejection():
    """Verify that IT server/cable assets are strictly rejected for medical/biology scenes."""
    scene_text = (
        "The human heart beats over 100,000 times daily, nourished by coronary arteries. "
        "Lipids penetrate the endothelial barrier forming an atherosclerotic plaque."
    )

    # 1. Contaminated IT cable hit (like pixabay_1626665 or pixabay_5033077)
    bad_hit = AssetHit(
        id="pixabay_5033077",
        provider="pixabay",
        url="https://pixabay.com/test.jpg",
        author="ugoxuqu",
        author_url="",
        license="Pixabay License",
        license_url="",
        title="Pixabay Image 5033077 (connection, cable, country cable)",
        tags=("connection", "cable", "country cable", "datacenter", "ethernet", "server"),
    )

    is_rel, score, reason = is_asset_relevant(bad_hit, scene_text)
    assert not is_rel
    assert "Cross-domain contamination detected" in reason

    # 2. Authentic medical hit
    good_hit = AssetHit(
        id="pixabay_999999",
        provider="pixabay",
        url="https://pixabay.com/test2.jpg",
        author="medical_artist",
        author_url="",
        license="Pixabay License",
        license_url="",
        title="Human Heart Anatomy and Coronary Artery Illustration",
        tags=("heart", "cardiac", "artery", "coronary", "anatomy", "medical"),
    )

    is_rel_good, score_good, reason_good = is_asset_relevant(good_hit, scene_text)
    assert is_rel_good
    assert score_good >= 0.5
    assert "heart" in reason_good or "artery" in reason_good


def test_domain_detection():
    """Verify accurate domain classification."""
    med_text = "Macrophage cells engulf oxidized LDL forming plaque in the coronary artery."
    it_text = "DNS servers resolve domain names across packet routing networks."

    assert detect_domain(med_text) == "medical_biology"
    assert detect_domain(it_text) == "computing_it"


def test_stage_assets_priority_inversion(tmp_path: Path):
    """Verify stage_external_assets_for_section selects curated catalog vector diagrams for heart scenes."""
    proj_dir = tmp_path / "heart_test"
    proj_dir.mkdir(parents=True)

    sec = SimpleNamespace(
        stem="01",
        anim="Macro cardiac anatomy showing the left anterior descending coronary artery branching over the myocardium",
        narration="The human heart beats over one hundred thousand times each day, powered by a dedicated vascular network.",
        assets=True,
    )

    mat_hint, manim_hint = stage_external_assets_for_section(proj_dir, sec)

    # Must find a curated vector asset (heart_anatomy.svg or coronary_artery.svg)
    assert "heart_anatomy.svg" in manim_hint or "coronary_artery.svg" in manim_hint
    assert "SVGMobject" in manim_hint
    # Must NOT contain server cables!
    assert "server" not in manim_hint.lower()
    assert "cable" not in manim_hint.lower()

    # Staged file must exist in build/assets
    staged_assets = list((proj_dir / "build" / "assets").glob("*.svg"))
    assert len(staged_assets) >= 1
    assert any("heart" in f.name or "coronary" in f.name for f in staged_assets)
