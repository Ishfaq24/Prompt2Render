"""Legacy assembly path for clips without cue-aware scene timing.

This module is intentionally conservative:

* never speed-ramps generated visuals to match narration;
* holds the final video frame when narration is longer;
* trims excessive visual tail when it exceeds the configured tolerance;
* prefers alignment-derived captions whenever available;
* falls back to deterministic proportional captions only when alignment is
  unavailable;
* uses temporary/intermediate files so a failed FFmpeg invocation does not
  leave a misleading final artifact.

Scene-kit output should normally use the newer plan/encode/finish pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import cfg
from .project import Script, Section


MAX_TRAILING_SILENCE = 2.0
CAPTION_CHARS = 84
_DURATION_EPSILON = 0.05


def _sync_section(
    sec: Section,
    out: Path,
    vopts: list[str],
) -> Path:
    """Synchronize one legacy visual clip with its audio."""

    if sec.video is None or sec.audio is None:
        raise ValueError(
            f"section {sec.stem} has no bound video/audio"
        )

    vdur = cfg.duration(sec.video)
    adur = cfg.duration(sec.audio)

    if vdur <= 0:
        raise SystemExit(
            f"[prompt2render] section {sec.stem}: "
            "visual has no usable duration"
        )

    if adur <= 0:
        raise SystemExit(
            f"[prompt2render] section {sec.stem}: "
            "audio has no usable duration"
        )

    filters: list[str] = []

    if vdur < adur - _DURATION_EPSILON:
        # Hold the final frame. Do not alter playback speed because that
        # changes the visual timing and can invalidate mathematical/algorithmic
        # demonstrations.
        pad = adur - vdur + 0.15
        filters.append(
            f"tpad=stop_mode=clone:"
            f"stop_duration={pad:.3f}"
        )

    elif vdur > adur + MAX_TRAILING_SILENCE:
        # Trim only a genuinely excessive visual tail. Keep a small cushion
        # because -shortest and codec timestamps can otherwise clip the final
        # spoken audio frame.
        trim_to = adur + 0.5

        cfg.say(
            f"  section {sec.stem}: trimming "
            f"{vdur:.1f}s video to {trim_to:.1f}s"
        )

        filters.extend(
            [
                f"trim=duration={trim_to:.3f}",
                "setpts=PTS-STARTPTS",
            ]
        )

    audio_filters = [
        "apad",
    ]

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(sec.video),
        "-i",
        str(sec.audio),
    ]

    if filters:
        command.extend(
            [
                "-vf",
                ",".join(filters),
            ]
        )

    command.extend(
        [
            "-af",
            ",".join(audio_filters),
            "-shortest",
            *vopts,
            "-c:a",
            "aac",
            "-b:a",
            cfg.AAC_BITRATE,
            "-ar",
            str(cfg.AUDIO_SR),
            "-ac",
            "1",
            str(out),
        ]
    )

    cfg.run(command)

    if not out.exists():
        raise SystemExit(
            f"[prompt2render] FFmpeg did not produce "
            f"{out}"
        )

    return out


def _split_caption(
    text: str,
) -> list[str]:
    """Split narration into readable SRT-sized caption chunks."""

    text = re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()

    if not text:
        return []

    # Prefer punctuation boundaries, then hard word boundaries.
    parts = re.split(
        r"(?<=[.!?;:,])\s+",
        text,
    )

    chunks: list[str] = []
    buffer = ""

    for part in parts:
        part = part.strip()

        if not part:
            continue

        while len(part) > CAPTION_CHARS:
            cut = part.rfind(
                " ",
                0,
                CAPTION_CHARS + 1,
            )

            if cut <= 0:
                cut = CAPTION_CHARS

            chunks.append(
                part[:cut].strip()
            )
            part = part[cut:].strip()

        candidate = (
            f"{buffer} {part}".strip()
            if buffer
            else part
        )

        if len(candidate) <= CAPTION_CHARS:
            buffer = candidate
        else:
            if buffer:
                chunks.append(
                    buffer
                )
            buffer = part

    if buffer:
        chunks.append(
            buffer
        )

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


def _ts(
    t: float,
) -> str:
    """Format seconds as an SRT timestamp."""

    t = max(
        0.0,
        float(t),
    )

    # Convert through integer milliseconds first. This avoids the subtle
    # 999.999ms rounding case in the original implementation.
    total_ms = int(
        round(
            t * 1000.0
        )
    )

    hours, remainder = divmod(
        total_ms,
        3_600_000,
    )

    minutes, remainder = divmod(
        remainder,
        60_000,
    )

    seconds, milliseconds = divmod(
        remainder,
        1_000,
    )

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds:02d},"
        f"{milliseconds:03d}"
    )


def _write_srt_atomic(
    lines: list[str],
    dst: Path,
) -> Path:
    """Write an SRT atomically."""

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = dst.with_name(
        dst.name + ".tmp"
    )

    tmp.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    tmp.replace(
        dst
    )

    return dst


def write_srt(
    script: Script,
    dst: Path,
    proj: Path | None = None,
) -> Path:
    """Write captions, preferring word/sentence alignment when available."""

    if proj is not None:
        align_dir = (
            proj
            / "build"
            / "align"
        )

        if align_dir.exists():
            try:
                from . import captions

                cfg.say(
                    "captions from the alignment"
                )

                result = captions.write_srt(
                    proj,
                    script,
                    dst,
                )

                if result.exists():
                    return result

            except (
                OSError,
                ValueError,
                KeyError,
                SystemExit,
            ) as exc:
                cfg.warn(
                    "no usable alignment — "
                    f"falling back to proportional timing ({exc})"
                )

    lines: list[str] = []
    number = 0

    for sec in script.sections:
        chunks = _split_caption(
            sec.narration
        )

        if not chunks:
            continue

        total_chars = sum(
            len(chunk)
            for chunk in chunks
        )

        if total_chars <= 0 or sec.dur <= 0:
            continue

        start = max(
            0.0,
            float(sec.start),
        )

        end = max(
            start,
            start + float(sec.dur),
        )

        t = start

        for index, chunk in enumerate(
            chunks
        ):
            if index == len(chunks) - 1:
                chunk_end = end
            else:
                span = (
                    float(sec.dur)
                    * len(chunk)
                    / total_chars
                )
                chunk_end = min(
                    end,
                    t + span,
                )

            # Never emit zero/negative-duration captions.
            if chunk_end <= t:
                continue

            number += 1

            lines.extend(
                [
                    str(number),
                    f"{_ts(t)} --> {_ts(chunk_end)}",
                    chunk,
                    "",
                ]
            )

            t = chunk_end

    return _write_srt_atomic(
        lines,
        dst,
    )


def chapters(
    script: Script,
) -> str:
    """Return FFmpeg/YouTube-compatible chapter timestamps."""

    lines: list[str] = []

    for sec in script.sections:
        start = max(
            0.0,
            float(sec.start),
        )

        total_seconds = int(
            start
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            stamp = (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )
        else:
            stamp = (
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        lines.append(
            f"{stamp} {sec.title}"
        )

    if lines and script.sections:
        # Preserve the existing public behavior: first chapter is anchored
        # explicitly at 00:00.
        first_title = script.sections[0].title
        lines[0] = (
            f"00:00 {first_title}"
        )

    return "\n".join(lines)


def _concat_file_entry(
    path: Path,
) -> str:
    """Produce a concat-demuxer file entry.

    Use single-quote escaping because section stems can contain apostrophes.
    """

    value = str(
        path.name
    ).replace(
        "'",
        "'\\''",
    )

    return (
        f"file '{value}'\n"
    )


def assemble(
    proj: Path,
    script: Script,
    burn_captions: bool = False,
) -> Path:
    """Assemble legacy section clips into the final video."""

    cfg.need(
        "ffmpeg",
        "ffprobe",
    )

    build = (
        proj
        / "build"
    )
    out = (
        proj
        / "out"
    )

    build.mkdir(
        parents=True,
        exist_ok=True,
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not script.sections:
        raise SystemExit(
            "[prompt2render] cannot assemble an empty script"
        )

    vopts = cfg.pick_vopts()

    clock = 0.0
    parts: list[Path] = []

    for sec in script.sections:
        video = (
            proj
            / "sections"
            / f"{sec.stem}.mp4"
        )

        audio = (
            proj
            / "audio"
            / f"{sec.stem}.m4a"
        )

        if not video.exists():
            raise SystemExit(
                f"[prompt2render] missing visual for "
                f"section {sec.stem}: {video}"
            )

        if not audio.exists():
            raise SystemExit(
                f"[prompt2render] missing audio for "
                f"section {sec.stem} — run narrate"
            )

        sec.video = video
        sec.audio = audio

        cfg.say(
            f"syncing section {sec.stem} — "
            f"{sec.title}"
        )

        piece = _sync_section(
            sec,
            build
            / f"sync_{sec.stem}.mp4",
            vopts,
        )

        sec.start = clock
        sec.dur = cfg.duration(
            piece
        )

        if sec.dur <= 0:
            raise SystemExit(
                f"[prompt2render] synced section "
                f"{sec.stem} has no usable duration"
            )

        clock += sec.dur
        parts.append(
            piece
        )

    listfile = (
        build
        / "concat.txt"
    )

    listfile.write_text(
        "".join(
            _concat_file_entry(path)
            for path in parts
        ),
        encoding="utf-8",
    )

    merged = (
        build
        / "merged.mp4"
    )

    cfg.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listfile),
            "-c",
            "copy",
            str(merged),
        ],
        cwd=str(build),
    )

    if not merged.exists():
        raise SystemExit(
            "[prompt2render] FFmpeg did not produce "
            f"{merged}"
        )

    srt = write_srt(
        script,
        out / "captions.srt",
        proj,
    )

    final = (
        out
        / "final.mp4"
    )

    if burn_captions:
        # Pass an absolute subtitle path through the subtitles filter. The
        # filter is sensitive to working-directory assumptions and Windows
        # drive-letter escaping, so use the existing output cwd and filename
        # where possible.
        subtitle_name = srt.name

        subtitle_filter = (
            "subtitles="
            f"{subtitle_name}:"
            "force_style="
            f"'FontName={cfg.CAPTION_FONT},"
            f"FontSize={cfg.CAPTION_FONT_SIZE},"
            "Bold=1,"
            "PrimaryColour=&HFFFFFF&,"
            "OutlineColour=&H80000000&,"
            "BorderStyle=3,"
            "Outline=1,"
            "MarginV=48'"
        )

        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(merged),
                "-vf",
                subtitle_filter,
                *cfg.pick_vopts(),
                "-c:a",
                "copy",
                str(final),
            ],
            cwd=str(out),
        )

    else:
        # Keep captions as a soft subtitle track. The standalone SRT remains
        # available for platforms that prefer external captions.
        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(merged),
                "-i",
                str(srt),
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "mov_text",
                "-movflags",
                "+faststart",
                str(final),
            ]
        )

    if not final.exists():
        raise SystemExit(
            "[prompt2render] FFmpeg did not produce "
            f"{final}"
        )

    total = cfg.duration(
        final
    )

    cfg.say(
        f"final: {final} "
        f"({total / 60:.1f} min)"
    )

    thumb = (
        out
        / "thumb_source.png"
    )

    # Avoid seeking exactly to the end on very short clips.
    seek = max(
        0.0,
        total * 0.45,
    )

    cfg.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{seek:.2f}",
            "-i",
            str(final),
            "-frames:v",
            "1",
            str(thumb),
        ]
    )

    return final


__all__ = [
    "CAPTION_CHARS",
    "MAX_TRAILING_SILENCE",
    "assemble",
    "chapters",
    "write_srt",
]