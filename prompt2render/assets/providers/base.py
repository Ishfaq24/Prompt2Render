"""Base interface and data models for external media asset providers."""

from __future__ import annotations

import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AssetHit:
    """Metadata representing a single visual asset discovered from an external provider."""

    id: str
    provider: str  # "pixabay", "unsplash", "pexels", "mock"
    url: str
    author: str
    author_url: str
    license: str
    license_url: str
    title: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    width: int = 1920
    height: int = 1080
    preview_url: str = ""
    asset_type: str = "photo"  # "photo", "vector", "illustration"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "url": self.url,
            "author": self.author,
            "author_url": self.author_url,
            "license": self.license,
            "license_url": self.license_url,
            "title": self.title,
            "tags": list(self.tags),
            "width": self.width,
            "height": self.height,
            "preview_url": self.preview_url,
            "asset_type": self.asset_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetHit:
        return cls(
            id=data["id"],
            provider=data["provider"],
            url=data["url"],
            author=data.get("author", "Unknown"),
            author_url=data.get("author_url", ""),
            license=data.get("license", "Public / Free to use"),
            license_url=data.get("license_url", ""),
            title=data.get("title", ""),
            tags=tuple(data.get("tags", [])),
            width=int(data.get("width", 1920)),
            height=int(data.get("height", 1080)),
            preview_url=data.get("preview_url", ""),
            asset_type=data.get("asset_type", "photo"),
        )


class AssetProvider(ABC):
    """Abstract base class for external media providers."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the provider has active credentials/configuration."""
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        orientation: str = "landscape",
        asset_type: str = "photo",
        limit: int = 5,
    ) -> list[AssetHit]:
        """Search for assets matching a query string."""
        ...

    def download(self, hit: AssetHit, dest_path: Path, timeout: float = 20.0) -> Path:
        """Download asset to target path. Defaults to standard HTTP GET."""
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            hit.url,
            headers={"User-Agent": "Prompt2Render/1.0 (Educational Video Pipeline)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read()
        dest_path.write_bytes(data)
        return dest_path
