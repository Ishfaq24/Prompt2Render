"""Loader and schema validator for Prompt2Render Asset Catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_ASSETS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AssetDefinition:
    """Validated in-memory asset definition."""

    id: str
    name: str
    category: str
    type: str  # "svg", "manim_component", "scenekit_widget"
    backends: tuple[str, ...]
    license: str
    source_url: str
    author: str
    keywords: tuple[str, ...]
    description: str
    asset_file: str | None = None
    module: str | None = None
    class_name: str | None = None
    default_bounds: dict[str, float] = field(default_factory=dict)
    parameter_schema: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0
    loopable: bool = False
    fps: int = 60
    render_mode: str = "vector"
    state_machine_inputs: dict[str, Any] = field(default_factory=dict)

    def resolved_file_path(self, assets_dir: Path | None = None) -> Path | None:
        """Resolve on-disk path for file-based assets (SVGs, Lottie JSON, Rive .riv)."""
        if not self.asset_file:
            return None
        base = assets_dir or DEFAULT_ASSETS_DIR
        return (base / self.asset_file).resolve()


def load_catalog(assets_dir: Path | None = None) -> dict[str, AssetDefinition]:
    """Load and validate all sharded category manifests from the catalog directory.

    Returns:
        dict[str, AssetDefinition] mapping asset ID -> AssetDefinition.
    Raises:
        ValueError if catalog files are corrupted or missing required schema fields.
    """
    root = assets_dir or DEFAULT_ASSETS_DIR
    catalog_dir = root / "catalog"
    index_path = catalog_dir / "index.json"

    if not index_path.is_file():
        raise FileNotFoundError(f"Asset catalog index not found: {index_path}")

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    categories = index_data.get("categories", [])
    catalog: dict[str, AssetDefinition] = {}

    for cat_meta in categories:
        manifest_file = cat_meta.get("manifest")
        if not manifest_file:
            continue
        manifest_path = catalog_dir / manifest_file
        if not manifest_path.is_file():
            continue

        with open(manifest_path, "r", encoding="utf-8") as f:
            cat_data = json.load(f)

        category_id = cat_data.get("category", cat_meta.get("id", "general"))
        objects = cat_data.get("objects", [])

        for obj in objects:
            asset_id = obj.get("id")
            if not asset_id:
                raise ValueError(f"Asset missing 'id' in {manifest_path}")

            # Validate required fields
            license_val = obj.get("license")
            source_url = obj.get("source_url")
            if not license_val or not source_url:
                raise ValueError(
                    f"Asset '{asset_id}' missing required provenance fields ('license', 'source_url') in {manifest_path}"
                )

            asset_def = AssetDefinition(
                id=asset_id,
                name=obj.get("name", asset_id),
                category=category_id,
                type=obj.get("type", "svg"),
                backends=tuple(obj.get("backends", ["manim", "scenekit"])),
                license=license_val,
                source_url=source_url,
                author=obj.get("author", "Unknown"),
                keywords=tuple(obj.get("keywords", [])),
                description=obj.get("description", ""),
                asset_file=obj.get("asset_file"),
                module=obj.get("module"),
                class_name=obj.get("class_name"),
                default_bounds=dict(obj.get("default_bounds", {})),
                parameter_schema=dict(obj.get("parameter_schema", {})),
                duration_seconds=float(obj.get("duration_seconds", 0.0)),
                loopable=bool(obj.get("loopable", False)),
                fps=int(obj.get("fps", 60)),
                render_mode=str(obj.get("render_mode", "vector")),
                state_machine_inputs=dict(obj.get("state_machine_inputs", {})),
            )
            catalog[asset_id] = asset_def

    return catalog
