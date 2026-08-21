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

#: CPU fallback for --preview on a machine where NVENC doesn't actually work
#: (see gpu_encode_available). Still optimised for speed over quality.
VOPTS_PREVIEW_CPU = [
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
    "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 5),
    "-x264-params", "scenecut=0",
]

#: GPU final encode via the NVENC ASIC, used in place of VOPTS whenever
#: gpu_encode_available() confirms the hardware actually works. Unlike
#: libx264, where a slower preset trades minutes of CPU time for quality,
#: NVENC's preset only controls search effort on a fixed-function chip --
#: p7 (best) costs nothing meaningful over p1 here, and its memory footprint
#: is well under a 2 GB card's budget regardless of resolution. So there is
#: no speed/quality trade to make: always ask for the best NVENC settings.
#: `cq` (not CRF) is NVENC's quality-target knob; low-20s is already called
#: "visually lossless" for Turing-generation NVENC (e.g. the MX350 this was
#: tuned on), so 18 leaves headroom. `-no-scenecut 1` mirrors the CPU
#: vector's `scenecut=0`: keep I-frames on the fixed, predictable period the
#: clip-head-dissolve scheme and concat demuxer both assume.
VOPTS_GPU = [
    "-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
    "-rc", "vbr", "-cq", "18", "-b:v", "0",
    "-maxrate", "20M", "-bufsize", "40M",
    "-multipass", "fullres",
    "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
    "-rc-lookahead", "32", "-bf", "3", "-b_ref_mode", "middle",
    "-no-scenecut", "1", "-profile:v", "high",
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
    `C:\\prompt2render\\x.bin` has to become `'C\\:/prompt2render/x.bin'` before it
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
        sys.exit(f"[prompt2render] {key} must be a number, got {raw!r}")


def env_int(key: str, default: int) -> int:
    return int(env_float(key, default))


# ------------------------------------------------------------ processes ---
def need(*binaries: str) -> None:
    missing = [b for b in binaries if shutil.which(b) is None]
    if missing:
        sys.exit(f"[prompt2render] missing required tool(s): {', '.join(missing)} — "
                 "run setup, then: python prompt2render.py doctor")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command, surfacing stderr on failure instead of swallowing it."""
    # errors="replace": ffmpeg and model logs carry non-cp1252 bytes that would
    # otherwise crash the decoder mid-run on Windows.
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)
    if proc.returncode != 0:
        sys.stderr.write((proc.stderr or "")[-4000:] + "\n")
        raise SystemExit(f"[prompt2render] command failed: {' '.join(cmd[:6])} ...")
    return proc


def try_run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Like run(), but a non-zero exit is the caller's problem, not fatal."""
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


_gpu_ok: bool | None = None


def gpu_encode_available() -> bool:
    """Whether h264_nvenc actually works right now -- not just whether ffmpeg
    lists it. ffmpeg advertises h264_nvenc whenever it was *built* with NVENC
    support, regardless of whether a GPU is present, the driver is new
    enough, or the GPU is currently in a healthy state -- all of which are
    the normal ways this fails in practice (an old driver reports an NVENC
    API version ffmpeg rejects; a GPU wedged after a TDR reports "lost" until
    the machine reboots). A real, tiny encode is the only trustworthy check.
    Cached: this runs at most once per process.
    """
    global _gpu_ok
    if _gpu_ok is None:
        try:
            proc = try_run([
                "ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
                "-i", "color=c=black:s=64x64:d=1:r=5",
                "-frames:v", "2", "-c:v", "h264_nvenc", "-f", "null", "-",
            ], timeout=15)
            _gpu_ok = proc.returncode == 0
        except Exception:
            _gpu_ok = False
    return _gpu_ok


def pick_vopts(preview: bool = False) -> list[str]:
    """The encoder vector for this run: GPU when it truly works, CPU otherwise.

    Call this once per encode *pass* (encode.py's whole todo list,
    assemble.py's whole section loop, ...) and reuse the result for every
    clip in it -- every clip that will later be joined with `-c copy` must
    share one byte-identical vector (see the cfg module docstring), so this
    must never be re-decided mid-pass.
    """
    if gpu_encode_available():
        return VOPTS_PREVIEW if preview else VOPTS_GPU
    if preview:
        warn("no working NVENC encoder found -- preview falling back to a "
             "fast CPU preset")
        return VOPTS_PREVIEW_CPU
    warn("no working NVENC encoder found -- encoding on CPU (libx264); "
         "this will be slower")
    return VOPTS


def default_encode_jobs() -> int:
    """How many clips to encode at once when --jobs isn't given explicitly.

    libx264 threads are CPU-bound, so more jobs just means more processes
    contending for the same cores the encoder already uses internally -- 1
    stays the safe default. NVENC is a separate fixed-function chip: a
    couple of clips in flight lets the CPU-side decode/filter work for clip
    N+1 overlap the GPU actually encoding clip N, instead of leaving the GPU
    idle between submissions.

    Measured, so that raising it is an informed choice rather than a guess:
    on a 1080p clip the per-frame x264 cost is ~27 ms and the fixed cost of
    the call -- process spawn, decoding the 6 MB PNG, initialising the xfade
    filter and the encoder -- is ~0.46 s. On a typical five-second clip that
    fixed part is only about a tenth of the call. It is the only part that
    cannot use a second core, so `--jobs 2` can recover at most that tenth,
    and only on a machine with cores x264 was not already using. That is why
    the default is 1 and why the advice is to time it rather than assume.

    Whatever you set, it cannot change a single byte of any clip: each ffmpeg
    process is independent and decides its own threading, so how many run at
    once is invisible to the bitstream. Verified by hashing the clips at
    --jobs 1 and --jobs 2.
    """
    return 3 if gpu_encode_available() else 1


def stream_run(cmd: list[str], **kw) -> int:
    """Run a command, printing its output live line by line."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **kw)
    if proc.stdout is not None:
        for line in proc.stdout:
            print(line, end="", flush=True)
    proc.wait()
    return proc.returncode


def parallel(fn, items: list, jobs: int, label: str = "") -> list:
    """Map `fn` over `items`, preserving order, `jobs` at a time.

    For subprocess fan-out only (ffprobe, ffmpeg): the child process is where
    the work happens and Python is only waiting on it, so threads give real
    concurrency here. Order is preserved because several callers compare the
    results positionally against `items`.
    """
    if not items:
        return []
    n = max(1, min(jobs, len(items)))
    if n == 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=n, thread_name_prefix=label or "prompt2render") as p:
        return list(p.map(fn, items))


def probe_jobs() -> int:
    """How many ffprobe calls to have in flight at once.

    Each one is a short-lived process that spends its life on file I/O, so
    this can sit comfortably above the core count -- the preflight in
    `prompt2render finish` is sixty of them back to back otherwise.
    """
    want = env_int("P2R_PROBE_JOBS", 0)
    return want if want > 0 else max(2, min(8, (os.cpu_count() or 2) * 2))


# -------------------------------------------------------------- ffprobe ---
#: (path, size, mtime_ns) -> parsed ffprobe output. A stage like `prompt2render check`
#: probes the same clip from three different gates; the file cannot change
#: underneath us mid-run, and an ffprobe is a whole process spawn.
_probe_cache: dict = {}
_probe_lock = threading.Lock()


def _stamp(path: Path, kind: str):
    try:
        st = path.stat()
    except OSError:
        return None
    return (kind, str(path), st.st_size, st.st_mtime_ns)


def _cached(key, produce):
    if key is None:
        return produce()
    with _probe_lock:
        hit = _probe_cache.get(key)
    if hit is not None:
        return hit
    val = produce()
    with _probe_lock:
        _probe_cache[key] = val
    return val


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
            sys.exit(f"[prompt2render] ffprobe reported no usable duration for {path}")


def frame_count(path: Path) -> int:
    """Exact video frame count. Counts packets — no rounding from duration."""
    def go() -> int:
        out = run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_packets", "-show_entries", "stream=nb_read_packets",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ]).stdout.strip()
        return int(out)
    return _cached(_stamp(path, "frames"), go)


def probe(path: Path) -> dict:
    def go() -> dict:
        return json.loads(run([
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(path),
        ]).stdout)
    return _cached(_stamp(path, "probe"), go)


def video_params(path: Path) -> dict:
    """The codec fields that must match across clips for a safe concat."""
    info = probe(path)
    v = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    if v is None:
        sys.exit(f"[prompt2render] no video stream in {path}")
    return {k: v.get(k) for k in (
        "codec_name", "profile", "level", "pix_fmt", "width", "height",
        "time_base", "sample_aspect_ratio", "field_order", "color_range",
    )}


# --------------------------------------------------------------- paths ----
def project_dir(slug: str) -> Path:
    d = PROJECTS / slug
    if not d.exists():
        sys.exit(f"[prompt2render] no project '{slug}' — run:  python prompt2render.py new {slug}")
    return d


def say(msg: str) -> None:
    print(f"[prompt2render] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[prompt2render] ! {msg}", flush=True)
