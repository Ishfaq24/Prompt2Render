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

import subprocess
import sys
import tempfile
from pathlib import Path

from . import cfg, voice
from .project import Script


def normalise(src: Path, dst: Path, seconds: float | None = None) -> None:
    """Letterbox to the delivery format, and optionally to an exact length."""
    dst.parent.mkdir(parents=True, exist_ok=True)

    vf = (
        f"scale={cfg.WIDTH}:{cfg.HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={cfg.WIDTH}:{cfg.HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={cfg.FPS}"
    )

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]

    if seconds is not None:
        frames = max(1, round(seconds * cfg.FPS))
        # tpad extends short clips; -frames:v gives an exact hard ceiling for
        # long clips. Together they guarantee the requested frame count.
        vf += f",tpad=stop_mode=clone:stop_duration={max(seconds, 0):.3f}"
        cmd += ["-vf", vf, "-frames:v", str(frames)]
    else:
        cmd += ["-vf", vf]

    cmd += ["-an", *cfg.pick_vopts(), str(dst)]
    cfg.run(cmd)


def _collect(search_root: Path, out_dir: Path,
             durations: list[float] | None = None) -> list[Path]:
    """Import MP4s in stable order, optionally locking each to a duration."""
    def keep(p: Path) -> bool:
        try:
            return "partial_movie_files" not in p.parts and p.stat().st_size > 1024
        except OSError:
            return False

    found = sorted(
        (p for p in search_root.rglob("*.mp4") if keep(p)),
        key=lambda p: (len(p.parts), str(p)),
    )
    if not found:
        raise SystemExit(f"[prompt2render] no .mp4 found under {search_root}")

    if durations is not None and len(found) != len(durations):
        raise SystemExit(
            f"[prompt2render] found {len(found)} imported clips but the project "
            f"has {len(durations)} sections; provide exactly one clip per section"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for i, src in enumerate(found, start=1):
        dst = out_dir / f"{i:02d}.mp4"
        seconds = durations[i - 1] if durations is not None else None
        detail = f" ({seconds:.3f}s)" if seconds is not None else ""
        cfg.say(f"normalising {src.name} -> {dst.name}{detail}")
        normalise(src, dst, seconds)
        written.append(dst)

    return written


def import_sections(proj: Path, src_dir: Path) -> list[Path]:
    """Import one clip per script section and lock each clip to narration time.

    If audio_map.json is not available yet, preserve the legacy behaviour and
    normalise without forcing a duration; the next voice/assemble pass can
    then enforce the section timing.
    """
    durations: list[float] | None = None
    try:
        amap = voice.audio_map(proj)
        script_path = proj / "script.md"
        if script_path.exists():
            from .project import parse_script
            script = parse_script(script_path)
            durations = [
                float(amap["sections"][sec.stem]["dur"])
                for sec in script.sections
            ]
    except (SystemExit, KeyError, TypeError, ValueError):
        durations = None

    return _collect(src_dir, proj / "sections", durations)


def _write_drawtext_file(proj: Path, index: int, text: str) -> Path:
    """Write drawtext content to a file so shell/filter escaping is irrelevant."""
    tmp_dir = proj / "build" / "import"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / f"title_{index:02d}.txt"
    path.write_text(text[:200], encoding="utf-8")
    return path


def stock_card(proj: Path, index: int, text: str, seconds: float = 6.0) -> Path:
    """A placeholder so one unwritten section never blocks a whole assembly."""
    dst = proj / "sections" / f"{index:02d}.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    text_file = _write_drawtext_file(proj, index, text)

    # textfile= avoids drawtext's special handling of %, :, ', \\, brackets,
    # and other punctuation in arbitrary section titles.
    vf = (
        f"drawtext={cfg.drawtext_font_arg()}"
        f"textfile='{text_file.as_posix()}'"
        ":fontcolor=white:fontsize=64:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )

    cfg.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi",
        "-i", f"color=c=0x0d1117:s={cfg.WIDTH}x{cfg.HEIGHT}:"
               f"d={seconds}:r={cfg.FPS}",
        "-vf", vf,
        "-an", *cfg.pick_vopts(), str(dst),
    ])
    return dst


def manim_scene(proj: Path, script: Script, py_file: Path, scene: str,
                index: int) -> Path:
    """Render one Manim scene into the section contract.

    Originally hand-authored only (Manim's API surface is enormous, renders
    are slow, and it has none of the scene kit's defensive self-shrinking, so
    pointing a model at it burned far more tokens for worse layout than the
    stills backend) -- as of the harness's Tier 2 Manim-as-compiler work
    (docs/ARCHITECTURE_AUDIT.md SS17), this is also the shared render entry
    point ``renderer_manim`` calls for LLM/compiler-generated scenes, not
    just the manual ``prompt2render manim`` escape hatch. Still the right
    tool for one or two hand-written hero shots too.

    Note MathTex and Tex need a LaTeX install; `prompt2render doctor` will say
    whether you have one.
    """
    cfg.need("manim")
    work = proj / "build" / "manim"
    work.mkdir(parents=True, exist_ok=True)

    cmd = [
        "manim", "-qh", "--format", "mp4", "--fps", str(cfg.FPS),
        "-r", f"{cfg.WIDTH},{cfg.HEIGHT}",
        "--media_dir", str(work), str(py_file), scene,
    ]

    try:
        # Capture output because the repair router can use the actual Manim
        # diagnostics rather than a generic "render failed" message.
        res = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        cfg.need("manim")
        raise

    if res.returncode != 0:
        diagnostics = (res.stderr or res.stdout or "").strip()
        raise SystemExit(
            f"Manim crashed with exit code {res.returncode}:\n{diagnostics}"
        )

    made = sorted(
        work.rglob(f"{scene}.mp4"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    if not made:
        raise SystemExit(
            f"[prompt2render] manim produced no {scene}.mp4 under {work}"
        )

    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")

    seconds: float | None = None
    try:
        seconds = float(voice.audio_map(proj)["sections"][sec.stem]["dur"])
    except (SystemExit, KeyError, TypeError, ValueError):
        cfg.warn(
            "no audio yet — the clip will keep its own length; re-run after "
            "`prompt2render voice` to lock it to the narration"
        )

    dst = proj / "sections" / f"{index:02d}.mp4"
    # When the harness is the caller, the raw Manim clip must already be
    # cue-synced; forcing the section to the narration length with a large
    # tpad would hide a temporal bug (sections 01/07 stale-assembly case).
    # Measure raw duration first and warn if the generator missed the target
    # by more than the verifier tolerance — the verifier will block assembly,
    # but this early warning makes the mismatch visible in logs.
    if seconds is not None:
        try:
            raw_dur = cfg.duration(made[-1])
            gap = abs(raw_dur - seconds)
            if gap > 1.6:
                cfg.warn(
                    f"Manim raw clip for section {index:02d} is {raw_dur:.2f}s "
                    f"but narration is {seconds:.2f}s (gap {gap:.2f}s) — "
                    "generator did not hit exact cue timing; temporal verifier should flag this."
                )
        except Exception:
            pass
    normalise(made[-1], dst, seconds)

    # Extract the final frame as a preview image for visual layout auditing.
    preview_dst = proj / "build" / "manim" / "previews"
    preview_dst.mkdir(parents=True, exist_ok=True)
    preview_img = preview_dst / f"Scene{sec.stem}.png"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-sseof", "-0.1", "-i", str(dst),
                "-frames:v", "1", str(preview_img),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    cfg.say(
        f"rendered {scene} -> {dst.name}"
        + (f" ({seconds:.1f}s to match the narration)" if seconds else "")
    )
    return dst