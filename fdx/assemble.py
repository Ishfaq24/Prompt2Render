"""Legacy assembly, kept for clips that genuinely have no cue structure.

This is the right tool for `fdx import`ed footage: it runs to its own internal
timing and knows nothing about how long you talk, so per section we hold the
last frame until the narration finishes (never speed-ramp the visuals — it
looks cheap and breaks the maths), then concat.

For anything the scene kit produced, use `fdx plan` / `fdx encode` /
`fdx finish` instead: those know when each word is spoken and cut to it,
rather than padding to fit afterwards.

One thing did get fixed here: captions come from the alignment when there is
one. The character-proportional fallback below is a last resort, not the
default it used to be.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cfg
from .project import Script, Section

MAX_TRAILING_SILENCE = 2.0   # seconds of animation allowed past the voice
CAPTION_CHARS = 84


def _sync_section(sec: Section, out: Path) -> Path:
    vdur, adur = cfg.duration(sec.video), cfg.duration(sec.audio)
    vf, af = [], []

    if vdur < adur - 0.05:
        # Hold the final frame rather than stretching time.
        vf.append(f"tpad=stop_mode=clone:stop_duration={adur - vdur + 0.15:.3f}")
    elif vdur > adur + MAX_TRAILING_SILENCE:
        # Animation badly overruns the script: trim it, don't leave dead air.
        cfg.say(f"  section {sec.stem}: trimming {vdur:.1f}s video to {adur:.1f}s voice")
        vf.append(f"trim=0:{adur + 0.5:.3f}")
        vf.append("setpts=PTS-STARTPTS")

    af.append("apad")  # then -shortest lets video decide final length

    cmd = ["ffmpeg", "-y", "-i", str(sec.video), "-i", str(sec.audio)]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-af", ",".join(af), "-shortest", *cfg.VOPTS,
            "-c:a", "aac", "-b:a", cfg.AAC_BITRATE,
            "-ar", str(cfg.AUDIO_SR), "-ac", "1", str(out)]
    cfg.run(cmd)
    return out


def _split_caption(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?;:,])\s+", text)
    chunks, buf = [], ""
    for p in parts:
        while len(p) > CAPTION_CHARS:
            cut = p.rfind(" ", 0, CAPTION_CHARS)
            cut = cut if cut > 0 else CAPTION_CHARS
            chunks.append(p[:cut].strip())
            p = p[cut:].strip()
        if len(buf) + len(p) + 1 <= CAPTION_CHARS:
            buf = f"{buf} {p}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c]


def _ts(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


def write_srt(script: Script, dst: Path, proj: Path | None = None) -> Path:
    """Captions for the legacy path.

    Prefer the alignment if this project has one — it knows when each word was
    actually spoken. Only fall back to sharing each section's time out in
    proportion to text length, which drifts the moment the voice pauses.
    """
    if proj is not None and (proj / "build" / "align").exists():
        try:
            from . import captions
            cfg.say("captions from the alignment")
            return captions.write_srt(proj, script, dst)
        except SystemExit:
            cfg.warn("no usable alignment — falling back to proportional timing")

    lines, n = [], 0
    for sec in script.sections:
        chunks = _split_caption(sec.narration)
        if not chunks:
            continue
        total = sum(len(c) for c in chunks)
        t = sec.start
        for c in chunks:
            span = sec.dur * (len(c) / total)
            n += 1
            lines += [str(n), f"{_ts(t)} --> {_ts(t + span)}", c, ""]
            t += span
    dst.write_text("\n".join(lines), encoding="utf-8")
    return dst


def chapters(script: Script) -> str:
    out = []
    for sec in script.sections:
        m, s = divmod(int(sec.start), 60)
        stamp = f"{m:02d}:{s:02d}" if m < 60 else f"{m//60}:{m%60:02d}:{s:02d}"
        out.append(f"{stamp} {sec.title}")
    if out:
        out[0] = "00:00 " + script.sections[0].title
    return "\n".join(out)


def assemble(proj: Path, script: Script, burn_captions: bool = False) -> Path:
    cfg.need("ffmpeg", "ffprobe")
    build, out = proj / "build", proj / "out"
    build.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)

    # Bind each section to its files and compute the timeline.
    clock = 0.0
    parts = []
    for sec in script.sections:
        v = proj / "sections" / f"{sec.stem}.mp4"
        a = proj / "audio" / f"{sec.stem}.m4a"
        if not v.exists():
            raise SystemExit(f"[fdx] missing visual for section {sec.stem}: {v}")
        if not a.exists():
            raise SystemExit(f"[fdx] missing audio for section {sec.stem} — run narrate")
        sec.video, sec.audio = v, a
        cfg.say(f"syncing section {sec.stem} — {sec.title}")
        piece = _sync_section(sec, build / f"sync_{sec.stem}.mp4")
        sec.start = clock
        sec.dur = cfg.duration(piece)
        clock += sec.dur
        parts.append(piece)

    listfile = build / "concat.txt"
    listfile.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    merged = build / "merged.mp4"
    cfg.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(listfile), "-c", "copy", str(merged)], cwd=str(build))

    srt = write_srt(script, out / "captions.srt", proj)
    final = out / "final.mp4"

    if burn_captions:
        cfg.run([
            "ffmpeg", "-y", "-i", str(merged),
            "-vf", (f"subtitles={srt.name}:force_style='FontName={cfg.CAPTION_FONT},"
                    "FontSize=22,PrimaryColour=&HFFFFFF&,OutlineColour=&H80000000&,"
                    "BorderStyle=3,Outline=1,MarginV=40'"),
            *cfg.VOPTS, "-c:a", "copy", str(final),
        ], cwd=str(out))
    else:
        # Soft track: YouTube prefers you upload the .srt separately anyway.
        cfg.run(["ffmpeg", "-y", "-i", str(merged), "-i", str(srt),
                 "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                 "-movflags", "+faststart", str(final)])

    total = cfg.duration(final)
    cfg.say(f"final: {final}  ({total/60:.1f} min)")

    thumb = out / "thumb_source.png"
    cfg.run(["ffmpeg", "-y", "-ss", f"{total * 0.45:.2f}", "-i", str(final),
             "-frames:v", "1", str(thumb)])
    return final
