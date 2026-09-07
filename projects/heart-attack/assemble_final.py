"""Assemble complete Heart Attack educational video with narration and procedural sound design."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.audio_foley import extract_foley_events_from_code, render_foley_track


def assemble():
    proj_dir = Path("projects/heart-attack")
    build_dir = proj_dir / "build"
    out_dir = proj_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load audio map
    audio_map = json.loads((build_dir / "audio_map.json").read_text(encoding="utf-8"))
    total_duration = float(audio_map["total"])
    sec_info = audio_map["sections"]

    # 1. Extract and schedule foley sound cues
    all_events: list[tuple[float, str]] = []

    for stem in ["01", "02", "03"]:
        code_file = proj_dir / "scenes" / f"{stem}.py"
        code_text = code_file.read_text(encoding="utf-8")
        start_t = float(sec_info[stem]["start"])
        dur = float(sec_info[stem]["dur"])

        events = extract_foley_events_from_code(code_text, dur)
        for ts, cue_type in events:
            all_events.append((round(start_t + ts, 2), cue_type))

    foley_wav = build_dir / "foley.wav"
    render_foley_track(all_events, total_duration, foley_wav)
    print(f"[assembly] Foley track rendered: {len(all_events)} events across {total_duration:.1f}s")

    # 2. Concat video clips
    clip_01 = Path("media/videos/01/480p15/Scene01.mp4").resolve()
    clip_02 = Path("media/videos/02/480p15/Scene02.mp4").resolve()
    clip_03 = Path("media/videos/03/480p15/Scene03.mp4").resolve()

    concat_txt = build_dir / "concat_list.txt"
    concat_txt.write_text(
        f"file '{clip_01.as_posix()}'\nfile '{clip_02.as_posix()}'\nfile '{clip_03.as_posix()}'\n",
        encoding="utf-8",
    )

    concat_video = build_dir / "video_concat.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(concat_video),
        ],
        check=True,
    )
    print(f"[assembly] Video clips concatenated: {concat_video}")

    # 3. Mux Video + Master Narration Audio + Foley Track into final MP4
    master_wav = build_dir / "master.wav"
    final_mp4 = out_dir / "final.mp4"

    # amix combines voice (weight 1.0) and foley sound design (weight 0.35)
    filter_expr = "[1:a][2:a]amix=inputs=2:duration=first:weights=1.0 0.35[aout]"

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(concat_video),
        "-i", str(master_wav),
        "-i", str(foley_wav),
        "-filter_complex", filter_expr,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(final_mp4),
    ]
    subprocess.run(cmd, check=True)
    print(f"[assembly] Final Mastered Video Ready: {final_mp4}")

    # Copy to Artifact directory for direct playback in UI
    artifact_dest = Path("C:/Users/Ishfaq/.gemini/antigravity/brain/d9e9ed6c-fb3b-452f-9c13-c9bc4fbdfd6d/heart_attack_cinematic.mp4")
    shutil.copyfile(final_mp4, artifact_dest)
    print(f"[assembly] Artifact copied to: {artifact_dest}")


if __name__ == "__main__":
    assemble()
