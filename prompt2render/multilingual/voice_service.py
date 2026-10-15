"""Configurable multilingual narration, TTS provider abstraction, and subtitle synchronization.

Supports:
- Local Kokoro TTS (for English and English-phoneme multilingual modes)
- Configurable external TTS providers / API bridges
- Subtitle (.srt / .ass) timestamp synchronization
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from .registry import LanguageRegistry


class TTSProvider(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    def synthesise_sentence(self, text: str, lang_code: str, voice: str | None = None) -> tuple[np.ndarray, int]:
        """Synthesise text into PCM float32 audio and sample rate."""
        pass


class KokoroTTSProvider(TTSProvider):
    """Local Kokoro neural voice synthesis provider."""

    def synthesise_sentence(self, text: str, lang_code: str, voice: str | None = None) -> tuple[np.ndarray, int]:
        from prompt2render import voice as voice_mod
        k = voice_mod.kokoro()
        chosen_voice = voice or "af_heart"
        pcm, sr = k.create(text, voice=chosen_voice, speed=1.0, lang="en-us")
        return np.asarray(pcm, dtype=np.float32), sr


class OnlineTTSProvider(TTSProvider):
    """Universal online neural TTS provider supporting Urdu, Hindi, Arabic, and other languages."""

    def synthesise_sentence(self, text: str, lang_code: str, voice: str | None = None) -> tuple[np.ndarray, int]:
        import subprocess
        import tempfile
        import urllib.parse
        import urllib.request
        from pathlib import Path
        import wave

        clean_text = text.strip()
        if not clean_text:
            return np.zeros(24000, dtype=np.float32), 24000

        # Map language codes
        target_tl = lang_code.split("-")[0].lower()
        if target_tl == "ks":
            # Perso-Arabic Kashmiri maps accurately to Urdu phonemes, Devanagari to Hindi
            if any(0x0900 <= ord(c) <= 0x097F for c in clean_text):
                target_tl = "hi"
            else:
                target_tl = "ur"
        encoded = urllib.parse.quote(clean_text)
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={target_tl}&client=tw-ob"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()

            with tempfile.TemporaryDirectory() as td:
                mp3_path = Path(td) / "audio.mp3"
                wav_path = Path(td) / "audio.wav"
                mp3_path.write_bytes(data)
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", str(mp3_path), "-ar", "24000", "-ac", "1", str(wav_path)],
                    check=True,
                    capture_output=True,
                )
                with wave.open(str(wav_path), "rb") as wf:
                    sr = wf.getframerate()
                    nframes = wf.getnframes()
                    raw = wf.readframes(nframes)
                    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                    return samples, sr
        except Exception:
            # Fallback to duration-scaled silence
            sr = 24000
            duration_s = max(1.5, len(clean_text.split()) * 0.45)
            samples = int(sr * duration_s)
            return np.zeros(samples, dtype=np.float32), sr


class MockTTSProvider(TTSProvider):
    """Lightweight test provider generating clean synthetic silence/tone."""

    def synthesise_sentence(self, text: str, lang_code: str, voice: str | None = None) -> tuple[np.ndarray, int]:
        # Generate 1.5 seconds of clean silence at 24000 Hz
        sr = 24000
        duration_s = max(1.0, len(text.split()) * 0.4)
        samples = int(sr * duration_s)
        pcm = np.zeros(samples, dtype=np.float32)
        return pcm, sr


class MultilingualVoiceManager:
    """Manages multi-language voice synthesis, provider fallback, and subtitle generation."""

    _ACTIVE_PROVIDER: TTSProvider | None = None

    @classmethod
    def get_provider(cls, lang_code: str = "en") -> TTSProvider:
        """Return the active or fallback TTS provider for the given language."""
        if cls._ACTIVE_PROVIDER is not None:
            return cls._ACTIVE_PROVIDER

        # Non-English languages default to OnlineTTSProvider
        clean_lang = lang_code.split("-")[0].lower()
        if clean_lang != "en":
            return OnlineTTSProvider()

        # Check if kokoro is available for English
        try:
            from prompt2render import voice as voice_mod
            model, voices = voice_mod._kokoro_paths()
            if model.exists() and voices.exists():
                cls._ACTIVE_PROVIDER = KokoroTTSProvider()
                return cls._ACTIVE_PROVIDER
        except Exception:
            pass

        return OnlineTTSProvider()

    @classmethod
    def set_provider(cls, provider: TTSProvider) -> None:
        """Set a custom TTS provider (e.g. for testing or cloud APIs)."""
        cls._ACTIVE_PROVIDER = provider

    @classmethod
    def generate_subtitles_srt(
        cls,
        cues: list[dict[str, Any]],
        output_file: Path | None = None,
    ) -> str:
        """Generate SRT subtitle file from timed cues."""
        def format_timestamp(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int(round((seconds - int(seconds)) * 1000))
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        srt_blocks = []
        for idx, cue in enumerate(cues, start=1):
            start_str = format_timestamp(cue["start"])
            end_str = format_timestamp(cue["end"])
            text = cue["text"].strip()
            srt_blocks.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")

        content = "\n".join(srt_blocks)
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(content, encoding="utf-8")
        return content
