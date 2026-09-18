"""Conform real-world video & B-roll footage to match section duration and format.

Enables Prompt2Render to mix live-action footage, microscopy, lab b-roll,
and stock video clips with mathematical and 3D animations in a hybrid documentary style.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Sequence

from . import align, cfg
from .project import Script, Section


def resolve_video_asset(proj: Path, sec: Section) -> Path | None:
    """Find a matching real-world video file for the given section."""
    # 1. Explicit source_media attribute
    if sec.source_media:
        candidates = [
            Path(sec.source_media),
            proj / sec.source_media,
            proj / "assets" / sec.source_media.name,
            proj / "assets" / "videos" / sec.source_media.name,
        ]
        for c in candidates:
            if c.is_file():
                return c.resolve()

    # 2. Check sections folder for manual clip
    sec_cand = proj / "sections" / f"{sec.stem}.mp4"
    if sec_cand.is_file():
        return sec_cand.resolve()

    # 3. Check assets/videos directory for matches with section keywords
    videos_dir = proj / "assets" / "videos"
    if not videos_dir.is_dir():
        videos_dir = proj / "assets"

    if videos_dir.is_dir():
        video_exts = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
        available = [p for p in videos_dir.iterdir() if p.suffix.lower() in video_exts]
        
        # Check by section stem (e.g. 01.mp4 or scene_01.mp4)
        for p in available:
            if sec.stem in p.stem:
                return p.resolve()

        # Check by title keywords
        keywords = [w.lower() for w in re.split(r'\W+', sec.title) if len(w) > 3]
        for p in available:
            p_words = [w.lower() for w in re.split(r'\W+', p.stem)]
            if any(k in p_words for k in keywords):
                return p.resolve()

        # Fallback to the first available video if only one exists
        if len(available) == 1:
            return available[0].resolve()

    return None


def conform_video(
    src_video: Path,
    out_mp4: Path,
    duration_s: float,
    *,
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
) -> Path:
    """Conform an input video to project video specs and exact section duration."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    duration_s = max(0.5, float(duration_s))
    w = width or cfg.WIDTH
    h = height or cfg.HEIGHT
    f = fps or cfg.FPS

    # Scale to cover target dimensions without distorting aspect ratio, then crop to center
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"fps={f}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(src_video),
        "-t", f"{duration_s:.3f}",
        "-vf", vf,
        *cfg.VOPTS,
        "-an",
        str(out_mp4),
    ]

    cfg.say(f"conforming real-world video {src_video.name} -> {out_mp4.name} ({duration_s:.2f}s)")
    cfg.run(cmd)
    return out_mp4


def create_placeholder_video(
    out_mp4: Path,
    duration_s: float,
    title: str,
    *,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Generate a clean dark placeholder clip when no raw video file is present."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    duration_s = max(0.5, float(duration_s))

    safe_title = re.sub(r'[^a-zA-Z0-9 _-]', '', title).strip()[:35]
    text_content = f"REAL-WORLD VIDEO - {safe_title}" if safe_title else "REAL-WORLD VIDEO"
    vf = (
        f"drawtext=text='{text_content}':"
        f"fontcolor=white:fontsize=44:x=(w-text_w)/2:y=(h-text_h)/2"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=#0d1117:s={width}x{height}:r={fps}:d={duration_s:.3f}",
        "-vf", vf,
        *cfg.VOPTS,
        "-an",
        str(out_mp4),
    ]

    cfg.warn(f"no source video found; generating placeholder -> {out_mp4.name} ({duration_s:.2f}s)")
    try:
        cfg.run(cmd)
    except (Exception, SystemExit):
        # Fallback if drawtext filter lacks fonts
        cmd_nofont = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=#0d1117:s={width}x{height}:r={fps}:d={duration_s:.3f}",
            *cfg.VOPTS,
            "-an",
            str(out_mp4),
        ]
        cfg.run(cmd_nofont)
    return out_mp4


def conform_video_for_section(
    proj: Path,
    script: Script,
    sec: Section,
    out_mp4: Path,
) -> Path:
    """Resolve duration and source video for section, conforming into out_mp4."""
    # 1. Determine duration from Whisper alignment
    dur = 5.0
    try:
        data = align.load(proj, sec.stem)
        sents = data.get("sentences", [])
        if sents:
            dur = float(sents[-1]["end"])
    except Exception:
        if sec.dur > 0:
            dur = sec.dur
        else:
            audio_path = proj / "audio" / f"{sec.stem}.wav"
            if audio_path.is_file():
                dur = cfg.duration(audio_path)

    # 2. Locate source video asset
    src_video = resolve_video_asset(proj, sec)

    if src_video and src_video.is_file():
        return conform_video(src_video, out_mp4, dur)
    else:
        return create_placeholder_video(out_mp4, dur, sec.title)
