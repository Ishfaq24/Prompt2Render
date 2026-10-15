"""Shared configuration, paths, subprocess helpers, and encoder selection.

All stages that produce clips intended for concat must use the same VOPTS vector.
GPU encoding is selected only after a real NVENC probe succeeds; otherwise the
pipeline falls back to libx264.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


IS_WINDOWS = platform.system() == "Windows"

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
MODELS = ROOT / "models"


# ---------------------------------------------------------------- video ----

WIDTH, HEIGHT, FPS = 1920, 1080, 30
CRF = "20"

PROFILES: dict[str, dict[str, Any]] = {
    "16:9": {"width": 1920, "height": 1080, "label": "landscape"},
    "landscape": {"width": 1920, "height": 1080, "label": "landscape"},
    "9:16": {"width": 1080, "height": 1920, "label": "portrait"},
    "portrait": {"width": 1080, "height": 1920, "label": "portrait"},
    "shorts": {"width": 1080, "height": 1920, "label": "portrait"},
    "1:1": {"width": 1080, "height": 1080, "label": "square"},
    "square": {"width": 1080, "height": 1080, "label": "square"},
}


def set_dimensions(aspect_or_width: str | int = "16:9", height: int | None = None) -> tuple[int, int]:
    """Dynamically set video dimensions and aspect ratio profile."""
    global WIDTH, HEIGHT
    if isinstance(aspect_or_width, str):
        key = aspect_or_width.lower().strip()
        if key in PROFILES:
            WIDTH = PROFILES[key]["width"]
            HEIGHT = PROFILES[key]["height"]
        elif "x" in key:
            try:
                w_str, h_str = key.split("x", 1)
                WIDTH = int(w_str.strip())
                HEIGHT = int(h_str.strip())
            except ValueError:
                pass
    elif isinstance(aspect_or_width, int) and height is not None:
        WIDTH = aspect_or_width
        HEIGHT = height
    return WIDTH, HEIGHT


# One encoder vector for all clips that will later be concatenated with
# -c copy. Do not change this independently in individual stages.
VOPTS = [
    "-c:v", "libx264",
    "-crf", CRF,
    "-preset", "veryfast",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
    "-g", str(FPS * 5),
    "-x264-params", "scenecut=0",
]

# Fast preview only. Preview clips must never be mixed with final libx264
# clips in a concat-copy operation.
VOPTS_PREVIEW = [
    "-c:v", "h264_nvenc",
    "-preset", "p1",
    "-cq", "28",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
    "-g", str(FPS * 5),
    "-bf", "0",
]

VOPTS_PREVIEW_CPU = [
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-crf", "28",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
    "-g", str(FPS * 5),
    "-x264-params", "scenecut=0",
]

# Conservative NVENC final vector. The probe below uses these same encoder
# settings so "GPU available" means the settings we actually intend to use
# can open successfully, rather than merely proving that ffmpeg was compiled
# with NVENC support.
VOPTS_GPU = [
    "-c:v", "h264_nvenc",
    "-preset", "p4",
    "-profile:v", "main",
    "-rc", "vbr",
    "-cq", "21",
    "-b:v", "0",
    "-pix_fmt", "yuv420p",
    "-r", str(FPS),
    "-g", str(FPS * 5),
    "-bf", "0",
]


# ---------------------------------------------------------------- audio ----

AUDIO_SR = 48000
TTS_SR = 24000
AAC_BITRATE = "192k"
LUFS = -14.0
TRUE_PEAK = -1.5
LRA = 9.0


# ------------------------------------------------------------- timing -----

PAUSE_SENTENCE_MS = 320
PAUSE_QUESTION_MS = 380
PAUSE_CLAUSE_MS = 120
PAUSE_PARAGRAPH_MS = 650
VISUAL_LEAD_MS = 120


# ------------------------------------------------------------- captions ---

CAPTION_LINE = 42
CAPTION_LINES = 2
CAPTION_MIN_S = 0.833
CAPTION_MAX_S = 7.0
CAPTION_CPS = 20.0

CAPTION_FONT = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
DEFAULT_MANIM_FONT = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
CAPTION_FONT_SIZE = 28

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def font_file() -> str | None:
    """Return an existing TTF/TTF-compatible font path, if available."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def filter_path(p: Path | str) -> str:
    """Quote and escape a filesystem path for an FFmpeg filtergraph."""
    value = str(p).replace("\\", "/").replace(":", r"\:")
    return f"'{value}'"


def drawtext_font_arg() -> str:
    """Return the escaped fontfile= fragment for FFmpeg drawtext."""
    font = font_file()
    if not font:
        return ""
    return f"fontfile={filter_path(font)}:"


# ------------------------------------------------------------------ env ----

_ENV_LOADED = False

def load_env(path: Path | None = None, force: bool = False) -> None:
    """Minimal .env loader without requiring python-dotenv at import time."""
    global _ENV_LOADED
    if _ENV_LOADED and not force and path is None:
        return
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    _ENV_LOADED = True

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = line.strip()
        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'"),
        )


def env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)

    if raw is None or not raw.strip():
        return default

    try:
        return float(raw)
    except ValueError:
        sys.exit(
            f"[prompt2render] {key} must be a number, "
            f"got {raw!r}"
        )


def env_int(key: str, default: int) -> int:
    return int(env_float(key, default))


# ------------------------------------------------------------ processes ----

def need(*binaries: str) -> None:
    missing = [
        binary
        for binary in binaries
        if shutil.which(binary) is None
    ]

    if missing:
        sys.exit(
            "[prompt2render] missing required tool(s): "
            f"{', '.join(missing)} — run setup, then: "
            "python prompt2render.py doctor"
        )


def run(
    cmd: list[str],
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run a command and surface useful stderr on failure."""
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    if proc.returncode != 0:
        sys.stderr.write(
            (proc.stderr or "")[-4000:] + "\n"
        )
        raise SystemExit(
            "[prompt2render] command failed: "
            f"{' '.join(cmd[:6])} ..."
        )

    return proc


def try_run(
    cmd: list[str],
    **kwargs,
) -> subprocess.CompletedProcess:
    """Run a command without turning a non-zero exit into SystemExit."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


# -------------------------------------------------------------- GPU --------

_gpu_ok: bool | None = None
_gpu_error: str | None = None
_gpu_lock = threading.Lock()


def _nvenc_probe() -> tuple[bool, str | None]:
    """Perform a real NVENC encode using the intended final settings.

    Merely finding ``h264_nvenc`` in ``ffmpeg -encoders`` is insufficient:
    driver/API incompatibility, unavailable hardware, or a failed NVENC
    initialization can still make the encoder unusable.
    """
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}",
        "-frames:v", "30",
        *VOPTS_GPU,
        "-f", "null",
        "-",
    ]

    try:
        proc = try_run(
            command,
            timeout=20,
        )
    except Exception as exc:
        return False, str(exc)

    if proc.returncode == 0:
        return True, None

    lines = [
        line.strip()
        for line in (proc.stderr or "").splitlines()
        if line.strip()
    ]

    # Prefer the actual encoder error instead of returning the whole log.
    keywords = (
        "error",
        "failed",
        "cannot",
        "unknown",
        "nvenc",
        "cuda",
    )

    diagnostic = next(
        (
            line
            for line in lines
            if any(
                keyword in line.lower()
                for keyword in keywords
            )
        ),
        lines[-1] if lines else None,
    )

    return False, diagnostic or "NVENC probe failed"


def gpu_encode_available() -> bool:
    """Return whether the intended NVENC final encoder currently works.

    The result is cached for the lifetime of this process. This prevents every
    clip from spawning a separate hardware probe.
    """
    global _gpu_ok, _gpu_error

    if _gpu_ok is not None:
        return _gpu_ok

    with _gpu_lock:
        if _gpu_ok is not None:
            return _gpu_ok

        _gpu_ok, _gpu_error = _nvenc_probe()

    return _gpu_ok


def pick_vopts(preview: bool = False) -> list[str]:
    """Select one encoder vector for the complete encoding pass.

    GPU capability is tested once. A failed NVENC probe falls back to CPU.
    The returned list is a copy so callers cannot accidentally mutate the
    shared constants.
    """
    if gpu_encode_available():
        return list(
            VOPTS_PREVIEW if preview else VOPTS_GPU
        )

    if not getattr(
        pick_vopts,
        "_warned",
        False,
    ):
        reason = (
            _gpu_error
            or "unsupported build or hardware"
        )

        if preview:
            warn(
                "no working NVENC encoder found "
                f"({reason}) -- preview falling back "
                "to a fast CPU preset"
            )
        else:
            warn(
                "no working NVENC encoder found "
                f"({reason}) -- encoding on CPU "
                "(libx264); this will be slower"
            )

        pick_vopts._warned = True

    return list(
        VOPTS_PREVIEW_CPU if preview else VOPTS
    )


def default_encode_jobs() -> int:
    """Choose a conservative default encode concurrency."""
    return 3 if gpu_encode_available() else 1


# -------------------------------------------------------------- streaming ---

def stream_run(
    cmd: list[str],
    **kwargs,
) -> int:
    """Run a command while forwarding combined output live."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    if proc.stdout is not None:
        for line in proc.stdout:
            print(
                line,
                end="",
                flush=True,
            )

    proc.wait()
    return proc.returncode


def parallel(
    fn,
    items: list,
    jobs: int,
    label: str = "",
) -> list:
    """Apply fn concurrently while preserving input order."""
    if not items:
        return []

    n = max(
        1,
        min(int(jobs), len(items)),
    )

    if n == 1:
        return [
            fn(item)
            for item in items
        ]

    with ThreadPoolExecutor(
        max_workers=n,
        thread_name_prefix=(
            label or "prompt2render"
        ),
    ) as pool:
        return list(
            pool.map(fn, items)
        )


def probe_jobs() -> int:
    """Return ffprobe concurrency from P2R_PROBE_JOBS or a safe default."""
    wanted = env_int(
        "P2R_PROBE_JOBS",
        0,
    )

    return (
        wanted
        if wanted > 0
        else max(
            2,
            min(
                8,
                (os.cpu_count() or 2) * 2,
            ),
        )
    )


# -------------------------------------------------------------- ffprobe ----

_probe_cache: dict = {}
_probe_lock = threading.Lock()


def _stamp(
    path: Path,
    kind: str,
):
    try:
        stat = path.stat()
    except OSError:
        return None

    return (
        kind,
        str(path),
        stat.st_size,
        stat.st_mtime_ns,
    )


def _cached(
    key,
    produce,
):
    if key is None:
        return produce()

    with _probe_lock:
        cached = _probe_cache.get(key)

    if cached is not None:
        return cached

    value = produce()

    with _probe_lock:
        _probe_cache[key] = value

    return value


def duration(path: Path) -> float:
    """Return media duration from ffprobe; never infer it from filenames."""
    output = run([
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]).stdout.strip()

    try:
        return float(output)
    except ValueError:
        output = run([
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]).stdout.strip()

        try:
            return float(output)
        except ValueError:
            sys.exit(
                "[prompt2render] ffprobe reported no "
                f"usable duration for {path}"
            )


def frame_count(path: Path) -> int:
    """Return exact video packet/frame count."""
    def probe_frames() -> int:
        output = run([
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]).stdout.strip()

        return int(output)

    return _cached(
        _stamp(path, "frames"),
        probe_frames,
    )


def probe(path: Path) -> dict:
    """Return cached ffprobe JSON for a media file."""
    def do_probe() -> dict:
        return json.loads(
            run([
                "ffprobe",
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ]).stdout
        )

    return _cached(
        _stamp(path, "probe"),
        do_probe,
    )


def video_params(path: Path) -> dict:
    """Return video codec fields relevant to safe concat-copy."""
    info = probe(path)

    video = next(
        (
            stream
            for stream in info.get("streams", [])
            if stream.get("codec_type") == "video"
        ),
        None,
    )

    if video is None:
        sys.exit(
            f"[prompt2render] no video stream in {path}"
        )

    return {
        key: video.get(key)
        for key in (
            "codec_name",
            "profile",
            "level",
            "pix_fmt",
            "width",
            "height",
            "time_base",
            "sample_aspect_ratio",
            "field_order",
            "color_range",
        )
    }


# --------------------------------------------------------------- paths -----

def validate_slug(slug: str, *, exit_on_error: bool = True) -> str:
    """Validate project slug against directory traversal, illegal characters, and escape.

    Returns the validated slug string. Raises ValueError (or SystemExit if exit_on_error=True)
    if the slug is empty, malformed, or attempts to escape cfg.PROJECTS.
    """
    if not isinstance(slug, str):
        msg = f"[prompt2render] project slug must be a string, got {type(slug).__name__}"
        if exit_on_error:
            sys.exit(msg)
        raise ValueError(msg)

    clean_slug = slug.strip()
    if not clean_slug:
        msg = "[prompt2render] project slug cannot be empty"
        if exit_on_error:
            sys.exit(msg)
        raise ValueError(msg)

    # Strictly disallow path separators, traversal dots, colons, null bytes
    if any(sep in clean_slug for sep in ('/', '\\', '..', ':', '\0')):
        msg = f"[prompt2render] invalid project slug '{slug}': path traversal and separators are forbidden"
        if exit_on_error:
            sys.exit(msg)
        raise ValueError(msg)

    # Must be valid safe identifier: alphanumeric start, only [a-zA-Z0-9._-]
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$', clean_slug):
        msg = f"[prompt2render] invalid project slug '{slug}': must start with alphanumeric and contain only [a-zA-Z0-9._-]"
        if exit_on_error:
            sys.exit(msg)
        raise ValueError(msg)

    # Explicit boundary check
    target = (PROJECTS / clean_slug).resolve()
    try:
        target.relative_to(PROJECTS.resolve())
    except ValueError:
        msg = f"[prompt2render] invalid project slug '{slug}': escapes project directory"
        if exit_on_error:
            sys.exit(msg)
        raise ValueError(msg)

    return clean_slug


def slugify(text: str) -> str:
    """Convert arbitrary text into a safe, canonical project slug.

    Lowercases, replaces spaces and separators with hyphens, strips invalid
    characters, and trims leading/trailing non-alphanumerics.
    Ensures output conforms to validate_slug rules.
    """
    if not isinstance(text, str):
        text = str(text)
    clean = text.strip().lower()
    # Replace whitespace, underscores, and path separators with hyphens
    clean = re.sub(r"[\s_/\\]+", "-", clean)
    # Remove any character that is not alphanumeric, dot, or hyphen
    clean = re.sub(r"[^a-z0-9.-]", "", clean)
    # Collapse multiple consecutive hyphens
    clean = re.sub(r"-+", "-", clean)
    # Strip non-alphanumeric leading characters (e.g. leading dots or hyphens)
    clean = re.sub(r"^[^a-z0-9]+", "", clean)
    # Strip trailing dots or hyphens
    clean = re.sub(r"[.-]+$", "", clean)
    if not clean:
        clean = "project"
    return clean


def project_dir(slug: str) -> Path:
    clean_slug = validate_slug(slug)
    directory = PROJECTS / clean_slug

    if not directory.exists():
        sys.exit(
            f"[prompt2render] no project '{clean_slug}' — "
            "run: python prompt2render.py new "
            f"{clean_slug}"
        )

    return directory


def safe_subprocess_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a sanitized environment dictionary for subprocess execution of untrusted code.

    Preserves standard execution variables while stripping sensitive API keys, tokens,
    and passwords to prevent leakage to LLM-generated code.
    """
    safe_prefixes = (
        "PATH", "SYSTEM", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT",
        "PYTHON", "LANG", "LC_", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
        "HOME", "OS", "PROCESSOR", "NUMBER_OF_PROCESSORS", "TERM",
    )
    forbidden_substrings = ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH", "CREDENTIAL", "PRIVATE")

    sanitized: dict[str, str] = {}
    for k, v in os.environ.items():
        k_upper = k.upper()
        if any(sub in k_upper for sub in forbidden_substrings):
            continue
        if any(k_upper.startswith(prefix) for prefix in safe_prefixes):
            sanitized[k] = v

    if extra_env:
        for k, v in extra_env.items():
            k_upper = k.upper()
            if not any(sub in k_upper for sub in forbidden_substrings):
                sanitized[k] = v

    return sanitized


def say(message: str) -> None:
    print(
        f"[prompt2render] {message}",
        flush=True,
    )


def warn(message: str) -> None:
    print(
        f"[prompt2render] ! {message}",
        flush=True,
    )


__all__ = [
    "AUDIO_SR",
    "AAC_BITRATE",
    "CAPTION_CPS",
    "CAPTION_FONT",
    "CAPTION_FONT_SIZE",
    "CAPTION_LINE",
    "CAPTION_LINES",
    "CAPTION_MAX_S",
    "CAPTION_MIN_S",
    "CRF",
    "DEFAULT_MANIM_FONT",
    "FPS",
    "HEIGHT",
    "IS_WINDOWS",
    "LRA",
    "LUFS",
    "MODELS",
    "PROJECTS",
    "ROOT",
    "TTS_SR",
    "TRUE_PEAK",
    "VOPTS",
    "VOPTS_GPU",
    "VOPTS_PREVIEW",
    "VOPTS_PREVIEW_CPU",
    "WIDTH",
    "default_encode_jobs",
    "drawtext_font_arg",
    "duration",
    "env_float",
    "env_int",
    "filter_path",
    "font_file",
    "frame_count",
    "gpu_encode_available",
    "load_env",
    "need",
    "parallel",
    "pick_vopts",
    "probe",
    "probe_jobs",
    "project_dir",
    "run",
    "safe_subprocess_env",
    "say",
    "slugify",
    "stream_run",
    "try_run",
    "validate_slug",
    "video_params",
    "warn",
]