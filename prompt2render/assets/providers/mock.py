"""Deterministic mock asset provider for offline testing, CI, and test harnesses."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from .base import AssetHit, AssetProvider


class MockProvider(AssetProvider):
    """Mock asset provider returning deterministic synthetic assets."""

    name = "mock"

    def __init__(self, is_enabled: bool = True) -> None:
        self.enabled = is_enabled

    def is_configured(self) -> bool:
        return self.enabled

    def search(
        self,
        query: str,
        orientation: str = "landscape",
        asset_type: str = "photo",
        limit: int = 3,
    ) -> list[AssetHit]:
        if not self.is_configured():
            return []

        results: list[AssetHit] = []
        slug = query.lower().replace(" ", "_")[:20]

        for i in range(1, limit + 1):
            hit_id = f"mock_{slug}_{i}"
            hit = AssetHit(
                id=hit_id,
                provider="mock",
                url=f"mock://assets/{hit_id}.png",
                author=f"Mock Artist {i}",
                author_url="https://example.com/artist",
                license="Creative Commons Zero (CC0)",
                license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                title=f"Mock Asset: {query} (Sample {i})",
                tags=tuple(query.lower().split()),
                width=1920,
                height=1080,
                preview_url=f"mock://assets/{hit_id}_thumb.png",
                asset_type=asset_type,
            )
            results.append(hit)
        return results

    def download(self, hit: AssetHit, dest_path: Path, timeout: float = 20.0) -> Path:
        """Create a synthetic 1920x1080 image locally."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1920, 1080), color=(20, 28, 40))
        draw = ImageDraw.Draw(img)

        # Draw tech grid pattern
        for x in range(0, 1920, 80):
            draw.line([(x, 0), (x, 1080)], fill=(30, 42, 60), width=1)
        for y in range(0, 1080, 80):
            draw.line([(0, y), (1920, y)], fill=(30, 42, 60), width=1)

        # Draw a central colored rectangle
        draw.rectangle([(660, 440), (1260, 640)], fill=(35, 60, 95), outline=(65, 120, 190), width=3)
        draw.text((960, 540), f"ASSET: {hit.id}", fill=(240, 245, 255), anchor="mm")

        img.save(dest_path, format="PNG")
        return dest_path
