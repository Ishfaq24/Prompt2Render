"""Pixabay media provider for photos, illustrations, and vector graphics."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ... import cfg
from .base import AssetHit, AssetProvider


class PixabayProvider(AssetProvider):
    """Provider adapter for Pixabay API."""

    name = "pixabay"

    def __init__(self, api_key: str | None = None) -> None:
        cfg.load_env()
        self.api_key = (
            api_key
            or os.environ.get("PIXABAY_API_KEY")
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

        # Map generic orientation to Pixabay orientation
        ori_map = {
            "landscape": "horizontal",
            "portrait": "vertical",
            "all": "all",
        }
        pixabay_orientation = ori_map.get(orientation.lower(), "horizontal")

        # Map asset_type ("photo", "vector", "illustration")
        valid_types = {"all", "photo", "illustration", "vector"}
        pixabay_type = asset_type.lower() if asset_type.lower() in valid_types else "photo"

        params = {
            "key": self.api_key,
            "q": query,
            "orientation": pixabay_orientation,
            "image_type": pixabay_type,
            "per_page": max(3, min(limit, 50)),
            "safesearch": "true",
        }

        url = "https://pixabay.com/api/?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Prompt2Render/1.0 (Educational Video Pipeline)"},
        )

        try:
            with urllib.request.urlopen(req, timeout=12.0) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                cfg.warn(f"Pixabay API authentication failed ({err.code}): invalid or inactive PIXABAY_API_KEY")
            elif err.code == 429:
                cfg.warn(f"Pixabay API rate limit exceeded ({err.code}): quota reached")
            else:
                cfg.warn(f"Pixabay API HTTP error {err.code}: {err.reason}")
            return []
        except urllib.error.URLError as err:
            cfg.warn(f"Pixabay API connection error: {err.reason}")
            return []
        except Exception as exc:
            cfg.warn(f"Pixabay API unexpected error: {exc}")
            return []

        hits_data = data.get("hits", [])
        results: list[AssetHit] = []

        for item in hits_data[:limit]:
            tags_list = tuple(
                t.strip() for t in item.get("tags", "").split(",") if t.strip()
            )
            # Prefer largeImageURL, fallback to webformatURL
            img_url = item.get("largeImageURL") or item.get("webformatURL")
            if not img_url:
                continue

            author = item.get("user") or "Unknown"
            author_url = (
                f"https://pixabay.com/users/{author}-{item.get('user_id')}/"
                if item.get("user_id")
                else "https://pixabay.com"
            )

            hit = AssetHit(
                id=f"pixabay_{item.get('id')}",
                provider="pixabay",
                url=img_url,
                author=author,
                author_url=author_url,
                license="Pixabay Content License",
                license_url="https://pixabay.com/service/license-summary/",
                title=f"Pixabay Image {item.get('id')} ({', '.join(tags_list[:3])})",
                tags=tags_list,
                width=int(item.get("imageWidth", 1920)),
                height=int(item.get("imageHeight", 1080)),
                preview_url=item.get("previewURL", ""),
                asset_type=pixabay_type,
            )
            results.append(hit)

        return results
