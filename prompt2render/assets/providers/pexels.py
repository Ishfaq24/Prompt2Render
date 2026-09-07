"""Pexels media provider for professional photography and realistic technology assets."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from ... import cfg
from .base import AssetHit, AssetProvider


class PexelsProvider(AssetProvider):
    """Provider adapter for Pexels API."""

    name = "pexels"

    def __init__(self, api_key: str | None = None) -> None:
        cfg.load_env()
        self.api_key = (
            api_key
            or os.environ.get("PEXELS_API_KEY")
            or ""
        ).strip().strip("'\"")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        query: str,
        orientation: str = "landscape",
        asset_type: str = "photo",
        limit: int = 5,
    ) -> list[AssetHit]:
        if not self.is_configured():
            return []

        ori_map = {
            "landscape": "landscape",
            "portrait": "portrait",
            "all": None,
        }
        pexels_orientation = ori_map.get(orientation.lower(), "landscape")

        params: dict[str, Any] = {
            "query": query,
            "per_page": max(1, min(limit, 30)),
        }
        if pexels_orientation:
            params["orientation"] = pexels_orientation

        url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": self.api_key,
                "User-Agent": "Prompt2Render/1.0 (Educational Video Pipeline)",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=12.0) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        photos_data = data.get("photos", [])
        results: list[AssetHit] = []

        for item in photos_data[:limit]:
            src = item.get("src", {})
            # Prefer large2x or large
            img_url = src.get("large2x") or src.get("large") or src.get("original")
            if not img_url:
                continue

            author = item.get("photographer") or "Unknown"
            author_url = item.get("photographer_url") or "https://www.pexels.com"
            title = item.get("alt") or f"Pexels Photo {item.get('id')}"

            hit = AssetHit(
                id=f"pexels_{item.get('id')}",
                provider="pexels",
                url=img_url,
                author=author,
                author_url=author_url,
                license="Pexels License",
                license_url="https://www.pexels.com/license/",
                title=title,
                tags=tuple(t.lower() for t in title.split() if len(t) > 3),
                width=int(item.get("width", 1920)),
                height=int(item.get("height", 1080)),
                preview_url=src.get("tiny") or src.get("small", ""),
                asset_type="photo",
            )
            results.append(hit)

        return results
