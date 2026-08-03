"""Turn scene stills into section clips, then into final.mp4.

The shape of this is dictated by one measurement: this machine encodes about
45 output frames per second at 1080p, so a 7-minute video is ~5 minutes of
solid encoding. Everything here is arranged so that cost is paid exactly once.

  plan     work out how long each still is on screen, from its weight and the
           section's narration length
  encode   render one still to one clip; resumable, so it can be run in
           batches without losing work
  finish   concat clips -> sections/NN.mp4, concat those -> final.mp4, mux the
           audio and captions. All stream copies, no re-encode.

    python tools/build_video.py plan   <slug>
    python tools/build_video.py encode <slug> [--limit 12]
    python tools/build_video.py finish <slug>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fdx import assemble as asm  # noqa: E402
from fdx import cfg  # noqa: E402
from fdx.project import parse_script  # noqa: E402

FPS = cfg.FPS
VOPTS = ["-c:v", "libx264", "-crf", cfg.CRF, "-preset", "veryfast",
         "-tune", "stillimage", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-g", str(FPS * 5)]


def plan_path(proj):
    return proj / "build" / "plan.json"


def cmd_plan(proj, script):
    plan = []
    for sec in script.sections:
        scenes = proj / "build" / "scenes" / sec.stem
        manifest = json.loads((scenes / "manifest.json").read_text())
        cues = json.loads(
            (proj / "build" / "align" / f"{sec.stem}.json").read_text())
        audio = proj / "audio" / f"{sec.stem}.m4a"
        adur = cfg.duration(audio)
        total_frames = round(adur * FPS)

        # Each state starts on the frame where its cue sentence starts being
        # spoken. That is the whole point of measuring the narration: the
        # picture changes when the words change, not on a proportional guess.
        starts = [round(cues[m["cue"]]["start"] * FPS) for m in manifest]
        starts[0] = 0
        for i in range(1, len(starts)):    # keep it strictly increasing
            starts[i] = max(starts[i], starts[i - 1] + FPS // 2)
        starts = [min(s, total_frames - FPS // 2 * (len(starts) - i))
                  for i, s in enumerate(starts)]

        frames = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
        frames.append(total_frames - starts[-1])

        for m, f in zip(manifest, frames):
            plan.append({
                "section": sec.stem,
                "i": m["i"],
                # Manifests may hold relative paths depending on where the
                # renderer was invoked from; the basename is the only part
                # worth trusting.
                "png": str(scenes / pathlib.Path(m["png"]).name),
                "frames": f,
                "seconds": round(f / FPS, 3),
                "clip": str(proj / "build" / "clips" /
                            f"{sec.stem}_{m['i']:03d}.mp4"),
            })
        cfg.say(f"section {sec.stem}: {len(manifest)} states, "
                f"{adur:.1f}s audio, {sum(frames)} frames")
    plan_path(proj).write_text(json.dumps(plan, indent=2), encoding="utf-8")
    tot = sum(p["frames"] for p in plan)
    cfg.say(f"plan: {len(plan)} clips, {tot} frames, {tot/FPS/60:.1f} min")


def cmd_encode(proj, script, limit):
    plan = json.loads(plan_path(proj).read_text())
    (proj / "build" / "clips").mkdir(parents=True, exist_ok=True)
    done = 0
    for p in plan:
        clip = pathlib.Path(p["clip"])
        if clip.exists() and clip.stat().st_size > 2048:
            continue                       # resumable: already encoded
        if done >= limit:
            break
        # Encode to a sidecar and move it into place, so a run cut short
        # never leaves a half-written clip that the resume check trusts.
        part = clip.with_name(clip.stem + ".part.mp4")
        cfg.run(["ffmpeg", "-y", "-v", "error", "-loop", "1",
                 "-framerate", str(FPS), "-i", p["png"],
                 "-frames:v", str(p["frames"]), *VOPTS, str(part)])
        try:
            part.replace(clip)
        except OSError:
            clip.write_bytes(part.read_bytes())
        done += 1
        cfg.say(f"  {clip.name}  {p['seconds']}s")
    remaining = sum(1 for p in plan
                    if not (pathlib.Path(p["clip"]).exists()
                            and pathlib.Path(p["clip"]).stat().st_size > 2048))
    cfg.say(f"encoded {done} this pass, {remaining} clips remaining")
    return remaining


def write_measured_srt(proj, script, dst):
    """Captions from the synthesiser's own timings.

    fdx's write_srt shares each section's time out in proportion to how many
    characters a chunk has, which drifts whenever the voice pauses or speeds
    up. We know when every sentence was actually spoken, so use that and only
    subdivide within a sentence when it is too long for one caption.
    """
    lines, n, offset = [], 0, 0.0
    for sec in script.sections:
        cues = json.loads(
            (proj / "build" / "align" / f"{sec.stem}.json").read_text())
        for c in cues:
            chunks = asm._split_caption(c["text"])
            if not chunks:
                continue
            span = max(c["end"] - c["start"], 0.4)
            total = sum(len(x) for x in chunks)
            t = c["start"]
            for ch in chunks:
                d = span * (len(ch) / total)
                n += 1
                lines += [str(n),
                          f"{asm._ts(offset + t)} --> {asm._ts(offset + t + d)}",
                          ch, ""]
                t += d
        offset += cfg.duration(proj / "sections" / f"{sec.stem}.mp4")
    dst.write_text("\n".join(lines), encoding="utf-8")
    return dst


def _concat(files, dst, cwd):
    lst = pathlib.Path(cwd) / f".concat_{dst.stem}.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files), encoding="utf-8")
    cfg.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", str(dst)], cwd=str(cwd))


def cmd_finish(proj, script):
    plan = json.loads(plan_path(proj).read_text())
    build = proj / "build"
    out = proj / "out"
    out.mkdir(exist_ok=True)
    (proj / "sections").mkdir(exist_ok=True)

    # 1. clips -> one silent clip per section (this is the fdx contract, so
    #    `python fdx.py assemble` still works from here later)
    for sec in script.sections:
        clips = [pathlib.Path(p["clip"]).name for p in plan
                 if p["section"] == sec.stem]
        _concat(clips, proj / "sections" / f"{sec.stem}.mp4", build / "clips")
        cfg.say(f"section {sec.stem}: {len(clips)} clips -> "
                f"{cfg.duration(proj / 'sections' / f'{sec.stem}.mp4'):.2f}s")

    # 2. sections -> full silent video, audio -> full track, then mux
    _concat([f"../../sections/{s.stem}.mp4" for s in script.sections],
            build / "video.mp4", build / "clips")
    _concat([f"../audio/{s.stem}.m4a" for s in script.sections],
            build / "audio.m4a", build)

    srt = write_measured_srt(proj, script, out / "captions.srt")

    final = out / "final.mp4"
    cfg.run(["ffmpeg", "-y", "-v", "error",
             "-i", str(build / "video.mp4"), "-i", str(build / "audio.m4a"),
             "-i", str(srt),
             "-map", "0:v", "-map", "1:a", "-map", "2:s",
             "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
             "-movflags", "+faststart", str(final)])

    total = cfg.duration(final)
    cfg.say(f"final: {final}  ({total/60:.2f} min)")
    cfg.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{total*0.42:.2f}",
             "-i", str(final), "-frames:v", "1", str(out / "thumb_source.png")])
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "encode", "finish"])
    ap.add_argument("slug")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()

    cfg.load_env()
    proj = cfg.project_dir(a.slug)
    script = parse_script(proj / "script.md")

    if a.cmd == "plan":
        cmd_plan(proj, script)
    elif a.cmd == "encode":
        left = cmd_encode(proj, script, a.limit)
        sys.exit(0 if left == 0 else 7)     # 7 = more passes needed
    else:
        cmd_finish(proj, script)


if __name__ == "__main__":
    main()
