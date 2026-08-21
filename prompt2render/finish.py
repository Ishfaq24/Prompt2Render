"""Clips -> sections -> final.mp4. Every video step is a stream copy.

Two things here are deliberate and load-bearing.

**The concat preflight.** MP4 keeps SPS/PPS out of band in `avcC`, and the
concat demuxer with `-c copy` takes that extradata from the first input only.
If one clip was encoded with different settings the result decodes wrong on
some players and looks fine on yours. So every clip's codec parameters are
compared before anything is joined.

**One audio master.** The old finish stage concatenated the per-section AAC
files, which adds roughly 4 ms of encoder priming gap per section — measured
at +21 ms over five sections in the original binary-search build, and growing
linearly with section count. Here the programme was mastered and encoded once,
so there is simply nothing to drift.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import captions, cfg, encode, timeline, voice
from .project import Script


def _concat(files: list[str], dst: Path, cwd: Path) -> None:
    lst = cwd / f".concat_{dst.stem}.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
    cfg.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", str(dst)], cwd=str(cwd))


def _preflight(proj: Path, rows: list[dict]) -> None:
    stale = [r["clip"] for r in rows if encode._needs_encode(proj, r)]
    if stale:
        sys.exit(
            "[prompt2render] clip(s) missing or older than the still they were "
            f"rendered from: {', '.join(stale[:5])}"
            + (f" (+{len(stale) - 5} more)" if len(stale) > 5 else "")
            + " — run `prompt2render encode --all`")

    # One ffprobe per clip, and a full-length video has dozens of them. They
    # are independent processes waiting on file reads, so they go out together
    # and the results are compared in plan order exactly as before.
    all_params = cfg.parallel(lambda r: cfg.video_params(proj / r["clip"]),
                              rows, cfg.probe_jobs(), "preflight")
    ref, ref_row = None, None
    for r, params in zip(rows, all_params):
        if ref is None:
            ref, ref_row = params, r
            continue
        if params != ref:
            diff = {k: (ref[k], params[k]) for k in ref if ref[k] != params[k]}
            sys.exit(
                f"[prompt2render] {r['clip']} was encoded differently from "
                f"{ref_row['clip']} and cannot be stream-copy concatenated:\n"
                f"      {diff}\n"
                "      delete build/clips and re-run `prompt2render encode --all` "
                "(a --preview pass cannot be mixed with a final one)")
    cfg.say(f"preflight: {len(rows)} clips share one encoder profile "
            f"({ref['codec_name']} {ref['profile']} {ref['pix_fmt']})")


def _chapters(proj: Path, script: Script, dst: Path) -> Path:
    amap = voice.audio_map(proj)
    lines = [";FFMETADATA1", f"title={script.title}", ""]
    for sec in script.sections:
        o = amap["sections"][sec.stem]
        lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={int(o['start'] * 1000)}",
                  f"END={int((o['start'] + o['dur']) * 1000)}",
                  f"title={sec.title}", ""]
    dst.write_text("\n".join(lines), encoding="utf-8")
    return dst


def _thumbnail(proj: Path, rows: list[dict], dst: Path) -> None:
    """Use the still that is on screen longest, not an arbitrary timestamp."""
    states = [r for r in rows if r["kind"] in ("state", "section")] or rows
    best = max(states, key=lambda r: r["frames"])
    src = proj / best["png"]
    if src.exists():
        # The PNG is the original render; grabbing the same frame back out of
        # the H.264 would only add compression artefacts to a thumbnail.
        shutil.copyfile(src, dst)
        cfg.say(f"thumbnail from {best['name']} ({best['seconds']}s on screen)")


def finish(proj: Path, script: Script, burn: bool = False,
           style: str = "srt") -> Path:
    cfg.need("ffmpeg", "ffprobe")
    plan = timeline.load(proj)
    rows = plan["clips"]
    build, out = proj / "build", proj / "out"
    out.mkdir(exist_ok=True)
    (proj / "sections").mkdir(exist_ok=True)

    _preflight(proj, rows)
    amap = voice.audio_map(proj)

    # 1. clips -> one silent clip per section. This keeps sections/NN.mp4 as
    #    the shared contract, so `prompt2render import` and `prompt2render assemble` still work.
    # Each section is an independent stream-copy concat of its own clips, so
    # they are joined together rather than one after another. Both the concat
    # and the frame-count check that follows it are I/O bound ffmpeg calls.
    by_section = {sec.stem: [Path(r["clip"]).name for r in rows
                             if r["section"] == sec.stem]
                  for sec in script.sections}
    for sec in script.sections:
        if not by_section[sec.stem]:
            sys.exit(f"[prompt2render] no clips planned for section {sec.stem}")

    def join(sec) -> int:
        dst = proj / "sections" / f"{sec.stem}.mp4"
        _concat(by_section[sec.stem], dst, build / "clips")
        return cfg.frame_count(dst)

    counts = cfg.parallel(join, list(script.sections),
                          cfg.env_int("P2R_CONCAT_JOBS", 4), "concat")
    for sec, got in zip(script.sections, counts):
        want = round(amap["sections"][sec.stem]["dur"] * cfg.FPS)
        if got != want:
            sys.exit(f"[prompt2render] section {sec.stem} is {got} frames but its audio "
                     f"is {want} — the plan and the encode disagree; "
                     "re-run `prompt2render plan` then `prompt2render encode --all`")
        cfg.say(f"section {sec.stem}: {len(by_section[sec.stem])} clips "
                f"-> {got} frames")

    # 2. sections -> the full silent picture
    _concat([f"../../sections/{s.stem}.mp4" for s in script.sections],
            build / "video.mp4", build / "clips")

    # 3. captions and chapters
    srt = captions.write_srt(proj, script, out / "captions.srt")
    meta = _chapters(proj, script, build / "chapters.txt")
    master = build / "master.m4a"
    if not master.exists():
        sys.exit("[prompt2render] no build/master.m4a — run `prompt2render voice`")

    final = out / "final.mp4"
    video = build / "video.mp4"

    if burn:
        sub = (captions.write_ass(proj, script, out / "captions.ass")
               if style == "ass" else srt)
        vf = (f"ass={cfg.filter_path(sub)}" if style == "ass" else
              f"subtitles={cfg.filter_path(sub)}:force_style='"
              f"FontName={cfg.CAPTION_FONT},FontSize=22,"
              "PrimaryColour=&HFFFFFF&,OutlineColour=&H80000000&,"
              "BorderStyle=3,Outline=1,MarginV=40'")
        burned = build / "video_burned.mp4"
        cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(video),
                 "-vf", vf, *cfg.pick_vopts(), str(burned)])
        video = burned

    cfg.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video), "-i", str(master), "-i", str(srt), "-i", str(meta),
        "-map", "0:v", "-map", "1:a", "-map", "2:s", "-map_metadata", "3",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=eng",
        "-movflags", "+faststart", str(final),
    ])

    total = cfg.duration(final)
    _thumbnail(proj, rows, out / "thumb_source.png")
    cfg.say(f"final: {final}  ({total/60:.2f} min)")
    return final
