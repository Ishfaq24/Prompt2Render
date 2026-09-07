"""Atomic, multi-process disk cache for external media assets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from .providers.base import AssetHit, AssetProvider

DEFAULT_CACHE_DIR = Path.home() / ".prompt2render" / "cache" / "assets"
_CACHE_LOCK = threading.Lock()


class AssetCache:
    """Multi-process and thread-safe disk cache for fetched media assets."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = (cache_dir or DEFAULT_CACHE_DIR).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_for(self, url: str) -> str:
        """Compute SHA256 hex digest for a URL."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def get(self, hit: AssetHit) -> Path | None:
        """Return cached image path if already downloaded and verified, else None."""
        key = self._key_for(hit.url)
        # Determine extension from hit or default to .png
        ext = Path(hit.url.split("?")[0]).suffix.lower() or ".png"
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            ext = ".png"

        img_path = self.cache_dir / f"{key}{ext}"
        meta_path = self.cache_dir / f"{key}.meta.json"

        if img_path.is_file() and meta_path.is_file():
            try:
                if img_path.stat().st_size > 0:
                    return img_path
            except OSError:
                pass

        return None

    def fetch_or_download(
        self,
        hit: AssetHit,
        provider: AssetProvider,
        timeout: float = 20.0,
    ) -> Path:
        """Get path from cache, or download via provider and cache atomically."""
        cached = self.get(hit)
        if cached:
            return cached

        key = self._key_for(hit.url)
        ext = Path(hit.url.split("?")[0]).suffix.lower() or ".png"
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".svg"}:
            ext = ".png"

        dest_img = self.cache_dir / f"{key}{ext}"
        dest_meta = self.cache_dir / f"{key}.meta.json"

        tmp_img = self.cache_dir / f".tmp_{os.getpid()}_{threading.get_ident()}_{key}{ext}"
        tmp_meta = self.cache_dir / f".tmp_{os.getpid()}_{threading.get_ident()}_{key}.meta.json"

        # Download to tmp_img
        provider.download(hit, tmp_img, timeout=timeout)

        # Write metadata
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(hit.to_dict(), f, indent=2)

        # Atomically replace
        with _CACHE_LOCK:
            try:
                tmp_img.replace(dest_img)
            except OSError:
                pass
            try:
                tmp_meta.replace(dest_meta)
            except OSError:
                pass

        # Cleanup tmp if anything remained
        tmp_img.unlink(missing_ok=True)
        tmp_meta.unlink(missing_ok=True)

        return dest_img
