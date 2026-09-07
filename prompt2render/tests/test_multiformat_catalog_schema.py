"""Tests for Multi-Format Asset Catalog Schema (Lottie JSON, SVGs, Manim Mobjects)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from prompt2render.assets.loader import load_catalog, DEFAULT_ASSETS_DIR


def test_load_multiformat_catalog():
    """Verify that catalog loads multi-format assets including Lottie and SVGs."""
    catalog = load_catalog()
    assert "packet_stream" in catalog
    assert "server_rack_pulse" in catalog
    assert "cpu_core" in catalog
    assert "binary_tree" in catalog


def test_lottie_asset_definitions():
    """Verify Lottie asset fields, durations, and file presence."""
    catalog = load_catalog()
    lottie_assets = [a for a in catalog.values() if a.type == "lottie"]
    assert len(lottie_assets) >= 2

    for asset in lottie_assets:
        assert asset.duration_seconds > 0.0
        assert asset.fps >= 30
        assert asset.license
        assert asset.source_url
        assert len(asset.keywords) > 0

        # Verify on-disk file existence
        file_path = asset.resolved_file_path(DEFAULT_ASSETS_DIR)
        assert file_path is not None
        assert file_path.is_file()

        # Verify valid Lottie JSON syntax and schema
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert "v" in content, f"{file_path} missing Lottie version 'v'"
        assert "layers" in content, f"{file_path} missing 'layers'"
        assert "fr" in content, f"{file_path} missing 'fr'"
        assert "ip" in content and "op" in content
