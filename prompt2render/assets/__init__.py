"""Visual assets management, adapters, and retrieval module for Prompt2Render."""

from .cache import AssetCache
from .loader import AssetDefinition, load_catalog
from .preprocessor import prepare_scene_asset
from .relevance import is_asset_relevant, detect_domain

__all__ = [
    "AssetCache",
    "AssetDefinition",
    "load_catalog",
    "prepare_scene_asset",
    "is_asset_relevant",
    "detect_domain",
]
