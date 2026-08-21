"""Escape hatches for pictures that did not come from the scene kit.

Everything here guarantees the same contract: silent, 1920x1080, 30 fps clips
named 01.mp4, 02.mp4 ... in <project>/sections/, each exactly as long as its
section's narration.

The Code2Video path that used to live here is retired — see docs/RETIRED.md.
What remains is the useful part: bring in clips from anywhere, stand in a
title card while a section is unwritten, and render a hand-authored Manim
scene for the one or two hero shots a video actually wants.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import cfg, voice
from .project import Script


def normalise(src: Path, dst: Path, seconds: float | None = None) -> None:
    """Letterbox to the delivery format, and optionally to an exact length."""
    vf = (f"scale={cfg.WIDTH}:{cfg.HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={cfg.WIDTH}:{cfg.HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
          f"setsar=1,fps={cfg.FPS}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if seconds is not None:
        frames = round(seconds * cfg.FPS)
        # Hold the last frame if it is short, cut if it is long, so the clip
        # lands on the exact frame count the contract requires.
        vf += f",tpad=stop_mode=clone:stop_duration={seconds:.3f}"
        cmd += ["-vf", vf, "-frames:v", str(frames)]
    else:
        cmd += ["-vf", vf]
    cmd += ["-an", *cfg.pick_vopts(), str(dst)]
    cfg.run(cmd)


def _collect(search_root: Path, out_dir: Path) -> list[Path]:
    def keep(p: Path) -> bool:
        return "partial_movie_files" not in p.parts and p.stat().st_size > 1024

    found = sorted((p for p in search_root.rglob("*.mp4") if keep(p)),
                   key=lambda p: (len(p.parts), str(p)))
    if not found:
        raise SystemExit(f"[prompt2render] no .mp4 found under {search_root}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i, src in enumerate(found, start=1):
        dst = out_dir / f"{i:02d}.mp4"
        cfg.say(f"normalising {src.name} -> {dst.name}")
        normalise(src, dst)
        written.append(dst)
    return written


def import_sections(proj: Path, src_dir: Path) -> list[Path]:
    return _collect(src_dir, proj / "sections")


def stock_card(proj: Path, index: int, text: str, seconds: float = 6.0) -> Path:
    """A placeholder so one unwritten section never blocks a whole assembly."""
    dst = proj / "sections" / f"{index:02d}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    # drawtext expands '%' and treats ':' and '\' as syntax; strip the lot
    # rather than try to escape a title we do not control.
    safe = "".join(c for c in text if c not in "\\:'%,[]")[:60]
    cfg.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", f"color=c=0x0d1117:s={cfg.WIDTH}x{cfg.HEIGHT}:d={seconds}:r={cfg.FPS}",
        "-vf", (f"drawtext={cfg.drawtext_font_arg()}text='{safe}':"
                "fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2"),
        "-an", *cfg.pick_vopts(), str(dst),
    ])
    return dst


def manim_scene(proj: Path, script: Script, py_file: Path, scene: str,
                index: int) -> Path:
    """Render one hand-authored Manim scene into the section contract.

    Deliberately hand-authored only. Manim's API surface is enormous, renders
    are slow, and it has none of the scene kit's defensive self-shrinking, so
    pointing a model at it burns far more tokens for worse layout. For one or
    two hero shots per video, written by you, it is the better tool.

    Note MathTex and Tex need a LaTeX install; `prompt2render doctor` will say whether
    you have one.
    """
    cfg.need("manim")
    work = proj / "build" / "manim"
    work.mkdir(parents=True, exist_ok=True)
    cfg.stream_run(["manim", "-qh", "--format", "mp4", "--fps", str(cfg.FPS),
                    "-r", f"{cfg.WIDTH},{cfg.HEIGHT}",
                    "--media_dir", str(work), str(py_file), scene])
    made = sorted(work.rglob(f"{scene}.mp4"), key=lambda p: p.stat().st_mtime)
    if not made:
        raise SystemExit(f"[prompt2render] manim produced no {scene}.mp4 under {work}")

    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")
    seconds = None
    try:
        seconds = voice.audio_map(proj)["sections"][sec.stem]["dur"]
    except SystemExit:
        cfg.warn("no audio yet — the clip will keep its own length; re-run "
                 "after `prompt2render voice` to lock it to the narration")

    dst = proj / "sections" / f"{index:02d}.mp4"
    normalise(made[-1], dst, seconds)
    cfg.say(f"rendered {scene} -> {dst.name}"
            + (f" ({seconds:.1f}s to match the narration)" if seconds else ""))
    return dst
