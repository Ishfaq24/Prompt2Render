"""Video library backing the Studio "Library" view.

Scans the curated ``Final Results/`` directory at the repository root and
exposes every finished video with a human-readable title, size, duration and
a cached poster thumbnail.

Design notes
------------
* The directory is re-scanned on every request so newly dropped videos show
  up without restarting the server.
* Lookups by filename only ever resolve against the directory listing -- a
  request can never name a path outside ``Final Results/``.
* Durations (ffprobe) and thumbnails (ffmpeg) are cached under
  ``media/library_cache/`` keyed by name + size + mtime, so they are computed
  once per file version. Both degrade gracefully when ffmpeg is missing.
* An optional ``Final Results/library.json`` can override titles/descriptions:
  ``{"NginX.mp4": {"title": "NGINX", "description": "..."}}``.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
from typing import Any

from prompt2render import cfg

LIBRARY_DIR: Path = cfg.ROOT / "Final Results"
CACHE_DIR: Path = cfg.ROOT / "media" / "library_cache"
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v", ".mkv"}
MANIFEST_NAME = "library.json"

_LANG_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("hindi", "Hindi"),
    ("urdu", "Urdu"),
    ("kashur", "Kashmiri"),
    ("kashmiri", "Kashmiri"),
    ("arabic", "Arabic"),
)

_meta_lock = threading.Lock()
_thumb_locks: dict[str, threading.Lock] = {}
_thumb_locks_guard = threading.Lock()


# ------------------------------------------------------------------ naming --

_WORD_FIXUPS: dict[str, str] = {
    "ml": "ML",
    "ai": "AI",
    "llm": "LLM",
    "llms": "LLMs",
    "dfa": "DFA",
    "nfa": "NFA",
    "rsa": "RSA",
    "dns": "DNS",
    "ssh": "SSH",
    "nginx": "NGINX",
    "virtualmemory": "Virtual Memory",
}


def prettify_name(stem: str) -> str:
    """Turn a file stem into a display title.

    ``GradientDescent`` -> ``Gradient Descent``, ``RSA-Full-Explainer`` ->
    ``RSA Full Explainer``, ``defectiveVideo`` -> ``Defective Video``.
    Acronyms such as ``DFA`` or ``KMeans`` are left intact.
    """
    text = re.sub(r"[-_]+", " ", stem)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"(?<=[A-Z]{2})(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return stem
    words = [
        _WORD_FIXUPS.get(w.lower(), w[:1].upper() + w[1:] if w.islower() else w)
        for w in text.split(" ")
    ]
    return " ".join(words)


def detect_language(stem: str) -> str:
    low = stem.lower()
    for key, lang in _LANG_KEYWORDS:
        if key in low:
            return lang
    return "English"


# --------------------------------------------------------------- discovery --

def _load_manifest() -> dict[str, dict[str, Any]]:
    path = LIBRARY_DIR / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _video_files() -> list[Path]:
    if not LIBRARY_DIR.is_dir():
        return []
    return sorted(
        (p for p in LIBRARY_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in VIDEO_EXTS and not p.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )


def resolve_video(filename: str) -> Path | None:
    """Return the library file whose name matches *exactly*, else ``None``."""
    for p in _video_files():
        if p.name == filename:
            return p
    return None


def _cache_key(p: Path) -> str:
    st = p.stat()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", p.stem)
    return f"{safe}-{st.st_size}-{int(st.st_mtime)}"


# --------------------------------------------------------------- ffmpeg io --

def _probe_duration(p: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            capture_output=True, text=True, timeout=20,
        )
        return round(float(out.stdout.strip()), 2)
    except Exception:
        return None


def _meta_cache_path() -> Path:
    return CACHE_DIR / "durations.json"


def _durations(files: list[Path]) -> dict[str, float | None]:
    """Durations keyed by filename; probes only files whose cache key changed."""
    with _meta_lock:
        cache_path = _meta_cache_path()
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
        except Exception:
            cache = {}

        keys = {p.name: _cache_key(p) for p in files}
        missing = [p for p in files if cache.get(keys[p.name]) is None]
        if missing:
            with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
                for p, dur in zip(missing, pool.map(_probe_duration, missing)):
                    if dur is not None:
                        cache[keys[p.name]] = dur
            # Drop entries for files that no longer exist / changed.
            live = set(keys.values())
            cache = {k: v for k, v in cache.items() if k in live}
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            except OSError:
                pass
        return {name: cache.get(key) for name, key in keys.items()}


def thumbnail_path(p: Path) -> Path | None:
    """Return a cached JPEG poster for *p*, generating it on first request."""
    target = CACHE_DIR / "thumbs" / f"{_cache_key(p)}.jpg"
    if target.is_file() and target.stat().st_size > 0:
        return target

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None

    with _thumb_locks_guard:
        lock = _thumb_locks.setdefault(target.name, threading.Lock())
    with lock:
        if target.is_file() and target.stat().st_size > 0:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp.jpg")
        # Seek a few seconds in to skip black title fades; fall back to frame 0
        # for very short clips.
        for seek in ("4", "0"):
            try:
                subprocess.run(
                    [ffmpeg, "-y", "-loglevel", "error", "-ss", seek, "-i", str(p),
                     "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(tmp)],
                    capture_output=True, timeout=30,
                )
            except Exception:
                continue
            if tmp.is_file() and tmp.stat().st_size > 0:
                tmp.replace(target)
                return target
        tmp.unlink(missing_ok=True)
        return None


# ------------------------------------------------------------------ public --

def list_videos() -> list[dict[str, Any]]:
    files = _video_files()
    manifest = _load_manifest()
    durations = _durations(files)
    items: list[dict[str, Any]] = []
    for p in files:
        st = p.stat()
        override = manifest.get(p.name, {}) if isinstance(manifest.get(p.name), dict) else {}
        items.append({
            "id": p.name,
            "filename": p.name,
            "title": str(override.get("title") or prettify_name(p.stem)),
            "description": str(override.get("description") or ""),
            "language": str(override.get("language") or detect_language(p.stem)),
            "size_bytes": st.st_size,
            "size_mb": round(st.st_size / (1024 * 1024), 1),
            "duration_s": durations.get(p.name),
            "modified": int(st.st_mtime),
            "format": p.suffix.lstrip(".").lower(),
        })
    return items


def library_filename_for(slug: str, title: str | None = None) -> str:
    """Derive a clean PascalCase `.mp4` filename for `Final Results/`."""
    raw = (title or slug or "Video").strip()
    tokens = re.findall(r"[A-Za-z0-9]+", raw)
    if not tokens:
        tokens = ["Video"]
    parts: list[str] = []
    for tok in tokens:
        fixed = _WORD_FIXUPS.get(tok.lower())
        if fixed and fixed.isupper():
            parts.append(fixed)
        elif tok.isupper() and len(tok) > 1:
            parts.append(tok)
        else:
            parts.append(tok[:1].upper() + tok[1:].lower())
    return "".join(parts) + ".mp4"


def export_project_video(
    proj_dir: Path,
    video_path: Path,
    title: str | None = None,
) -> dict[str, Any] | None:
    """Copy a project's finished video into ``Final Results/`` and return its library entry."""
    if not video_path.is_file() or video_path.stat().st_size <= 1024:
        return None
    slug = proj_dir.name
    # If a renamed MP4 already exists in out/ (e.g. GradientDescent.mp4), keep its filename
    if video_path.name.lower() != "final.mp4":
        dest_name = video_path.name
    else:
        dest_name = library_filename_for(slug, title)

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = LIBRARY_DIR / dest_name
    tmp = dest.with_suffix(".tmp.mp4")
    shutil.copy2(video_path, tmp)
    tmp.replace(dest)

    # Record clean display title in library.json when provided
    if title:
        manifest_path = LIBRARY_DIR / MANIFEST_NAME
        manifest = _load_manifest()
        entry = manifest.get(dest_name, {})
        if not isinstance(entry, dict):
            entry = {}
        entry["title"] = title
        manifest[dest_name] = entry
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    st = dest.stat()
    dur = _durations([dest]).get(dest_name)
    return {
        "id": dest_name,
        "filename": dest_name,
        "title": title or prettify_name(dest.stem),
        "path": str(dest),
        "size_mb": round(st.st_size / (1024 * 1024), 1),
        "duration_s": dur,
    }
