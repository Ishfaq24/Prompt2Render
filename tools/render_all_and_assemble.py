"""Batch renderer and assembler for K-Means Clustering Hindi Video.

Renders scenes 01 to 07, normalises each clip to match narration audio,
concatenates them, masters audio to -14 LUFS, muxes final.mp4, and writes upload packet.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt2render import cfg, visuals

PROJECT_SLUG = "kmeans-clustering-hindi"
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

    print(f"\n>>> Rendering {scene_class} from {py_file.name}...")
    cmd = [
        sys.executable, "-m", "manim", "-qh", "--format", "mp4",
        "--fps", str(cfg.FPS), "-r", f"{cfg.WIDTH},{cfg.HEIGHT}",
        "--media_dir", str(work), str(py_file), scene_class
    ]
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        print(f"ERROR rendering {scene_class}:\n{res.stderr or res.stdout}")
        sys.exit(1)

    made = sorted(work.rglob(f"{scene_class}.mp4"), key=lambda p: p.stat().st_mtime_ns)
    if not made:
        sys.exit(f"No {scene_class}.mp4 found under {work}")

    print(f"  Finished {scene_class} in {time.time() - t0:.1f}s -> {made[-1]}")
    return made[-1]

def main():
    print("==========================================================")
    print(" K-Means Clustering Video: Batch Render & Assembly")
    print("==========================================================")

    # 1. Load audio durations
    amap_file = BUILD_DIR / "audio_map.json"
    if not amap_file.exists():
        sys.exit(f"Missing {amap_file} - run build_kmeans_hindi.py first")
    amap = json.loads(amap_file.read_text(encoding="utf-8"))

    stems = ["01", "02", "03", "04", "05", "06", "07"]
    section_clips = []

    # 2. Render and normalise each scene
    for stem in stems:
        dur = float(amap["sections"][stem]["dur"])
        raw_clip = render_scene(stem)
        dst_clip = SECTIONS_DIR / f"{stem}.mp4"
        print(f"  Normalising to {dur:.2f}s -> {dst_clip.name}")
        visuals.normalise(raw_clip, dst_clip, seconds=dur)
        section_clips.append(dst_clip)

    # 3. Concatenate video clips
    concat_list = BUILD_DIR / "clips_concat.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in section_clips]
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    video_only = BUILD_DIR / "video_only.mp4"
    print(f"\n>>> Concatenating {len(section_clips)} clips into {video_only.name}...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(video_only)
    ], check=True)

    # 4. Master audio with EBU R128 limiter / LUFS normalisation
    master_wav = BUILD_DIR / "master.wav"
    master_lufs = BUILD_DIR / "master_lufs.wav"
    print(f"\n>>> Mastering audio to -14 LUFS standard...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
        "-af", "loudnorm=I=-14:LRA=7:TP=-1.5",
        "-ar", "48000", "-ac", "2", str(master_lufs)
    ], check=True)

    # 5. Final Mux: Video + Master Audio
    final_mp4 = OUT_DIR / "final.mp4"
    print(f"\n>>> Muxing final production video -> {final_mp4}...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_only),
        "-i", str(master_lufs),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(final_mp4)
    ], check=True)

    # 6. Verify final video
    v_dur = cfg.duration(final_mp4)
    file_mb = final_mp4.stat().st_size / (1024 * 1024)
    print("\n==========================================================")
    print(f"  SUCCESS! Final video produced:")
    print(f"  File:     {final_mp4}")
    print(f"  Duration: {v_dur:.2f}s ({v_dur/60:.2f} minutes)")
    print(f"  Size:     {file_mb:.2f} MB")
    print("==========================================================")

    # 7. Write upload metadata packet
    upload_md = OUT_DIR / "upload.md"
    upload_content = f"""# YouTube Upload Packet: K-Means Clustering (Hindi)

## Title
K-Means Clustering Explained in Detail (Full Hindi Tutorial) | Machine Learning Unsupervised Learning

## Video Details
- **Duration:** {v_dur/60:.2f} minutes ({int(v_dur//60)}m {int(v_dur%60)}s)
- **Resolution:** 1080p Full HD (1920x1080 @ 30 FPS)
- **Audio:** Hindi Audio (-14 LUFS YouTube standard)
- **Subtitles:** Included in `captions.srt`

## Description
इस विस्तृत वीडियो में K-Means Clustering एल्गोरिदम की कार्यप्रणाली, गणितीय समीकरणों और विजुअल कन्वर्जेंस को आसान हिंदी में गहराई से समझाया गया है।

## Video Chapters / Timestamps
- 0:00 - Introduction & Unsupervised Learning Intuition
- 0:38 - Mathematical Foundations & WCSS Objective Function
- 1:22 - Lloyd's Algorithm: The 4 Core Iterative Steps
- 2:08 - Visual Convergence & Voronoi Decision Boundaries
- 2:49 - Finding Optimal K: The Elbow Method
- 3:35 - Initialization Trap & K-Means++ Smart Seeding
- 4:17 - Summary: Strengths, Limitations & Real-World Applications

## Tags
K-Means Clustering, Machine Learning in Hindi, Unsupervised Learning, Data Science Hindi, WCSS, Elbow Method, KMeans++, Lloyds Algorithm, Artificial Intelligence, Clustering Tutorial
"""
    upload_md.write_text(upload_content, encoding="utf-8")
    print(f"Upload packet written to {upload_md}")

if __name__ == "__main__":
    main()
