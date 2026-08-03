"""Bootstrap the GGML models the ffmpeg whisper filter needs.

Alignment needs no Python package — ffmpeg 8.x is built `--enable-whisper` and
carries whisper.cpp inside it. What it does need is a model file, and that is
the only thing standing between a clean checkout and word-level sync.

The rule that shapes this module: **never download inside a build**. A ten
minute pipeline must not stop to fetch 148 MB, and a missing optional model
must degrade rather than abort. `fdx models` is the explicit, interruptible
place where that cost is paid.
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import cfg

WHISPER_DIR = cfg.MODELS / "whisper"

_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

#: name -> (filename, url, approximate MB). The sizes are sanity bounds, not
#: checksums: a truncated download is the failure mode worth catching, and it
#: is always dramatically short rather than subtly wrong.
ASR_MODELS = {
    "tiny.en":  ("ggml-tiny.en.bin",  f"{_BASE}/ggml-tiny.en.bin",   77),
    "base.en":  ("ggml-base.en.bin",  f"{_BASE}/ggml-base.en.bin",  148),
    "small.en": ("ggml-small.en.bin", f"{_BASE}/ggml-small.en.bin", 488),
}

VAD_MODEL = (
    "ggml-silero-v5.1.2.bin",
    "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin",
    1,          # genuinely this small — silero is a tiny model
)

#: whisper.cpp writes `struct.pack("i", 0x67676d6c)`, which lands on disk as
#: b"lmgg" on a little-endian machine. Accept both orientations rather than
#: assume the writer's endianness.
_GGML_MAGIC = (b"lmgg", b"ggml")


def _looks_like_ggml(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) in _GGML_MAGIC
    except OSError:
        return False


def asr_path(name_or_path: str | None = None) -> Path:
    """Resolve FDX_WHISPER_MODEL to a concrete path (which may not exist).

    Accepts either a model name ("base.en") or an explicit path, so a shared
    model directory outside the repo works without copying files around.
    """
    raw = name_or_path or os.environ.get("FDX_WHISPER_MODEL", "base.en")
    if raw in ASR_MODELS:
        return WHISPER_DIR / ASR_MODELS[raw][0]
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (cfg.ROOT / p)


def vad_path() -> Path:
    return WHISPER_DIR / VAD_MODEL[0]


def available(name_or_path: str | None = None) -> Path | None:
    """The ASR model path if it is present and plausibly intact, else None."""
    p = asr_path(name_or_path)
    if p.exists() and p.stat().st_size > 1_000_000 and _looks_like_ggml(p):
        return p
    return None


def vad_available() -> Path | None:
    p = vad_path()
    return p if p.exists() and p.stat().st_size > 200_000 else None


def missing_note(name_or_path: str | None = None) -> str:
    name = name_or_path or os.environ.get("FDX_WHISPER_MODEL", "base.en")
    mb = ASR_MODELS.get(name, (None, None, 148))[2]
    return (f"no ASR model at {asr_path(name)} — "
            f"run: python fdx.py models --asr {name}  ({mb} MB, one time)")


def _download(url: str, dst: Path, approx_mb: int) -> None:
    """Fetch to a .part sidecar, validate, then rename into place.

    A half-written model that the presence check trusts is worse than no model
    at all: it would fail deep inside a filtergraph with an opaque error.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_suffix(dst.suffix + ".part")
    cfg.say(f"fetching {dst.name} (~{approx_mb} MB) from {url.split('/')[2]}")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fdx-studio"})
        with urllib.request.urlopen(req) as resp, part.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                got += len(chunk)
                if total:
                    pct = 100 * got / total
                    print(f"\r      {got/1e6:6.1f} / {total/1e6:.1f} MB  {pct:5.1f}%",
                          end="", flush=True)
                else:
                    print(f"\r      {got/1e6:6.1f} MB", end="", flush=True)
        print()
    except urllib.error.URLError as e:
        part.unlink(missing_ok=True)
        sys.exit(f"[fdx] download failed: {e}\n"
                 f"      you can also fetch it by hand into {dst.parent}\n"
                 f"      {url}")

    size_mb = part.stat().st_size / 1e6
    if size_mb < approx_mb * 0.5:
        part.unlink(missing_ok=True)
        sys.exit(f"[fdx] {dst.name} came back at {size_mb:.1f} MB, expected "
                 f"~{approx_mb} MB — the download was truncated, try again")
    if dst.name.startswith("ggml-") and "silero" not in dst.name \
            and not _looks_like_ggml(part):
        part.unlink(missing_ok=True)
        sys.exit(f"[fdx] {dst.name} is not a GGML model — the URL probably "
                 "returned an error page rather than the file")

    part.replace(dst)
    digest = hashlib.sha256(dst.read_bytes()).hexdigest()
    cfg.say(f"  {dst.name}  {size_mb:.1f} MB  sha256:{digest[:16]}...")


def fetch_asr(name: str = "base.en", force: bool = False) -> Path:
    if name not in ASR_MODELS:
        sys.exit(f"[fdx] unknown ASR model '{name}' — "
                 f"choose from: {', '.join(ASR_MODELS)}")
    fname, url, mb = ASR_MODELS[name]
    dst = WHISPER_DIR / fname
    if dst.exists() and not force and _looks_like_ggml(dst):
        cfg.say(f"{fname} already present ({dst.stat().st_size/1e6:.1f} MB)")
        return dst
    _download(url, dst, mb)
    return dst


def fetch_vad(force: bool = False) -> Path | None:
    """VAD is genuinely optional — never let its absence stop anything.

    It matters because the inter-sentence silences the voice engine inserts
    are exactly where whisper likes to hallucinate text. Worth having, not
    worth failing over.
    """
    fname, url, mb = VAD_MODEL
    dst = WHISPER_DIR / fname
    if dst.exists() and not force:
        cfg.say(f"{fname} already present")
        return dst
    try:
        _download(url, dst, mb)
        return dst
    except SystemExit as e:
        cfg.warn(f"VAD model unavailable ({e}) — alignment will run without it")
        return None
