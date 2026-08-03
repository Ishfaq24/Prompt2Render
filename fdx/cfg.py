"""Shared config, paths and small subprocess helpers.

Everything that more than one stage needs to agree on lives here. In
particular VOPTS: MP4 stores SPS/PPS out of band in `avcC`, and the concat
demuxer with `-c copy` takes that extradata from the *first* input only. So
every clip in a project must be encoded with a byte-identical settings vector
or the result decodes wrong on some players. One definition, no per-stage
variation.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
MODELS = ROOT / "models"

# ---------------------------------------------------------------- video ----
WIDTH, HEIGHT, FPS = 1920, 1080, 30
CRF = "20"

#: The one encoder settings vector. See the module docstring for why this is
#: not per-stage. `-tune stillimage` is deliberately absent: it would have to
#: be dropped for motion clips, and a mixed vector is exactly the failure this
#: constant exists to prevent. At CRF 20 the loss on a static frame is nil.
VOPTS = [
    "-c:v", "libx264", "-crf", CRF, "-preset", "veryfast",
    "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 5),
    "-x264-params", "scenecut=0",
]

#: Fast preview encoder. Only ever used for `--preview`; never for a clip that
#: will be concatenated with a libx264 one.
VOPTS_PREVIEW = [
    "-c:v", "h264_nvenc", "-preset", "p1", "-cq", "28",
    "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 5),
]

# ---------------------------------------------------------------- audio ----
AUDIO_SR = 48000          # delivery sample rate
TTS_SR = 24000            # what Kokoro emits
AAC_BITRATE = "192k"
LUFS = -14.0              # YouTube's target; matches the published catalogue
TRUE_PEAK = -1.5
LRA = 9.0

# ------------------------------------------------------------- timing -----
PAUSE_SENTENCE_MS = 320
PAUSE_QUESTION_MS = 380
PAUSE_CLAUSE_MS = 120
PAUSE_PARAGRAPH_MS = 650
VISUAL_LEAD_MS = 120      # cut this far *before* the word; landing after reads sloppy

# ------------------------------------------------------------- captions ---
CAPTION_LINE = 42         # broadcast norm, not the old 84
CAPTION_LINES = 2
CAPTION_MIN_S = 0.833
CAPTION_MAX_S = 7.0
CAPTION_CPS = 20.0

# libass has no font discovery guarantee across platforms; pick one that exists.
CAPTION_FONT = "Arial" if IS_WINDOWS else "DejaVu Sans"

# drawtext needs a real font file when fontconfig isn't wired up — which is the
# normal state of the Windows ffmpeg builds. Resolve one once, here, so a
# missing font shows up as a clear message instead of an ffmpeg filter error.
_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)


def font_file() -> str | None:
    """Absolute path to a usable TTF, or None to let fontconfig try."""
    for c in _FONT_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def filter_path(p: Path | str) -> str:
    """A filesystem path, quoted and escaped for use *inside* a filtergraph.

    Inside a filtergraph ':' separates options and '\\' is an escape, so
    `C:\\fdx-studio\\x.bin` has to become `'C\\:/fdx-studio/x.bin'` before it
    can be handed to whisper's `model=`, subtitles' filename, and so on.
    Windows drive letters in a filtergraph are a guaranteed bug otherwise.
    """
    s = str(p).replace("\\", "/").replace(":", r"\:")
    return f"'{s}'"


def drawtext_font_arg() -> str:
    """The `fontfile=...` fragment for a drawtext filter, escaped for ffmpeg."""
    f = font_file()
    if not f:
        return ""
    return f"fontfile={filter_path(f)}:"


# ------------------------------------------------------------------ env ---
def load_env(path: Path | None = None) -> None:
    """Minimal .env loader so we don't need python-dotenv at import time."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        sys.exit(f"[fdx] {key} must be a number, got {raw!r}")


def env_int(key: str, default: int) -> int:
    return int(env_float(key, default))


# ------------------------------------------------------------ processes ---
def need(*binaries: str) -> None:
    missing = [b for b in binaries if shutil.which(b) is None]
    if missing:
        sys.exit(f"[fdx] missing required tool(s): {', '.join(missing)} — "
                 "run setup, then: python fdx.py doctor")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command, surfacing stderr on failure instead of swallowing it."""
    # errors="replace": ffmpeg and model logs carry non-cp1252 bytes that would
    # otherwise crash the decoder mid-run on Windows.
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or "")[-4000:] + "\n")
        raise SystemExit(f"[fdx] command failed: {' '.join(cmd[:6])} ...")
    return proc


def try_run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Like run(), but a non-zero exit is the caller's problem, not fatal."""
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def stream_run(cmd: list[str], **kw) -> int:
    """Run a command, printing its output live line by line."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **kw)
    if proc.stdout is not None:
        for line in proc.stdout:
            print(line, end="", flush=True)
    proc.wait()
    return proc.returncode


# -------------------------------------------------------------- ffprobe ---
def duration(path: Path) -> float:
    """Duration in seconds via ffprobe. Never guess this."""
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]).stdout.strip()
    try:
        return float(out)
    except ValueError:
        # Some containers carry no format-level duration. Fall back to the
        # stream, and fail with a path rather than a bare ValueError.
        out = run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ]).stdout.strip()
        try:
            return float(out)
        except ValueError:
            sys.exit(f"[fdx] ffprobe reported no usable duration for {path}")


def frame_count(path: Path) -> int:
    """Exact video frame count. Counts packets — no rounding from duration."""
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_packets", "-show_entries", "stream=nb_read_packets",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]).stdout.strip()
    return int(out)


def probe(path: Path) -> dict:
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]).stdout
    return json.loads(out)


def video_params(path: Path) -> dict:
    """The codec fields that must match across clips for a safe concat."""
    info = probe(path)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if v is None:
        sys.exit(f"[fdx] no video stream in {path}")
    return {k: v.get(k) for k in (
        "codec_name", "profile", "level", "pix_fmt", "width", "height",
        "time_base", "sample_aspect_ratio", "field_order", "color_range",
    )}


# --------------------------------------------------------------- paths ----
def project_dir(slug: str) -> Path:
    d = PROJECTS / slug
    if not d.exists():
        sys.exit(f"[fdx] no project '{slug}' — run:  python fdx.py new {slug}")
    return d


def say(msg: str) -> None:
    print(f"[fdx] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[fdx] ! {msg}", flush=True)
