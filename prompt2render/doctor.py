"""Preflight. The failure mode this replaces: run for ten minutes, then crash.

Every check here corresponds to something that used to fail late and opaquely
— a missing matplotlib surfacing as an ImportError inside generated code, a
font falling back and silently changing every frame's metrics, an ffmpeg build
without the whisper filter producing "No such filter" halfway through a build.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import asrmodel, cfg

OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.rows.append((status, name, detail))

    @property
    def failed(self) -> bool:
        return any(s == FAIL for s, _, _ in self.rows)

    def show(self) -> None:
        width = max(len(n) for _, n, _ in self.rows)
        for status, name, detail in self.rows:
            print(f"[{_MARK[status]}] {name.ljust(width)}  {detail}")


def _check_ffmpeg(r: Report) -> None:
    if shutil.which("ffmpeg") is None:
        r.add(FAIL, "ffmpeg", "not on PATH")
        return
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-version"])
    text = proc.stdout or ""
    ver = text.splitlines()[0].split()[2] if text else "?"

    if "--enable-whisper" in text:
        r.add(OK, "ffmpeg", f"{ver}, whisper filter built in")
    else:
        # Not fatal: alignment degrades to the exact synthesis boundaries,
        # which are already sample-accurate on the kokoro path.
        r.add(WARN, "ffmpeg", f"{ver}, no --enable-whisper — "
                              "word-level alignment unavailable")

    missing = [f for f in ("xfade", "loudnorm", "alimiter", "acompressor",
                           "deesser", "silencedetect", "aresample")
               if cfg.try_run(["ffmpeg", "-hide_banner", "-h",
                               f"filter={f}"]).returncode != 0]
    if missing:
        r.add(FAIL, "ffmpeg filters", f"missing: {', '.join(missing)}")
    else:
        r.add(OK, "ffmpeg filters", "xfade, loudnorm, alimiter, deesser, …")

    r.add(OK if shutil.which("ffprobe") else FAIL, "ffprobe",
          "" if shutil.which("ffprobe") else "not on PATH")

    # Check NVENC specifically
    if "h264_nvenc" in text or "hevc_nvenc" in text or cfg.try_run(["ffmpeg", "-hide_banner", "-h", "encoder=h264_nvenc"]).returncode == 0:
        # ffmpeg was built with NVENC. Does the hardware actually work?
        import os
        proc = cfg.try_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", 
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:r=30",
            "-frames:v", "30", "-c:v", "h264_nvenc", "-preset", "p1", "-profile:v", "main", "-bf", "0",
            "-pix_fmt", "yuv420p", "-f", "null", "-"
        ], timeout=15)
        if proc.returncode == 0:
            r.add(OK, "gpu encode", "h264_nvenc is hardware-accelerated and working")
        else:
            err = (proc.stderr or "").strip().splitlines()
            # Look for the actual error line, not just the generic "Nothing was written" warning
            real_err = next((line for line in err if "Error" in line or "failed" in line or "Unknown" in line or "Cannot" in line), None)
            if not real_err and err:
                real_err = err[-1]
            last_err = real_err if real_err else "unknown error"
            r.add(WARN, "gpu encode", f"ffmpeg has h264_nvenc, but hardware failed: {last_err}")
    else:
        r.add(WARN, "gpu encode", "ffmpeg build does not support NVENC (missing h264_nvenc)")


def _check_render(r: Report) -> None:
    try:
        import matplotlib
        import matplotlib.font_manager as fm
    except ImportError:
        r.add(FAIL, "matplotlib", "not installed — pip install -r requirements.txt")
        return
    r.add(OK, "matplotlib", matplotlib.__version__)

    # A silent font fallback changes the metrics of every frame the scene kit
    # draws, so the layout audit would be calibrated against the wrong thing.
    names = {f.name for f in fm.fontManager.ttflist}
    want = ["DejaVu Sans", "DejaVu Sans Mono"]
    absent = [w for w in want if w not in names]
    if absent:
        r.add(FAIL, "scene fonts", f"missing {', '.join(absent)} — layout "
                                   "would silently fall back")
    else:
        r.add(OK, "scene fonts", ", ".join(want))

    try:
        import numpy
        r.add(OK, "numpy", numpy.__version__)
    except ImportError:
        r.add(FAIL, "numpy", "not installed")


def _check_voice(r: Report) -> None:
    backend = os.environ.get("P2R_TTS_BACKEND", "kokoro")
    r.add(OK, "voice backend", backend)

    if backend != "kokoro":
        if backend == "edge" and shutil.which("edge-tts") is None:
            r.add(FAIL, "edge-tts", "not on PATH — pip install edge-tts")
        return

    kdir = cfg.ROOT / Path(os.environ.get("P2R_KOKORO_DIR", "tools/kokoro"))
    model = kdir / os.environ.get("P2R_KOKORO_MODEL", "kokoro-v1.0.onnx")
    voices = kdir / "voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        r.add(FAIL, "kokoro models", f"expected {model.name} and {voices.name} "
                                     f"under {kdir}")
        return
    try:
        import kokoro_onnx  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError as e:
        r.add(FAIL, "kokoro-onnx", f"not installed ({e.name})")
        return
    r.add(OK, "kokoro models", f"{model.name}, {voices.name}")

    want = os.environ.get("P2R_KOKORO_VOICE", "am_eric")
    try:
        from . import voice
        names = voice.voices()
    except Exception as e:                       # noqa: BLE001 — report, don't crash
        r.add(WARN, "kokoro load", f"{type(e).__name__}: {e}")
        return
    if want in names:
        r.add(OK, "kokoro voice", f"{want} ({len(names)} available)")
    else:
        r.add(FAIL, "kokoro voice", f"'{want}' not in {len(names)} voices — "
                                    "run: python prompt2render.py voices")


def _check_align(r: Report) -> None:
    name = os.environ.get("P2R_WHISPER_MODEL", "base.en")
    p = asrmodel.available(name)
    if p:
        r.add(OK, "ASR model", f"{p.name} ({p.stat().st_size/1e6:.0f} MB)")
    else:
        # Deliberately a warning: ranks 1-2 of the fallback chain are already
        # sample-exact without it.
        r.add(WARN, "ASR model", asrmodel.missing_note(name))


def _check_scenes(r: Report) -> None:
    if os.environ.get("GEMINI_API_KEY"):
        r.add(OK, "GEMINI_API_KEY", "set")
    else:
        r.add(WARN, "GEMINI_API_KEY", "unset — `prompt2render scenes` cannot run")
    try:
        import openai  # noqa: F401
        r.add(OK, "openai sdk", openai.__version__)
    except ImportError:
        r.add(FAIL, "openai sdk", "not installed — pip install openai")


def _check_optional(r: Report) -> None:
    try:
        import manim  # noqa: F401
    except ImportError:
        r.add(OK, "manim", "not installed (optional)")
        return
    latex = shutil.which("latex") or shutil.which("pdflatex")
    if latex:
        r.add(OK, "manim", "available with LaTeX")
    else:
        # Worth stating plainly: it is the difference between Manim being
        # useful for a maths channel and being decorative.
        r.add(WARN, "manim", "available, but no LaTeX — Text only, "
                             "MathTex/Tex will fail")


def _check_disk(r: Report) -> None:
    free = shutil.disk_usage(cfg.ROOT).free / 1e9
    r.add(OK if free >= 5 else WARN, "disk", f"{free:.1f} GB free")


def doctor() -> int:
    r = Report()
    _check_ffmpeg(r)
    _check_render(r)
    _check_voice(r)
    _check_align(r)
    _check_scenes(r)
    _check_optional(r)
    _check_disk(r)
    r.show()

    if r.failed:
        print("\n[prompt2render] blockers above must be fixed before a build will run.")
        return 1
    warns = sum(1 for s, _, _ in r.rows if s == WARN)
    print(f"\n[prompt2render] ready{f' ({warns} warning(s))' if warns else ''}.")
    return 0


def main() -> None:
    cfg.load_env()
    sys.exit(doctor())
