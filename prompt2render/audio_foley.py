"""Procedural Audio Foley Synthesizer for kinetic animation sound cues.

Generates zero-dependency, pure-math synthesized acoustic sound design:
- Whoosh: smooth kinetic transitions (Transform, MoveTo).
- Pop: discrete node and element appearances (Create, Dot, Card).
- Chime: harmonic highlight and emphasis (Indicate, Circumscribe, Highlight).
- Click: fast mechanical key/step cues (Write, next_step).
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Sequence


def synthesize_tone(
    freq_start: float,
    freq_end: float,
    duration_s: float,
    *,
    sample_rate: int = 48000,
    volume: float = 0.25,
    harmonic_ratio: float = 0.0,
) -> bytes:
    """Synthesize a frequency-modulated waveform with smooth Hann window envelope."""
    num_samples = int(sample_rate * duration_s)
    raw_bytes = bytearray()
    phase = 0.0

    for i in range(num_samples):
        progress = i / max(1, num_samples - 1)
        envelope = 0.5 * (1.0 - math.cos(2.0 * math.pi * progress))
        curr_freq = freq_start + (freq_end - freq_start) * progress
        phase += 2.0 * math.pi * curr_freq / sample_rate

        sample = math.sin(phase)
        if harmonic_ratio > 0.0:
            sample += harmonic_ratio * math.sin(phase * 2.0)

        sample = sample * envelope * volume
        int_sample = max(-32767, min(32767, int(sample * 32767.0)))
        raw_bytes.extend(struct.pack("<h", int_sample))

    return bytes(raw_bytes)


def make_whoosh(duration_s: float = 0.16, sample_rate: int = 48000, volume: float = 0.20) -> bytes:
    """Stereo-compatible pitch whoosh for motion transitions."""
    return synthesize_tone(180.0, 480.0, duration_s, sample_rate=sample_rate, volume=volume)


def make_pop(duration_s: float = 0.07, sample_rate: int = 48000, volume: float = 0.25) -> bytes:
    """Gentle downward pitch pop for object creation."""
    return synthesize_tone(360.0, 90.0, duration_s, sample_rate=sample_rate, volume=volume)


def make_chime(duration_s: float = 0.18, sample_rate: int = 48000, volume: float = 0.18) -> bytes:
    """Harmonic chime for highlights and indicators."""
    return synthesize_tone(784.0, 880.0, duration_s, sample_rate=sample_rate, volume=volume, harmonic_ratio=0.4)


def make_click(duration_s: float = 0.04, sample_rate: int = 48000, volume: float = 0.22) -> bytes:
    """Sharp subtle transient for code typing and discrete states."""
    return synthesize_tone(600.0, 200.0, duration_s, sample_rate=sample_rate, volume=volume)


FOLEY_PRESETS = {
    "whoosh": make_whoosh,
    "pop": make_pop,
    "chime": make_chime,
    "click": make_click,
    "Create": make_pop,
    "Write": make_click,
    "FadeIn": make_pop,
    "Transform": make_whoosh,
    "MoveTo": make_whoosh,
    "Highlight": make_chime,
    "Circumscribe": make_chime,
    "Indicate": make_chime,
    "pulse_signal": make_chime,
    "signal": make_chime,
    "cognitive_cue": make_chime,
}


def render_foley_track(
    events: Sequence[tuple[float, str]],
    total_duration_s: float,
    output_wav: Path,
    *,
    sample_rate: int = 48000,
) -> Path:
    """Render a timeline of (timestamp_s, cue_type) into a single 16-bit mono WAV file."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    total_samples = int(total_duration_s * sample_rate)
    buffer = [0.0] * total_samples

    for timestamp, cue_type in events:
        start_sample = int(timestamp * sample_rate)
        if start_sample >= total_samples:
            continue

        generator = FOLEY_PRESETS.get(cue_type, make_pop)
        cue_bytes = generator(sample_rate=sample_rate)
        num_cue_samples = len(cue_bytes) // 2
        for idx in range(num_cue_samples):
            target_idx = start_sample + idx
            if target_idx < total_samples:
                sample_val = struct.unpack_from("<h", cue_bytes, idx * 2)[0] / 32767.0
                buffer[target_idx] += sample_val

    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        packed = bytearray()
        for sample in buffer:
            clamped = max(-1.0, min(1.0, sample))
            packed.extend(struct.pack("<h", int(clamped * 32767.0)))
        wf.writeframes(packed)

    return output_wav


def extract_foley_events_from_code(
    code_text: str,
    total_duration_s: float = 10.0,
    *,
    offset_s: float = 0.0,
) -> list[tuple[float, str]]:
    """Extract chronological animation acoustic events from scene code."""
    import re

    # Match animation constructor calls inside scene source
    matches = re.findall(
        r"\b(Create|Write|FadeIn|Transform|ReplacementTransform|MoveTo|Indicate|Circumscribe|Highlight|pulse_signal)\b",
        code_text,
    )
    if not matches:
        return []

    events: list[tuple[float, str]] = []
    step_duration = max(0.2, (total_duration_s - 0.6) / max(1, len(matches)))
    for i, anim_name in enumerate(matches):
        ts = round(offset_s + 0.3 + i * step_duration, 2)
        events.append((ts, anim_name))

    return events
