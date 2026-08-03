"""Kokoro-82M TTS backend (kokoro-onnx, no torch).

Reads model files from FDX_KOKORO_DIR (default <repo>/tools/kokoro) and
synthesises 24 kHz mono WAV from text with a named voice such as af_nicole.

The model is loaded once per process and reused across sections.
"""
from __future__ import annotations

import os
import sys
import wave
from pathlib import Path

import numpy as np

from . import cfg

KOKORO_DIR = Path(os.environ.get("FDX_KOKORO_DIR", "tools/kokoro")).expanduser()
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

_kokoro = None


def _load():
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    model = cfg.ROOT / KOKORO_DIR / MODEL_FILE
    voices = cfg.ROOT / KOKORO_DIR / VOICES_FILE
    if not model.exists() or not voices.exists():
        sys.exit(
            f"[fdx] kokoro model files not found under {cfg.ROOT / KOKORO_DIR}\n"
            "      download them from "
            "https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0\n"
            "      (kokoro-v1.0.onnx and voices-v1.0.bin)"
        )
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        sys.exit("[fdx] kokoro-onnx not installed — pip install kokoro-onnx")
    _kokoro = Kokoro(str(model), str(voices))
    return _kokoro


def synthesize(text: str, voice: str, speed: float, dst: Path) -> None:
    """Render narration to a 24 kHz 16-bit mono WAV."""
    k = _load()
    if voice not in k.get_voices():
        sys.exit(f"[fdx] kokoro voice '{voice}' not available. "
                 f"Pick one of: {', '.join(k.get_voices())}")
    audio, sr = k.create(text, voice=voice, speed=speed, lang="en-us")
    pcm = np.clip(audio, -1.0, 1.0)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((pcm * 32767.0).astype(np.int16).tobytes())
