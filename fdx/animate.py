"""Stage 1 - visuals.

Three ways in, all producing the same thing: normalised, silent
1920x1080 clips named 01.mp4, 02.mp4 ... in <project>/sections/.

  animate  - drive Code2Video from script.md
  import   - bring in clips you made any other way (manual escape hatch)
  rerender - re-render a Manim .py you hand-edited (the quality step)

The manual path matters: Code2Video setup is the flakiest part of the
whole chain, and you should never be blocked from shipping by it.
"""
from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from . import cfg
from .project import Script


def _env_for_code2video() -> None:
    """Make Code2Video run with THIS Python, not whatever `python3` means to bash.

    run_agent_single.sh execs `python3` (overridable via $PYTHON) and the
    Manim workers shell out to `manim` on PATH. Point both at the current
    interpreter's environment so the venv's openai/manim are the ones used.
    """
    venv_bin = str(Path(sys.executable).parent)
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")
    # Force UTF-8 mode: Code2Video's logs are full of emojis and its own
    # stdout would otherwise crash the cp1252 encoder on Windows.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    # Forward slashes so Git bash can exec the path verbatim.
    os.environ.setdefault("PYTHON", sys.executable.replace("\\", "/"))


def normalise(src: Path, dst: Path) -> None:
    """Force every clip to the same resolution/fps/pixel format, strip audio.

    Doing this once here means concat later is predictable instead of a
    mismatched-codec debugging session.
    """
    cfg.run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", (f"scale={cfg.WIDTH}:{cfg.HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={cfg.WIDTH}:{cfg.HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={cfg.FPS}"),
        "-an", "-c:v", "libx264", "-crf", cfg.CRF, "-preset", "medium",
        "-pix_fmt", "yuv420p", str(dst),
    ])


def _collect(search_root: Path, out_dir: Path,
             match: Callable[[Path], bool] | None = None) -> list[Path]:
    def keep(p: Path) -> bool:
        if "partial_movie_files" in p.parts:
            return False
        if p.stat().st_size <= 1024:
            return False
        return match is None or match(p)

    found = sorted(
        (p for p in search_root.rglob("*.mp4") if keep(p)),
        key=lambda p: (len(p.parts), str(p)),
    )
    if not found:
        raise SystemExit(f"[fdx] no .mp4 found under {search_root}")
    written = []
    for i, src in enumerate(found, start=1):
        dst = out_dir / f"{i:02d}.mp4"
        cfg.say(f"normalising {src.name} -> {dst.name}")
        normalise(src, dst)
        written.append(dst)
    return written


def knowledge_point(script: Script) -> str:
    """Turn script.md into the single query string Code2Video expects."""
    topic = script.meta.get("topic") or script.title
    audience = script.meta.get("audience", "undergraduate")
    beats = "; ".join(f"{s.title}: {s.anim}" for s in script.sections if s.anim)
    return f"{topic} (for {audience}). Cover in order - {beats}"


def animate(proj: Path, script: Script, prefix: str | None = None) -> list[Path]:
    c2v = cfg._c2v_dir()
    if not (c2v / "src" / "run_agent_single.sh").exists():
        raise SystemExit(
            f"[fdx] Code2Video not found at {c2v}\n"
            "      set CODE2VIDEO_DIR in .env, or use:  python fdx.py import <slug> <dir>"
        )
    prefix = prefix or f"FDX-{proj.name}"
    kp = knowledge_point(script)
    cfg.say(f"Code2Video query: {kp[:160]}...")
    cfg.say("this takes ~15 min and costs real API money — go make tea")
    _env_for_code2video()
    # Pass the prefix through so the run lands in CASES/<prefix> and we can
    # collect exactly this project's clips instead of scraping all of CASES.
    rc = cfg.stream_run(cfg.shell_runner() + ["run_agent_single.sh",
                                              "--knowledge_point", kp,
                                              "--folder_prefix", prefix],
                        cwd=str(c2v / "src"))
    if rc != 0:
        raise SystemExit(f"[fdx] Code2Video exited with code {rc}")

    cases = c2v / "src" / "CASES" / prefix
    if not cases.exists():
        cases = c2v / "src" / "CASES"
    def _c2v_section(p: Path) -> bool:
        # The per-section renders land at media/videos/<scene>/<quality>/<Scene>.mp4
        # (quality 480p15 for the -ql flag agent.py uses). Skip the stitched
        # whole-video and manim's partial chunk files, or we'd collect them too.
        return p.parent.name == "480p15"
    return _collect(cases, proj / "sections", match=_c2v_section)


def import_sections(proj: Path, src_dir: Path) -> list[Path]:
    return _collect(src_dir, proj / "sections")


def rerender(py_file: Path, scene: str, proj: Path, index: int) -> Path:
    """Re-render one hand-edited Manim scene back into sections/.

    This is where you claw back the layout quality the paper's own human
    study says is the weak point. Fix the overlap, re-run this, done.
    """
    cfg.need("manim")
    work = proj / "build" / "manim"
    work.mkdir(parents=True, exist_ok=True)
    cfg.run(["manim", "-qh", "--format", "mp4", "--media_dir", str(work),
             str(py_file), scene])
    made = sorted(work.rglob(f"{scene}.mp4"), key=lambda p: p.stat().st_mtime)
    if not made:
        raise SystemExit(f"[fdx] manim produced no {scene}.mp4 under {work}")
    dst = proj / "sections" / f"{index:02d}.mp4"
    normalise(made[-1], dst)
    cfg.say(f"rerendered {scene} -> {dst.name}")
    return dst


def stock_card(proj: Path, index: int, text: str, seconds: float = 6.0) -> Path:
    """Placeholder card so a missing section never blocks a full assembly."""
    dst = proj / "sections" / f"{index:02d}.mp4"
    safe = text.replace("\\", "").replace(":", r"\:").replace("'", "")[:60]
    cfg.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x0d1117:s={cfg.WIDTH}x{cfg.HEIGHT}:d={seconds}:r={cfg.FPS}",
        "-vf", (f"drawtext={cfg.drawtext_font_arg()}text='{safe}':"
                f"fontcolor=white:fontsize=64:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"),
        "-c:v", "libx264", "-crf", cfg.CRF, "-pix_fmt", "yuv420p", "-an", str(dst),
    ])
    return dst
