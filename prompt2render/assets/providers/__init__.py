"""External asset providers package and aggregator."""

from __future__ import annotations

from typing import Sequence

from .base import AssetHit, AssetProvider
from .mock import MockProvider
from .pexels import PexelsProvider
from .pixabay import PixabayProvider
from .unsplash import UnsplashProvider

__all__ = [
    "AssetHit",
    "AssetProvider",
    "PixabayProvider",
    "UnsplashProvider",
    "PexelsProvider",
    "MockProvider",
    "get_available_providers",
    "search_all_providers",
]


def get_available_providers(allow_mock_fallback: bool = True) -> list[AssetProvider]:
    """Return all active providers with valid credentials, or mock if none are configured."""
    active: list[AssetProvider] = []

    # Check Pixabay
    pix = PixabayProvider()
    if pix.is_configured():
        active.append(pix)

    # Check Unsplash
    uns = UnsplashProvider()
    if uns.is_configured():
        active.append(uns)

    # Check Pexels
    pex = PexelsProvider()
    if pex.is_configured():
        active.append(pex)

    if not active and allow_mock_fallback:
        active.append(MockProvider())

    return active


def search_all_providers(
    query: str,
    providers: Sequence[AssetProvider] | None = None,
    orientation: str = "landscape",
    asset_type: str = "photo",
    limit_per_provider: int = 3,
) -> list[AssetHit]:
    """Query all available or specified providers and return aggregated hits."""
    target_providers = providers if providers is not None else get_available_providers()
    all_hits: list[AssetHit] = []

    for prov in target_providers:
        try:
            hits = prov.search(
                query=query,
                orientation=orientation,
                asset_type=asset_type,
                limit=limit_per_provider,
            )
            all_hits.extend(hits)
        except Exception:
            continue

    return all_hits
