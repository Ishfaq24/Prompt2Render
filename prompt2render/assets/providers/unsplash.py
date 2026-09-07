"""Unsplash media provider for high-quality editorial and conceptual photography."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any

from ... import cfg
from .base import AssetHit, AssetProvider


class UnsplashProvider(AssetProvider):
    """Provider adapter for Unsplash API."""

    name = "unsplash"

    def __init__(self, access_key: str | None = None) -> None:
        cfg.load_env()
        self.access_key = (
            access_key
            or os.environ.get("UNSPLASH_ACCESS_KEY")
            or ""
        ).strip().strip("'\"")

    def is_configured(self) -> bool:
        return bool(self.access_key)

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
        unsplash_orientation = ori_map.get(orientation.lower(), "landscape")

        params: dict[str, Any] = {
            "query": query,
            "per_page": max(1, min(limit, 30)),
            "content_filter": "high",
        }
        if unsplash_orientation:
            params["orientation"] = unsplash_orientation

        url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Client-ID {self.access_key}",
                "User-Agent": "Prompt2Render/1.0 (Educational Video Pipeline)",
                "Accept-Version": "v1",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=12.0) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []

        results_data = data.get("results", [])
        results: list[AssetHit] = []

        for item in results_data[:limit]:
            urls = item.get("urls", {})
            # Prefer regular (1080p width) or full
            img_url = urls.get("regular") or urls.get("full") or urls.get("raw")
            if not img_url:
                continue

            user_data = item.get("user", {})
            author = user_data.get("name") or user_data.get("username") or "Unknown"
            links = user_data.get("links", {})
            author_url = links.get("html") or f"https://unsplash.com/@{user_data.get('username', '')}"

            title = item.get("description") or item.get("alt_description") or f"Unsplash Photo {item.get('id')}"

            # Extract tags
            tags_raw = item.get("tags", [])
            tags_list = tuple(
                t.get("title") for t in tags_raw if isinstance(t, dict) and t.get("title")
            )

            hit = AssetHit(
                id=f"unsplash_{item.get('id')}",
                provider="unsplash",
                url=img_url,
                author=author,
                author_url=author_url,
                license="Unsplash License",
                license_url="https://unsplash.com/license",
                title=title,
                tags=tags_list,
                width=int(item.get("width", 1920)),
                height=int(item.get("height", 1080)),
                preview_url=urls.get("thumb") or urls.get("small", ""),
                asset_type="photo",
            )
            results.append(hit)

        return results
