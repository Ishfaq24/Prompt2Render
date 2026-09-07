import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

proj_dir = Path("projects/human-brain-problem")

build_dir = proj_dir / "build"
out_dir = proj_dir / "out"
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Gather all 6 rendered scene clips
stage_dir = build_dir / "manim_finish"
stage_dir.mkdir(parents=True, exist_ok=True)

clips = {
    "01": Path("media/videos/scene_01/1080p60/scene_01.mp4"),
    "02": Path("media/videos/scene_02/1080p60/scene_02.mp4"),
    "03": Path("media/videos/scene_03/1080p60/scene_03.mp4"),
    "04": Path("media/videos/scene_04/1080p60/scene_04.mp4"),
    "05": Path("media/videos/scene_05/1080p60/scene_05.mp4"),
    "06": Path("media/videos/scene_06/1080p60/scene_06.mp4"),
}

for stem, src in clips.items():
    if not src.exists():
        print(f"Waiting for {src}...")
        sys.exit(1)
    dst = stage_dir / f"{stem}.mp4"
    shutil.copyfile(src, dst)
    print(f"Staged {dst}")

# 2. Concat video clips
concat_list = stage_dir / "concat_list.txt"
lines = [f"file '{stem}.mp4'\n" for stem in sorted(clips.keys())]
concat_list.write_text("".join(lines), encoding="utf-8")

raw_video = build_dir / "video_raw.mp4"
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "concat", "-safe", "0",
    "-i", str(concat_list),
    "-c", "copy",
    str(raw_video)
], check=True)
print("Concatenated video clips ->", raw_video)

# 3. Generate SRT captions
from prompt2render import captions
from prompt2render.project import parse_script
script = parse_script(proj_dir / "script.md")
srt_file = out_dir / "captions.srt"

captions.write_srt(proj_dir, script, srt_file)
print("Wrote captions ->", srt_file)

# 4. Check master audio and pad video if needed to match audio length
from prompt2render import cfg
master_audio = build_dir / "master.wav"
if not master_audio.exists():
    master_audio = build_dir / "master.m4a"

adur = cfg.duration(master_audio)
vdur = cfg.duration(raw_video)
print(f"Durations: Audio={adur:.3f}s, Video={vdur:.3f}s (delta = {abs(adur - vdur):.3f}s)")

padded_video = raw_video
if adur > vdur + 0.05:
    pad = adur - vdur
    padded_video = build_dir / "video_padded.mp4"
    print(f"Padding video by {pad:.3f}s to match audio length...")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(raw_video),
        "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(padded_video)
    ], check=True)

# 5. Final Mux with AAC mastered audio and subtitles
final_mp4 = out_dir / "final.mp4"
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-i", str(padded_video),
    "-i", str(master_audio),
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "192k",
    "-movflags", "+faststart",
    str(final_mp4)
], check=True)

final_dur = cfg.duration(final_mp4)
print(f"SUCCESS: Master video created at {final_mp4} ({final_dur / 60:.2f} min)")
