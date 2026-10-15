"""Batch renderer and assembler for Machine Learning Kashmiri Video.

Renders scenes 01 to 05 at 1080p Full HD, normalises each clip to match narration audio,
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from prompt2render import cfg, visuals

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

    print(f"\n>>> Rendering {scene_class} from {py_file.name} (1080p HD)...")
    cmd = [
        sys.executable, "-m", "manim", "-qh", "--format", "mp4",
        "--fps", str(cfg.FPS), "-r", f"{cfg.WIDTH},{cfg.HEIGHT}",
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

    print(f"  Finished {scene_class} in {time.time() - t0:.1f}s -> {made[-1]}")
    return made[-1]

def main():
    print("==========================================================")
    print(" Machine Learning in Kashmiri: Batch Render & Assembly")
    print("==========================================================")

    # 1. Load audio durations
    amap_file = BUILD_DIR / "audio_map.json"
    if not amap_file.exists():
        sys.exit(f"Missing {amap_file} - run build_ml_kashmiri.py first")
    amap = json.loads(amap_file.read_text(encoding="utf-8"))

    stems = ["01", "02", "03", "04", "05"]
    section_clips = []

    # 2. Render and normalise each scene
    for stem in stems:
        dur = float(amap["sections"][stem]["dur"])
        dst_clip = SECTIONS_DIR / f"{stem}.mp4"
        if dst_clip.exists():
            curr_dur = cfg.duration(dst_clip)
            if abs(curr_dur - dur) <= 0.2:
                print(f"  Section {stem} already rendered and normalised ({curr_dur:.2f}s) -> skipping")
                section_clips.append(dst_clip)
                continue

        raw_clip = render_scene(stem)
        print(f"  Normalising clip to audio duration {dur:.2f}s -> {dst_clip.name}")
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

    # 4. Master audio with EBU R128 limiter / -14 LUFS normalisation
    master_wav = BUILD_DIR / "master.wav"
    master_lufs = BUILD_DIR / "master_lufs.wav"
    print(f"\n>>> Mastering audio to -14 LUFS broadcast standard...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
        "-af", "loudnorm=I=-14:LRA=7:TP=-1.5",
        "-ar", "48000", "-ac", "2", str(master_lufs)
    ], check=True)

    # 5. Final Mux: Video + Master Audio
    final_mp4 = OUT_DIR / "final.mp4"
    print(f"\n>>> Muxing final production broadcast video -> {final_mp4}...")
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
    upload_content = f"""# YouTube Release Packet: Machine Learning in Kashmiri (کٲشُر)

## Title
Machine Learning Explained in Kashmiri (کٲشُر زَبانہِ مَنٛز مکمل تعارف) | Full AI & ML Course

## Video Specifications
- **Duration:** {v_dur/60:.2f} minutes ({int(v_dur//60)}m {int(v_dur%60)}s)
- **Resolution:** 1080p Full HD (1920x1080 @ 30 FPS)
- **Audio:** Kashmiri Narration (-14.0 LUFS YouTube broadcast standard)
- **Subtitles:** Included in `captions.srt` (Perso-Arabic Kashmiri)
- **Renderer:** Manim Community Edition CE

## Description (English & Kashmiri)
اَتھ مکمل تعلیمی ویڈیو ہَس مَنٛز چھُ مشین لرننگ ہُنٛد بنیادی تصور، روایتی پروگرامنگ سٟتؠ موازنہٕ، سُوپر وائزڈ، اَن سُوپر وائزڈ تہٕ ری اِنفورسمنٹ لرننگ، لاس فنکشن، گریڈینٹ ڈیسینٹ، تہٕ اوورفِٹِنٛگ کٲشُر زَبانہِ مَنٛز آسان اندازس مَنٛز سمجھاونہٕ آمُت۔

This comprehensive educational video explains the foundations of Machine Learning from first principles in Kashmiri (Koshur). It features intuitive animations comparing traditional programming vs machine learning, the three core paradigms, loss function optimization with gradient descent, overfitting vs underfitting, and modern real-world applications in medical imaging, autonomous vehicles, and Kashmiri language AI.

## Video Chapters / Timestamps
- 0:00 - تعارف تہٕ پیراڈائم شفٹ (Introduction & Paradigm Shift)
- 0:50 - مشین لرننگ ہٕنٛدی ترٛے قسٕم (Three Core Paradigms of Machine Learning)
- 1:52 - لاس فنکشن تہٕ گریڈینٹ ڈیسینٹ (Loss Function & Gradient Descent)
- 2:51 - اوورفِٹِنٛگ بمقابلہ انڈرفِٹِنٛگ (Overfitting vs Underfitting)
- 3:47 - اصل دُنیاہَس مَنٛز استعمال تہٕ خلاصہٕ (Real-World Applications & Summary)

## Tags
Machine Learning in Kashmiri, Kashmiri AI, Koshur Machine Learning, Artificial Intelligence in Kashmiri, Supervised Learning, Unsupervised Learning, Gradient Descent Kashmiri, Overfitting, Deep Learning, Prompt2Render
"""
    upload_md.write_text(upload_content, encoding="utf-8")
    print(f"Upload packet written to {upload_md}")

if __name__ == "__main__":
    main()
