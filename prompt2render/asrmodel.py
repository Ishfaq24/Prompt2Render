"""Bootstrap the optional GGML models used by prompt2render alignment.

Alignment itself must never download models.  ``prompt2render models`` is the
explicit provisioning command; builds only call :func:`available` and degrade
gracefully when a model is absent.

The downloader is deliberately defensive:

* downloads are written to ``.part`` and atomically renamed;
* HTTP failures and interrupted transfers are reported cleanly;
* downloaded files are sanity-checked before installation;
* existing models are validated before being trusted;
* hashing is streamed rather than loading a large model into RAM;
* optional VAD provisioning can never make ASR alignment fatal.
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

# name -> (filename, URL, approximate size in MB)
ASR_MODELS: dict[str, tuple[str, str, int]] = {
    "tiny.en": (
        "ggml-tiny.en.bin",
        f"{_BASE}/ggml-tiny.en.bin",
        77,
    ),
    "base.en": (
        "ggml-base.en.bin",
        f"{_BASE}/ggml-base.en.bin",
        148,
    ),
    "small.en": (
        "ggml-small.en.bin",
        f"{_BASE}/ggml-small.en.bin",
        488,
    ),
}

VAD_MODEL = (
    "ggml-silero-v5.1.2.bin",
    "https://huggingface.co/ggml-org/whisper-vad/resolve/main/"
    "ggml-silero-v5.1.2.bin",
    1,
)

# whisper.cpp GGML files normally begin with "lmgg" on little-endian
# systems. Accept the opposite byte ordering as well.
_GGML_MAGIC = (b"lmgg", b"ggml")

# Never accept a model that is suspiciously small, even if it happens to have
# a matching four-byte header.
_MIN_ASR_BYTES = 1_000_000
_MIN_VAD_BYTES = 200_000

_USER_AGENT = "prompt2render/1.0"
_DOWNLOAD_TIMEOUT = 60


def _looks_like_ggml(path: Path) -> bool:
    """Return True when ``path`` has a recognized GGML header."""

    try:
        if not path.is_file() or path.stat().st_size < 8:
            return False

        with path.open("rb") as fh:
            return fh.read(4) in _GGML_MAGIC
    except OSError:
        return False


def _looks_like_vad(path: Path) -> bool:
    """Conservative sanity check for the optional VAD model."""

    try:
        return (
            path.is_file()
            and path.stat().st_size >= _MIN_VAD_BYTES
        )
    except OSError:
        return False


def asr_path(name_or_path: str | None = None) -> Path:
    """Resolve a configured ASR model name or explicit filesystem path.

    ``base.en`` and the other registered names resolve into the project's
    model directory. Explicit absolute paths are supported for shared models.
    Relative explicit paths are resolved from ``cfg.ROOT``.
    """

    raw = (
        name_or_path
        or os.environ.get(
            "P2R_WHISPER_MODEL",
            "base.en",
        )
    ).strip()

    if raw in ASR_MODELS:
        return WHISPER_DIR / ASR_MODELS[raw][0]

    path = Path(raw).expanduser()
    return (
        path
        if path.is_absolute()
        else cfg.ROOT / path
    )


def vad_path() -> Path:
    """Return the installed optional VAD model path."""

    return WHISPER_DIR / VAD_MODEL[0]


def available(name_or_path: str | None = None) -> Path | None:
    """Return a usable ASR model, otherwise ``None``.

    This function is intentionally side-effect free: it never downloads,
    creates directories, or modifies the model.
    """

    path = asr_path(name_or_path)

    try:
        valid = (
            path.is_file()
            and path.stat().st_size >= _MIN_ASR_BYTES
            and _looks_like_ggml(path)
        )
    except OSError:
        valid = False

    return path if valid else None


def vad_available() -> Path | None:
    """Return the optional VAD model when a plausible file is installed."""

    path = vad_path()
    return path if _looks_like_vad(path) else None


def missing_note(name_or_path: str | None = None) -> str:
    """Human-readable provisioning instruction for a missing ASR model."""

    name = (
        name_or_path
        or os.environ.get(
            "P2R_WHISPER_MODEL",
            "base.en",
        )
    )

    if name in ASR_MODELS:
        mb = ASR_MODELS[name][2]
    else:
        mb = 148

    return (
        f"no ASR model at {asr_path(name)} — "
        f"run: python prompt2render.py models --asr {name} "
        f"({mb} MB, one time)"
    )


def _sha256(path: Path) -> str:
    """Hash a file without loading it entirely into memory."""

    digest = hashlib.sha256()

    with path.open("rb") as fh:
        for block in iter(
            lambda: fh.read(1 << 20),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def _download(
    url: str,
    dst: Path,
    approx_mb: int,
) -> None:
    """Download, validate, and atomically install a model.

    ``dst`` is untouched until the complete temporary download passes all
    validation checks. This prevents an interrupted download from destroying
    an already-installed working model.
    """

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    part = dst.with_name(
        dst.name + ".part"
    )

    # Remove a stale partial file from an earlier interrupted invocation.
    part.unlink(
        missing_ok=True
    )

    host = url.split("/", 3)[2] if "://" in url else url

    cfg.say(
        f"fetching {dst.name} (~{approx_mb} MB) "
        f"from {host}"
    )

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/octet-stream",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=_DOWNLOAD_TIMEOUT,
        ) as response:
            total_header = response.headers.get(
                "Content-Length"
            )

            try:
                total = int(total_header or 0)
            except ValueError:
                total = 0

            got = 0

            with part.open("wb") as out:
                while True:
                    chunk = response.read(
                        1 << 20
                    )
                    if not chunk:
                        break

                    out.write(chunk)
                    got += len(chunk)

                    if total > 0:
                        pct = (
                            100.0
                            * got
                            / total
                        )
                        print(
                            f"\r      "
                            f"{got / 1e6:6.1f} / "
                            f"{total / 1e6:.1f} MB "
                            f"{pct:5.1f}%",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\r      "
                            f"{got / 1e6:6.1f} MB",
                            end="",
                            flush=True,
                        )

            print()

            # When the server supplied a length, detect a truncated response
            # before any model validation.
            if total > 0 and got != total:
                raise OSError(
                    f"incomplete download: received "
                    f"{got} of {total} bytes"
                )

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        OSError,
    ) as exc:
        part.unlink(
            missing_ok=True
        )

        sys.exit(
            f"[prompt2render] download failed: {exc}\n"
            f"      you can also fetch it by hand into "
            f"{dst.parent}\n"
            f"      {url}"
        )

    try:
        size = part.stat().st_size
    except OSError as exc:
        part.unlink(
            missing_ok=True
        )
        sys.exit(
            f"[prompt2render] downloaded file cannot be "
            f"inspected: {exc}"
        )

    size_mb = size / 1e6

    # Approximate sizes are intentionally treated as lower bounds only.
    # This catches truncated downloads without rejecting a legitimate model
    # whose upstream size changes slightly.
    minimum_bytes = max(
        _MIN_ASR_BYTES,
        int(
            approx_mb
            * 1e6
            * 0.50
        ),
    )

    if size < minimum_bytes:
        part.unlink(
            missing_ok=True
        )
        sys.exit(
            f"[prompt2render] {dst.name} came back at "
            f"{size_mb:.1f} MB, expected ~{approx_mb} MB — "
            "the download was truncated; try again"
        )

    if dst.name.startswith(
        "ggml-"
    ) and "silero" not in dst.name:
        if not _looks_like_ggml(part):
            part.unlink(
                missing_ok=True
            )
            sys.exit(
                f"[prompt2render] {dst.name} is not a "
                "recognized GGML model — the URL probably "
                "returned an error page rather than the file"
            )

    if "silero" in dst.name and not _looks_like_vad(part):
        part.unlink(
            missing_ok=True
        )
        sys.exit(
            f"[prompt2render] {dst.name} is unexpectedly "
            "small or invalid"
        )

    digest = _sha256(part)

    try:
        # os.replace() is atomic when source and destination are on the same
        # filesystem, which they are because both live in WHISPER_DIR.
        os.replace(
            part,
            dst,
        )
    except OSError as exc:
        part.unlink(
            missing_ok=True
        )
        sys.exit(
            f"[prompt2render] could not install "
            f"{dst.name}: {exc}"
        )

    cfg.say(
        f"  {dst.name}  "
        f"{size_mb:.1f} MB  "
        f"sha256:{digest[:16]}..."
    )


def fetch_asr(
    name: str = "base.en",
    force: bool = False,
) -> Path:
    """Provision one registered ASR model."""

    if name not in ASR_MODELS:
        sys.exit(
            f"[prompt2render] unknown ASR model '{name}' — "
            f"choose from: {', '.join(ASR_MODELS)}"
        )

    filename, url, approx_mb = ASR_MODELS[name]
    dst = WHISPER_DIR / filename

    if (
        dst.exists()
        and not force
        and available(name) is not None
    ):
        cfg.say(
            f"{filename} already present "
            f"({dst.stat().st_size / 1e6:.1f} MB)"
        )
        return dst

    _download(
        url,
        dst,
        approx_mb,
    )

    # Validate the final installed path as an additional postcondition.
    if available(name) is None:
        dst.unlink(
            missing_ok=True
        )
        sys.exit(
            f"[prompt2render] installed ASR model "
            f"{dst} failed final validation"
        )

    return dst


def fetch_vad(
    force: bool = False,
) -> Path | None:
    """Provision the optional VAD model.

    VAD is deliberately non-fatal. Alignment must continue without it.
    """

    filename, url, approx_mb = VAD_MODEL
    dst = WHISPER_DIR / filename

    if (
        dst.exists()
        and not force
        and vad_available() is not None
    ):
        cfg.say(
            f"{filename} already present"
        )
        return dst

    try:
        _download(
            url,
            dst,
            approx_mb,
        )

        if vad_available() is None:
            dst.unlink(
                missing_ok=True
            )
            raise OSError(
                "installed VAD model failed validation"
            )

        return dst

    except SystemExit as exc:
        cfg.warn(
            f"VAD model unavailable ({exc}) — "
            "alignment will run without it"
        )
        return None


__all__ = [
    "ASR_MODELS",
    "VAD_MODEL",
    "WHISPER_DIR",
    "asr_path",
    "available",
    "fetch_asr",
    "fetch_vad",
    "missing_note",
    "vad_available",
    "vad_path",
]