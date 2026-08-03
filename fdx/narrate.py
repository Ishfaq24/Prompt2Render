"""Stage 2 - the voice. This is the stage Code2Video does not have,
and the reason a raw Code2Video upload dies on retention.

Two modes:
  own  - you record 01.wav, 02.wav ... into <project>/audio/ (best)
  tts  - synthesised from script.md. Backend selected by FDX_TTS_BACKEND:
         edge-tts (default) or kokoro (local Kokoro-82M, voice af_nicole,
         see fdx/kokoro_tts.py).

Either way the output is audio/NN.m4a, loudness-normalised to -14 LUFS,
which is what YouTube targets. Consistent loudness across your catalogue
is a small thing that quietly helps retention.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import cfg
from .project import Script, Section

RAW_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg")


def _normalise_audio(src: Path, dst: Path) -> None:
    cfg.run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,highpass=f=80",
        "-ar", "48000", "-ac", "1", "-c:a", "aac", "-b:a", "160k", str(dst),
    ])


def _find_own(audio_dir: Path, sec: Section) -> Path | None:
    for ext in RAW_EXTS:
        for name in (f"{sec.stem}{ext}", f"{sec.index}{ext}"):
            p = audio_dir / name
            if p.exists():
                return p
    return None


def _tts(text: str, dst_raw: Path, voice: str, rate: str, backend: str) -> None:
    if backend == "kokoro":
        from . import kokoro_tts
        kokoro_tts.synthesize(
            text, voice,
            speed=float(os.environ.get("FDX_KOKORO_SPEED", "1.0")),
            dst=dst_raw,
        )
        return
    if shutil.which("edge-tts") is None:
        raise SystemExit("[fdx] edge-tts not installed — pip install edge-tts, "
                         "or record your own audio into <project>/audio/")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(text)
        tmp = fh.name
    # NOTE: --rate takes values like "-4%". Passed as two argv items, argparse
    # inside edge-tts reads the leading "-" as a new flag and errors out, so
    # these must go over as a single "--rate=-4%" token.
    try:
        subprocess.run(
            ["edge-tts", f"--voice={voice}", f"--rate={rate}",
             f"--file={tmp}", f"--write-media={dst_raw}"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"[fdx] edge-tts failed:\n{(e.stderr or e.stdout or '')[-1500:]}")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def narrate(proj: Path, script: Script, force_tts: bool = False) -> list[Section]:
    cfg.need("ffmpeg", "ffprobe")
    audio_dir = proj / "audio"
    audio_dir.mkdir(exist_ok=True)
    backend = os.environ.get("FDX_TTS_BACKEND", "edge-tts")
    if backend == "kokoro":
        voice = os.environ.get("FDX_KOKORO_VOICE", "af_nicole")
        rate = ""  # kokoro uses FDX_KOKORO_SPEED instead
    else:
        voice = os.environ.get("FDX_TTS_VOICE", "en-IN-PrabhatNeural")
        rate = os.environ.get("FDX_TTS_RATE", "-4%")

    for sec in script.sections:
        dst = audio_dir / f"{sec.stem}.m4a"
        own = None if force_tts else _find_own(audio_dir, sec)

        if own and own != dst:
            cfg.say(f"section {sec.stem}: using your recording ({own.name})")
            _normalise_audio(own, dst)
        elif dst.exists() and not force_tts:
            cfg.say(f"section {sec.stem}: audio already built, skipping")
        else:
            if not sec.narration.strip():
                raise SystemExit(f"[fdx] section {sec.stem} has no narration text")
            cfg.say(f"section {sec.stem}: synthesising ({backend}:{voice})")
            # Stage the raw TTS in the system temp dir, not in the project.
            # Some mounts (network drives, synced folders) refuse unlink and
            # would otherwise leave .NN.raw.mp3 litter next to your audio.
            with tempfile.TemporaryDirectory(prefix="fdx-tts-") as td:
                raw = Path(td) / f"{sec.stem}.wav"
                _tts(sec.narration, raw, voice, rate, backend)
                _normalise_audio(raw, dst)

        sec.audio = dst
        sec.dur = cfg.duration(dst)

    total = sum(s.dur for s in script.sections)
    cfg.say(f"narration total: {total/60:.1f} min across {len(script.sections)} sections")
    if total < 480:
        cfg.say("NOTE: under 8 min. Watch-hours math gets much harder below this — "
                "consider adding a worked example section.")
    return script.sections
