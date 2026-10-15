"""Render and assemble all 5 scenes for Machine Learning in Kashmiri (v2)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from prompt2render import cfg

PROJECT_SLUG = "machine-learning-kashmiri"
PROJ_DIR = ROOT / "projects" / PROJECT_SLUG
SCENES_DIR = PROJ_DIR / "scenes"
SECTIONS_DIR = PROJ_DIR / "sections"
BUILD_DIR = PROJ_DIR / "build"
OUT_DIR = PROJ_DIR / "out"

def render_scene(stem: str) -> Path:
    scene_class = f"Scene{stem}"
    py_file = SCENES_DIR / f"scene_{stem}.py"
    work = BUILD_DIR / "manim"
    work.mkdir(parents=True, exist_ok=True)

    print(f"\n>>> Rendering {scene_class} at 1080p Full HD (30 FPS)...")
    cmd = [
        sys.executable, "-m", "manim", "-qh", "--format", "mp4",
        "--fps", "30", "-r", "1920,1080",
        "--media_dir", str(work), str(py_file), scene_class
    ]
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if res.returncode != 0:
        print(f"ERROR rendering {scene_class}:\n{res.stderr or res.stdout}")
        sys.exit(1)

    made = sorted(work.rglob(f"{scene_class}.mp4"), key=lambda p: p.stat().st_mtime_ns)
    if not made:
        sys.exit(f"No {scene_class}.mp4 found under {work}")

    print(f"  Rendered {scene_class} in {time.time() - t0:.1f}s -> {made[-1]}")
    return made[-1]

def normalise_high_quality(src: Path, dst: Path, seconds: float) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(seconds * 30))
    vf = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps=30,"
        f"tpad=stop_mode=clone:stop_duration={max(seconds, 0):.3f}"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-crf", "17", "-preset", "slow",
        "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
        "-pix_fmt", "yuv420p", "-an",
        str(dst)
    ]
    subprocess.run(cmd, check=True)

def main():
    print("==========================================================")
    print(" Re-rendering & Assembling Machine Learning Kashmiri v2")
    print("==========================================================")

    amap_file = BUILD_DIR / "audio_map.json"
    amap = json.loads(amap_file.read_text(encoding="utf-8"))

    stems = ["01", "02", "03", "04", "05"]
    section_clips = []

    for stem in stems:
        dur = float(amap["sections"][stem]["dur"])
        raw_clip = render_scene(stem)
        dst_clip = SECTIONS_DIR / f"{stem}.mp4"
        print(f"  Conforming clip {stem} to exact audio length {dur:.2f}s...")
        normalise_high_quality(raw_clip, dst_clip, seconds=dur)
        section_clips.append(dst_clip)

    print("\n>>> Concatenating 5 clips...")
    concat_list = BUILD_DIR / "clips_concat.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in section_clips]
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    video_only = BUILD_DIR / "video_only.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(video_only)
    ], check=True)

    master_wav = BUILD_DIR / "master.wav"
    master_lufs = BUILD_DIR / "master_lufs.wav"
    print("\n>>> Mastering audio to broadcast -14 LUFS...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
        "-af", "loudnorm=I=-14:LRA=7:TP=-1.5",
        "-ar", "48000", "-ac", "2", str(master_lufs)
    ], check=True)

    final_mp4 = OUT_DIR / "final.mp4"
    print(f"\n>>> Muxing final video -> {final_mp4}...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_only),
        "-i", str(master_lufs),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "320k",
        "-movflags", "+faststart",
        str(final_mp4)
    ], check=True)

    showcase_mp4 = ROOT / "media" / "showcase" / "videos" / "Kashmiri_MachineLearning_preview.mp4"
    shutil.copy2(str(final_mp4), str(showcase_mp4))

    # Extract 5 QC verification frames
    qc_dir = BUILD_DIR / "qc_frames"
    qc_dir.mkdir(parents=True, exist_ok=True)
    timestamps = [("s1", 15), ("s2", 50), ("s3", 85), ("s4", 120), ("s5", 155)]
    for name, t in timestamps:
        dst = qc_dir / f"{name}.png"
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(final_mp4), "-vframes", "1", str(dst)], check=True)

    v_dur = cfg.duration(final_mp4)
    file_mb = final_mp4.stat().st_size / (1024 * 1024)
    print("\n==========================================================")
    print(f"  SUCCESS! High-Fidelity Kashmiri Video Built:")
    print(f"  File:     {final_mp4}")
    print(f"  Duration: {v_dur:.2f}s ({v_dur/60:.2f} minutes)")
    print(f"  Size:     {file_mb:.2f} MB")
    print("==========================================================")

if __name__ == "__main__":
    main()
