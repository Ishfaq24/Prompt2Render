"""Tests for Asset Catalog schema integrity and provenance."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from prompt2render.assets.loader import load_catalog, DEFAULT_ASSETS_DIR


def test_load_catalog():
    """Verify that catalog index and all sharded manifests load cleanly."""
    catalog = load_catalog()
    assert len(catalog) >= 5
    assert "cpu_core" in catalog
    assert "memory_bank" in catalog
    assert "register_file" in catalog
    assert "alu_unit" in catalog
    assert "bus_line" in catalog


def test_provenance_and_licensing():
    """Ensure every asset has license, source_url, author, and version/category."""
    catalog = load_catalog()
    for asset_id, asset in catalog.items():
        assert asset.license, f"Asset {asset_id} missing license"
        assert asset.source_url, f"Asset {asset_id} missing source_url"
        assert asset.author, f"Asset {asset_id} missing author"
        assert len(asset.keywords) > 0, f"Asset {asset_id} missing keywords"
        assert asset.category, f"Asset {asset_id} missing category"


def test_svg_asset_files_exist():
    """Verify that every SVG asset file declared exists on disk."""
    catalog = load_catalog()
    for asset_id, asset in catalog.items():
        if asset.type == "svg":
            resolved = asset.resolved_file_path(DEFAULT_ASSETS_DIR)
            assert resolved is not None, f"Asset {asset_id} has no resolved path"
            assert resolved.is_file(), f"Asset {asset_id} file not found: {resolved}"


def test_manim_component_modules_importable():
    """Verify that every declared Manim component module exists and exports class."""
    catalog = load_catalog()
    for asset_id, asset in catalog.items():
        if asset.type == "manim_component":
            assert asset.module, f"Asset {asset_id} missing module"
            assert asset.class_name, f"Asset {asset_id} missing class_name"
            mod = importlib.import_module(asset.module)
            assert hasattr(mod, asset.class_name), f"Module {asset.module} lacks class {asset.class_name}"
