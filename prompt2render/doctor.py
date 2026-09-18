"""Preflight checks for prompt2render.

The doctor command is deliberately front-loaded: validate the external tools,
rendering stack, voice backend, alignment model, LLM access, optional tooling,
and disk space before an expensive build starts.

Warnings represent degraded-but-runnable paths. Failures represent missing
hard prerequisites.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import asrmodel, cfg, manimver


OK, WARN, FAIL = "ok", "warn", "fail"
_MARK = {
    OK: "  ok  ",
    WARN: " warn ",
    FAIL: " FAIL ",
}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(
        self,
        status: str,
        name: str,
        detail: str = "",
    ) -> None:
        if status not in _MARK:
            raise ValueError(
                f"invalid report status: {status!r}"
            )
        self.rows.append(
            (status, name, detail)
        )

    @property
    def failed(self) -> bool:
        return any(
            status == FAIL
            for status, _, _ in self.rows
        )

    def show(self) -> None:
        if not self.rows:
            return

        width = max(
            len(name)
            for _, name, _ in self.rows
        )

        for status, name, detail in self.rows:
            suffix = (
                f"  {detail}"
                if detail
                else ""
            )
            print(
                f"[{_MARK[status]}] "
                f"{name.ljust(width)}{suffix}"
            )


def _ffmpeg_version() -> str:
    proc = cfg.try_run([
        "ffmpeg",
        "-hide_banner",
        "-version",
    ])

    text = (
        proc.stdout
        or proc.stderr
        or ""
    )

    first = next(
        (
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ),
        "",
    )

    parts = first.split()
    return (
        parts[2]
        if len(parts) >= 3
        else "?"
    )


def _has_filter(name: str) -> bool:
    """Check whether FFmpeg exposes a filter by name."""
    proc = cfg.try_run([
        "ffmpeg",
        "-hide_banner",
        "-filters",
    ])

    if proc.returncode != 0:
        return False

    for line in (
        proc.stdout or ""
    ).splitlines():
        fields = line.split()

        # Typical output contains:
        # "... T.C xfade ..."
        # "... A.C loudnorm ..."
        if len(fields) >= 2 and fields[-1] == name:
            return True

        # Be tolerant of FFmpeg formatting changes.
        if any(
            field == name
            for field in fields
        ):
            return True

    return False


def _check_ffmpeg(r: Report) -> None:
    if shutil.which("ffmpeg") is None:
        r.add(
            FAIL,
            "ffmpeg",
            "not on PATH",
        )
        return

    version = _ffmpeg_version()

    # FFmpeg builds differ in how configuration flags are exposed. Check both
    # the version configuration line and the actual filter inventory.
    version_proc = cfg.try_run([
        "ffmpeg",
        "-hide_banner",
        "-version",
    ])
    version_text = (
        version_proc.stdout
        or version_proc.stderr
        or ""
    )

    whisper_built = (
        "--enable-whisper" in version_text
        or _has_filter("whisper")
    )

    if whisper_built:
        r.add(
            OK,
            "ffmpeg",
            f"{version}, whisper filter built in",
        )
    else:
        r.add(
            WARN,
            "ffmpeg",
            f"{version}, no whisper filter — "
            "word-level alignment unavailable",
        )

    required_filters = (
        "xfade",
        "loudnorm",
        "alimiter",
        "acompressor",
        "deesser",
        "silencedetect",
        "aresample",
    )

    missing = [
        name
        for name in required_filters
        if not _has_filter(name)
    ]

    if missing:
        r.add(
            FAIL,
            "ffmpeg filters",
            f"missing: {', '.join(missing)}",
        )
    else:
        r.add(
            OK,
            "ffmpeg filters",
            "xfade, loudnorm, alimiter, deesser, "
            "silencedetect, aresample",
        )

    ffprobe_ok = (
        shutil.which("ffprobe") is not None
    )

    r.add(
        OK if ffprobe_ok else FAIL,
        "ffprobe",
        "" if ffprobe_ok else "not on PATH",
    )

    # Do not duplicate the NVENC probe here. cfg.gpu_encode_available()
    # performs the authoritative hardware test and is also what the encoder
    # selection path uses, so doctor and the actual build cannot disagree
    # because they tested different encoder arguments.
    has_nvenc = (
        _has_encoder("h264_nvenc")
    )

    if not has_nvenc:
        r.add(
            WARN,
            "gpu encode",
            "ffmpeg build does not support "
            "h264_nvenc",
        )
        return

    if cfg.gpu_encode_available():
        r.add(
            OK,
            "gpu encode",
            "h264_nvenc probe succeeded; "
            "NVENC is usable",
        )
    else:
        reason = (
            getattr(cfg, "_gpu_error", None)
            or "hardware/driver initialization failed"
        )
        r.add(
            WARN,
            "gpu encode",
            "ffmpeg has h264_nvenc, but "
            f"hardware failed: {reason}",
        )


def _has_encoder(name: str) -> bool:
    proc = cfg.try_run([
        "ffmpeg",
        "-hide_banner",
        "-h",
        f"encoder={name}",
    ])
    return proc.returncode == 0


def _check_render(r: Report) -> None:
    try:
        import matplotlib
        import matplotlib.font_manager as fm
    except ImportError:
        r.add(
            FAIL,
            "matplotlib",
            "not installed — "
            "pip install -r requirements.txt",
        )
        return

    r.add(
        OK,
        "matplotlib",
        matplotlib.__version__,
    )

    # The scene-kit layout audit depends on stable font metrics. A missing
    # expected font should therefore be visible before generation starts.
    names = {
        font.name
        for font in fm.fontManager.ttflist
    }

    wanted = (
        "DejaVu Sans",
        "DejaVu Sans Mono",
    )

    absent = [
        font
        for font in wanted
        if font not in names
    ]

    if absent:
        r.add(
            FAIL,
            "scene fonts",
            f"missing {', '.join(absent)} — "
            "layout would silently fall back",
        )
    else:
        r.add(
            OK,
            "scene fonts",
            ", ".join(wanted),
        )

    try:
        import numpy
        r.add(
            OK,
            "numpy",
            numpy.__version__,
        )
    except ImportError:
        r.add(
            FAIL,
            "numpy",
            "not installed",
        )


def _check_voice(r: Report) -> None:
    backend = os.environ.get(
        "P2R_TTS_BACKEND",
        "kokoro",
    ).strip().lower()

    r.add(
        OK,
        "voice backend",
        backend,
    )

    if backend != "kokoro":
        if (
            backend == "edge"
            and shutil.which("edge-tts") is None
        ):
            r.add(
                FAIL,
                "edge-tts",
                "not on PATH — "
                "pip install edge-tts",
            )
        return

    kokoro_dir = (
        cfg.ROOT
        / Path(
            os.environ.get(
                "P2R_KOKORO_DIR",
                "tools/kokoro",
            )
        )
    )

    model = (
        kokoro_dir
        / os.environ.get(
            "P2R_KOKORO_MODEL",
            "kokoro-v1.0.onnx",
        )
    )

    voices = (
        kokoro_dir
        / "voices-v1.0.bin"
    )

    missing = [
        path.name
        for path in (model, voices)
        if not path.exists()
    ]

    if missing:
        r.add(
            FAIL,
            "kokoro models",
            f"missing {', '.join(missing)} "
            f"under {kokoro_dir}",
        )
        return

    try:
        import kokoro_onnx  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError as exc:
        r.add(
            FAIL,
            "kokoro-onnx",
            f"not installed ({getattr(exc, 'name', exc)})",
        )
        return

    r.add(
        OK,
        "kokoro models",
        f"{model.name}, {voices.name}",
    )

    wanted_voice = os.environ.get(
        "P2R_KOKORO_VOICE",
        "am_eric",
    )

    try:
        from . import voice

        available_voices = voice.voices()
    except Exception as exc:  # noqa: BLE001
        r.add(
            WARN,
            "kokoro load",
            f"{type(exc).__name__}: {exc}",
        )
        return

    if wanted_voice in available_voices:
        r.add(
            OK,
            "kokoro voice",
            f"{wanted_voice} "
            f"({len(available_voices)} available)",
        )
    else:
        r.add(
            FAIL,
            "kokoro voice",
            f"'{wanted_voice}' not in "
            f"{len(available_voices)} voices — "
            "run: python prompt2render.py voices",
        )


def _check_align(r: Report) -> None:
    name = os.environ.get(
        "P2R_WHISPER_MODEL",
        "base.en",
    )

    model = asrmodel.available(name)

    if model:
        r.add(
            OK,
            "ASR model",
            f"{model.name} "
            f"({model.stat().st_size / 1e6:.0f} MB)",
        )
    else:
        # Alignment is deliberately optional. The downstream pipeline can
        # still use the deterministic synthesis/sample clock.
        r.add(
            WARN,
            "ASR model",
            asrmodel.missing_note(name),
        )


def _check_scenes(r: Report) -> None:
    from . import llm

    active_endpoint = llm.endpoint()
    is_gemini_default = active_endpoint == llm.ENDPOINT
    endpoint_label = "Google Gemini (default)" if is_gemini_default else active_endpoint

    r.add(
        OK,
        "LLM endpoint",
        endpoint_label,
    )

    has_key = bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or os.environ.get("P2R_LLM_API_KEY", "").strip()
    )
    is_local = any(h in active_endpoint.lower() for h in ("localhost", "127.0.0.1", "0.0.0.0"))

    if has_key:
        r.add(
            OK,
            "LLM API key",
            "set",
        )
    elif is_local:
        r.add(
            OK,
            "LLM API key",
            "not required (local endpoint)",
        )
    else:
        r.add(
            WARN,
            "LLM API key",
            "unset — GEMINI_API_KEY or OPENAI_API_KEY needed for scene generation",
        )

    try:
        import openai

        r.add(
            OK,
            "openai sdk",
            getattr(
                openai,
                "__version__",
                "installed",
            ),
        )
    except ImportError:
        r.add(
            FAIL,
            "openai sdk",
            "not installed — pip install openai",
        )

    # F15: llm.py previously exposed no temperature/seed control at all.
    # Unset (the default) is not a warning — most builds want the
    # provider's normal creative variation; this just makes the opt-in
    # visible for anyone running a reproducibility-focused build.
    temperature = os.environ.get("P2R_LLM_TEMPERATURE", "").strip()
    seed = os.environ.get("P2R_LLM_SEED", "").strip()

    r.add(
        OK,
        "LLM temperature",
        f"{temperature} (fixed)" if temperature else "unset (provider default)",
    )
    r.add(
        OK,
        "LLM seed",
        f"{seed} (best-effort determinism)" if seed else "unset",
    )


def _check_optional(r: Report) -> None:
    try:
        import cv2

        r.add(
            OK,
            "opencv (cv2)",
            cv2.__version__,
        )
    except ImportError:
        r.add(
            WARN,
            "opencv (cv2)",
            "not installed — observer_visual (Tier 3 Phase 11, "
            "--manim only) will report skip for every stem",
        )


def _check_manim(r: Report) -> None:
    target, installed, matches = manimver.status()

    if installed is None:
        r.add(
            OK,
            "manim",
            f"not installed (optional — target is {target})",
        )
        return

    if matches:
        r.add(
            OK,
            "manim",
            f"{installed} (matches target {target})",
        )
    else:
        # WARN, not FAIL: manim only drives the optional --manim backend
        # and the `prompt2render manim` escape hatch, matching this
        # function's existing "degraded but runnable" treatment of the
        # LaTeX check below. Any actual render call still hard-fails on
        # this mismatch (see visuals.manim_scene / scenes._render_manim)
        # so a stale install can't silently produce wrong-API renders.
        r.add(
            WARN,
            "manim",
            f"{installed} installed, but this build targets {target} — "
            f'pip install "manim=={target}" (or set '
            f"P2R_MANIM_VERSION={installed} to declare that version "
            "intentionally)",
        )

    latex = (
        shutil.which("latex")
        or shutil.which("pdflatex")
    )

    if latex:
        r.add(
            OK,
            "manim LaTeX",
            "available",
        )
    else:
        r.add(
            WARN,
            "manim LaTeX",
            "not available — Text only; MathTex/Tex will fail",
        )


def _check_render_test(r: Report) -> None:
    target, installed, matches = manimver.status()

    if installed is None:
        r.add(FAIL, "manim render test", "manim is not installed")
        return

    if not matches:
        r.add(
            FAIL,
            "manim render test",
            f"skipped — installed {installed} does not match target {target}",
        )
        return

    import tempfile

    from . import manim_smoke

    try:
        with tempfile.TemporaryDirectory(prefix="p2r-manim-smoke-") as tmp:
            clip = manim_smoke.render_smoke_scene(Path(tmp))
            info = manim_smoke.probe_clip(clip)
    except Exception as exc:  # noqa: BLE001 - surface any failure as a doctor row
        r.add(FAIL, "manim render test", f"render failed: {exc}")
        return

    ok = (
        info["width"] == cfg.WIDTH
        and info["height"] == cfg.HEIGHT
        and abs(info["fps"] - cfg.FPS) < 0.01
        and info["size_bytes"] > 10_000
    )
    detail = (
        f"{info['width']}x{info['height']} @ {info['fps']:.2f}fps, "
        f"{info['size_bytes'] / 1024:.0f} KB"
    )
    r.add(OK if ok else FAIL, "manim render test", detail)


def _check_disk(r: Report) -> None:
    try:
        free = (
            shutil.disk_usage(cfg.ROOT).free
            / 1e9
        )
    except OSError as exc:
        r.add(
            WARN,
            "disk",
            f"could not determine free space: {exc}",
        )
        return

    # 5 GB is the minimum warning threshold retained from the original
    # preflight. Large renders can consume considerably more, so expose the
    # exact free space rather than hiding it behind a boolean.
    r.add(
        OK if free >= 5 else WARN,
        "disk",
        f"{free:.1f} GB free",
    )


def doctor(render_test: bool = False) -> int:
    r = Report()

    _check_ffmpeg(r)
    _check_render(r)
    _check_voice(r)
    _check_align(r)
    _check_scenes(r)
    _check_optional(r)
    _check_manim(r)
    if render_test:
        _check_render_test(r)
    _check_disk(r)

    r.show()

    if r.failed:
        print(
            "\n[prompt2render] blockers above must be "
            "fixed before a build will run."
        )
        return 1

    warnings = sum(
        status == WARN
        for status, _, _ in r.rows
    )

    suffix = (
        f" ({warnings} warning(s))"
        if warnings
        else ""
    )

    print(
        f"\n[prompt2render] ready{suffix}."
    )
    return 0


def main() -> None:
    cfg.load_env()
    render_test = "--render-test" in sys.argv[1:]
    sys.exit(doctor(render_test=render_test))


__all__ = [
    "FAIL",
    "OK",
    "WARN",
    "Report",
    "doctor",
    "main",
]


if __name__ == "__main__":
    main()