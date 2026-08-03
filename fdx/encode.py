"""One still -> one clip. Resumable, and with the motion baked in.

The trick that makes transitions cheap here: put the dissolve at the **head**
of each clip rather than across the boundary between two. Clip N is
`[dissolve from still N-1 into still N]` followed by `[hold still N]`. Clip
N-1 already ends on still N-1, so concatenating them is seamless — and every
clip stays an independent, resumable, stream-copyable unit. Nothing about the
resume logic has to know that motion exists.

The transition vocabulary is deliberately two: a dissolve, and a dip to black
at chapter changes. Wipes, pixelize and the rest are the "AI slop" signal;
a dissolve between two frames that share most of their content reads as the
elements themselves moving, which is the point.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from . import cfg

DISSOLVE = {
    "state": 0.35,
    "reveal": 0.20,       # shorter: a reveal is a smaller change
    "section": 0.50,
}
OPEN_FADE = 0.60         # from black, on the very first clip


def _clip_paths(proj: Path, row: dict) -> tuple[Path, Path, Path | None]:
    clip = proj / row["clip"]
    png = proj / row["png"]
    prev = (proj / row["prev_png"]) if row.get("prev_png") else None
    return clip, png, prev


def _cmd(row: dict, png: Path, prev: Path | None, out: Path,
         vopts: list[str]) -> list[str]:
    n = row["frames"]
    secs = n / cfg.FPS
    base = ["ffmpeg", "-y", "-v", "error"]

    if prev is None:
        # First clip of the video: come up from black.
        d = min(OPEN_FADE, secs / 2)
        return base + [
            "-loop", "1", "-framerate", str(cfg.FPS), "-i", str(png),
            "-vf", f"fps={cfg.FPS},format=yuv420p,fade=t=in:st=0:d={d:.3f}",
            "-frames:v", str(n), *vopts, str(out)]

    d = DISSOLVE.get(row["kind"], DISSOLVE["state"])
    d = min(d, max(secs / 2, 1.0 / cfg.FPS))
    # settb=AVTB is required: xfade refuses inputs whose timebases differ.
    graph = (f"[0:v]settb=AVTB,fps={cfg.FPS},format=yuv420p[a];"
             f"[1:v]settb=AVTB,fps={cfg.FPS},format=yuv420p[b];"
             f"[a][b]xfade=transition=fade:duration={d:.3f}:offset=0[v]")
    return base + [
        "-loop", "1", "-framerate", str(cfg.FPS), "-t", f"{d:.3f}", "-i", str(prev),
        "-loop", "1", "-framerate", str(cfg.FPS), "-t", f"{secs:.3f}", "-i", str(png),
        "-filter_complex", graph, "-map", "[v]",
        "-frames:v", str(n), *vopts, str(out)]


def encode(proj: Path, limit: int | None = None, preview: bool = False) -> int:
    from . import timeline
    plan = timeline.load(proj)
    rows = plan["clips"]
    (proj / "build" / "clips").mkdir(parents=True, exist_ok=True)
    vopts = cfg.VOPTS_PREVIEW if preview else cfg.VOPTS
    if preview:
        cfg.warn("preview encode (nvenc) — do not mix these clips with a "
                 "final render; re-encode before `fdx finish`")

    done = 0
    for row in rows:
        clip, png, prev = _clip_paths(proj, row)
        if clip.exists() and clip.stat().st_size > 2048:
            continue
        if limit is not None and done >= limit:
            break
        if not png.exists():
            sys.exit(f"[fdx] missing still {png} — run `fdx stills`")

        # Encode to a sidecar and move it into place, so a run cut short never
        # leaves a half-written clip that the resume check trusts.
        part = clip.with_name(clip.stem + ".part.mp4")
        cfg.run(_cmd(row, png, prev, part, vopts))
        try:
            part.replace(clip)
        except OSError:
            shutil.copyfile(part, clip)
            part.unlink(missing_ok=True)
        done += 1
        cfg.say(f"  {clip.name}  {row['seconds']}s  {row['kind']}")

    remaining = sum(1 for r in rows
                    if not ((proj / r["clip"]).exists()
                            and (proj / r["clip"]).stat().st_size > 2048))
    cfg.say(f"encoded {done} this pass, {remaining} remaining")
    return remaining
