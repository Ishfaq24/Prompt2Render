"""Tests for RetrieverAssetRagPlugin and idempotent asset staging."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render.harness.context import SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.retriever_asset_rag import (
    RetrieverAssetRagPlugin,
    match_assets,
    stage_asset_safe,
)
from prompt2render.assets.loader import load_catalog


def test_match_assets_keywords():
    """Verify that keyword matching extracts correct asset definitions."""
    catalog = load_catalog()
    matches = match_assets("The CPU processor fetches instructions from memory cache", catalog)
    matched_ids = [m.id for m in matches]
    assert "cpu_core" in matched_ids
    assert "memory_bank" in matched_ids


def test_graceful_degradation_on_zero_match():
    """Ensure zero-match queries degrade gracefully to an empty list without error."""
    catalog = load_catalog()
    matches = match_assets("A completely unrelated topic about ancient roman architecture and pottery", catalog)
    assert matches == []


def test_idempotent_asset_staging(tmp_path: Path):
    """Test that stage_asset_safe is idempotent and copies file cleanly."""
    src_file = tmp_path / "test_icon.svg"
    src_file.write_text("<svg><rect/></svg>", encoding="utf-8")

    dest_dir = tmp_path / "build" / "assets"
    staged1 = stage_asset_safe(src_file, dest_dir)
    assert staged1.is_file()
    assert staged1.read_text(encoding="utf-8") == "<svg><rect/></svg>"

    # Second call should be idempotent
    staged2 = stage_asset_safe(src_file, dest_dir)
    assert staged1 == staged2


def test_plugin_run_populates_retrieval_context(tmp_path: Path):
    """Verify that plugin runs across scene plan and populates SceneContext.retrieval_context."""
    plugin = RetrieverAssetRagPlugin(config={})
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [
        ScenePlanEntry(
            index=1,
            stem="01",
            title="CPU Architecture",
            anim="Diagram of central processing unit and ALU logic",
            narration_text="The CPU coordinates arithmetic operations in the ALU.",
        ),
        ScenePlanEntry(
            index=2,
            stem="02",
            title="Unrelated Concept",
            anim="Abstract geometric visual",
            narration_text="A philosophical intro without hardware.",
        ),
    ]

    ctx = plugin.run(ctx)

    assert "01" in ctx.retrieval_context
    matched_01 = ctx.retrieval_context["01"]
    matched_ids_01 = [m["id"] for m in matched_01]
    assert "cpu_core" in matched_ids_01 or "alu_unit" in matched_ids_01

    # Check that SVG asset was staged to build/assets
    staged_assets = list((tmp_path / "build" / "assets").glob("*.svg"))
    assert len(staged_assets) > 0

    # Check graceful degradation for scene 02
    assert "02" in ctx.retrieval_context
    assert ctx.retrieval_context["02"] == []
