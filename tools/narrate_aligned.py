"""Narrate a section and keep the timings edge-tts already knows.

fdx's own narrate throws away the one thing that makes real sync possible: the
synthesiser knows exactly when it said each sentence. Asking for
--write-subtitles alongside the audio costs nothing and gives us a measured
timeline, which then drives both the captions and the moment each visual
appears. Everything downstream stops guessing.

    python tools/narrate_aligned.py <slug> [--only 03] [--force]

Writes audio/NN.m4a as usual, plus build/align/NN.json:
    [{"start": 0.1, "end": 4.5, "text": "..."}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fdx import cfg, narrate  # noqa: E402
from fdx.project import parse_script  # noqa: E402

TS = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->\s*"
                r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)")


def _secs(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: pathlib.Path):
    """Parse by blank-line-separated blocks.

    Scanning line by line and treating everything after a timestamp as text
    swallows the *next* block's index number, which then rides along on the end
    of the caption. Blocks are unambiguous.
    """
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].isdigit():          # drop the sequence number
            lines = lines[1:]
        if not lines:
            continue
        m = TS.search(lines[0])
        if not m:
            continue
        g = m.groups()
        text = " ".join(lines[1:]).strip()
        if text:
            cues.append({"start": _secs(*g[:4]), "end": _secs(*g[4:]),
                         "text": text})

    # edge-tts sometimes emits a cue that starts a hair before the previous
    # one ends; make the timeline strictly monotonic so later maths is safe.
    for i in range(1, len(cues)):
        if cues[i]["start"] < cues[i - 1]["end"]:
            mid = (cues[i]["start"] + cues[i - 1]["end"]) / 2
            cues[i - 1]["end"] = cues[i]["start"] = mid
    return [c for c in cues if c["text"]]


def synth(text, voice, rate, m4a_dst, align_dst):
    with tempfile.TemporaryDirectory(prefix="fdx-align-") as td:
        td = pathlib.Path(td)
        txt, mp3, srt = td / "n.txt", td / "n.mp3", td / "n.srt"
        txt.write_text(text, encoding="utf-8")
        proc = subprocess.run(
            ["edge-tts", f"--voice={voice}", f"--rate={rate}",
             f"--file={txt}", f"--write-media={mp3}", f"--write-subtitles={srt}"],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"[align] edge-tts failed:\n{proc.stderr[-800:]}")
        narrate._normalise_audio(mp3, m4a_dst)
        cues = parse_srt(srt)

    # Normalising re-times slightly; rescale cues onto the real audio length
    # so the last cue always lands exactly on the end of the track.
    adur = cfg.duration(m4a_dst)
    if cues:
        span = cues[-1]["end"]
        if span > 0:
            k = adur / span
            for c in cues:
                c["start"] *= k
                c["end"] *= k
        cues[-1]["end"] = adur
    align_dst.write_text(json.dumps(cues, indent=2), encoding="utf-8")
    return adur, len(cues)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--only", help="section stem, e.g. 03")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    cfg.load_env()
    cfg.need("ffmpeg", "ffprobe")
    proj = cfg.project_dir(a.slug)
    script = parse_script(proj / "script.md")
    (proj / "audio").mkdir(exist_ok=True)
    aligndir = proj / "build" / "align"
    aligndir.mkdir(parents=True, exist_ok=True)

    voice = os.environ.get("FDX_TTS_VOICE", "en-IN-PrabhatNeural")
    rate = os.environ.get("FDX_TTS_RATE", "-4%")

    for sec in script.sections:
        if a.only and sec.stem != a.only:
            continue
        m4a = proj / "audio" / f"{sec.stem}.m4a"
        al = aligndir / f"{sec.stem}.json"
        if m4a.exists() and al.exists() and not a.force:
            cfg.say(f"section {sec.stem}: already aligned, skipping")
            continue
        cfg.say(f"section {sec.stem}: synthesising + aligning ({voice})")
        dur, n = synth(sec.narration, voice, rate, m4a, al)
        cfg.say(f"  {dur:.1f}s across {n} measured cues")


if __name__ == "__main__":
    main()
