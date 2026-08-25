"""Assemble encoded clips into sections and produce the final MP4.

The finish stage is intentionally conservative:

1. preflight every clip before any concatenation;
2. require one compatible video encoder profile for stream-copy concatenation;
3. concatenate clips into independent section files;
4. verify each section's frame count against the audio timeline;
5. concatenate sections into one silent programme;
6. optionally burn captions in a separate encode;
7. mux the single mastered audio track, subtitles, and chapter metadata.

The audio is never concatenated per section. ``build/master.m4a`` is the single
programme audio clock, avoiding cumulative AAC priming gaps.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from . import captions, cfg, encode, timeline, voice
from .project import Script


def _concat(
    files: list[str],
    dst: Path,
    cwd: Path,
) -> None:
    """Concatenate compatible MP4 files using stream copy.

    ``files`` are interpreted relative to ``cwd`` by ffmpeg's concat demuxer.
    The list is written beside the output and removed after a successful run.
    """
    if not files:
        raise ValueError(
            f"cannot concatenate an empty file list into {dst}"
        )

    cwd.mkdir(
        parents=True,
        exist_ok=True
    )
    dst.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    list_path = cwd / f".concat_{dst.stem}.txt"

    # Concat-demuxer paths need single-quote escaping. Keep the generated list
    # deterministic and safe for filenames containing spaces or apostrophes.
    def quote(path: str) -> str:
        return "'" + path.replace("'", "'\\''") + "'"

    list_path.write_text(
        "".join(
            f"file {quote(name)}\n"
            for name in files
        ),
        encoding="utf-8",
    )

    try:
        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(dst),
            ],
            cwd=str(cwd),
        )
    finally:
        list_path.unlink(
            missing_ok=True
        )

    if not dst.exists() or dst.stat().st_size <= 2048:
        raise RuntimeError(
            f"ffmpeg completed without producing a valid concat output: {dst}"
        )


def _preflight(
    proj: Path,
    rows: list[dict],
) -> None:
    """Verify clip freshness and stream-copy compatibility."""
    if not rows:
        sys.exit(
            "[prompt2render] timeline contains no clips — "
            "run `prompt2render plan`"
        )

    stale = [
        r["clip"]
        for r in rows
        if encode._needs_encode(proj, r)
    ]

    if stale:
        shown = ", ".join(
            stale[:5]
        )
        extra = (
            f" (+{len(stale) - 5} more)"
            if len(stale) > 5
            else ""
        )
        sys.exit(
            "[prompt2render] clip(s) missing or older than the still they "
            f"were rendered from: {shown}{extra} — run "
            "`prompt2render encode --all`"
        )

    # video_params() is intentionally used rather than merely comparing codec
    # names. Stream-copy concatenation requires compatible codec/extradata
    # parameters, not just "all are H.264".
    all_params = cfg.parallel(
        lambda row: cfg.video_params(
            proj / row["clip"]
        ),
        rows,
        cfg.probe_jobs(),
        "preflight",
    )

    if len(all_params) != len(rows):
        raise RuntimeError(
            "preflight returned a different number of probe results "
            f"({len(all_params)}) than clips ({len(rows)})"
        )

    ref = all_params[0]
    ref_row = rows[0]

    for row, params in zip(
        rows[1:],
        all_params[1:],
    ):
        if params != ref:
            keys = set(ref) | set(params)
            diff = {
                key: (
                    ref.get(key),
                    params.get(key),
                )
                for key in sorted(keys)
                if ref.get(key) != params.get(key)
            }

            sys.exit(
                f"[prompt2render] {row['clip']} was encoded differently "
                f"from {ref_row['clip']} and cannot be stream-copy "
                "concatenated:\n"
                f"      {diff}\n"
                "      delete build/clips and re-run "
                "`prompt2render encode --all` "
                "(a --preview pass cannot be mixed with a final one)"
            )

    cfg.say(
        f"preflight: {len(rows)} clips share one encoder profile "
        f"({ref.get('codec_name', '?')} "
        f"{ref.get('profile', '?')} "
        f"{ref.get('pix_fmt', '?')})"
    )


def _chapters(
    proj: Path,
    script: Script,
    dst: Path,
) -> Path:
    """Write FFmetadata chapters using the master-audio clock."""
    amap = voice.audio_map(
        proj
    )

    lines = [
        ";FFMETADATA1",
        f"title={script.title}",
        "",
    ]

    for section in script.sections:
        try:
            info = amap["sections"][section.stem]
            start = float(info["start"])
            duration = float(info["dur"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"audio map has no valid timing for section "
                f"{section.stem}"
            ) from exc

        if start < 0 or duration < 0:
            raise RuntimeError(
                f"invalid chapter timing for section "
                f"{section.stem}: start={start}, dur={duration}"
            )

        # FFmetadata chapter timestamps use the declared TIMEBASE. Rounding
        # here is intentional: chapter positions are integer milliseconds.
        start_ms = max(
            0,
            round(start * 1000)
        )
        end_ms = max(
            start_ms,
            round((start + duration) * 1000)
        )

        # FFmetadata treats '=' specially in values only in some contexts;
        # escaping backslash/newline/semicolon keeps titles robust.
        title = (
            str(section.title)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(";", "\\;")
            .replace("=", "\\=")
        )

        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={title}",
                "",
            ]
        )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    dst.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return dst


def _thumbnail(
    proj: Path,
    rows: list[dict],
    dst: Path,
) -> None:
    """Use the longest-lived state/section still as the thumbnail."""
    if not rows:
        return

    states = [
        row
        for row in rows
        if row.get("kind") in (
            "state",
            "section",
        )
    ] or rows

    best = max(
        states,
        key=lambda row: int(row.get("frames", 0)),
    )

    src = proj / best["png"]

    if not src.exists():
        cfg.warn(
            f"thumbnail source is missing: {src}"
        )
        return

    dst.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Copy the original PNG rather than extracting a compressed frame from
    # H.264. This preserves the quality of the scene renderer's output.
    shutil.copyfile(
        src,
        dst,
    )

    cfg.say(
        f"thumbnail from {best.get('name', best.get('png', 'still'))} "
        f"({best.get('seconds', '?')}s on screen)"
    )


def _section_rows(
    script: Script,
    rows: list[dict],
) -> dict[str, list[dict]]:
    """Group timeline clips by section while preserving plan order."""
    known = {
        section.stem
        for section in script.sections
    }

    grouped = {
        section.stem: []
        for section in script.sections
    }

    for row in rows:
        section = row.get("section")

        if section not in known:
            raise SystemExit(
                f"[prompt2render] timeline clip "
                f"{row.get('name', row.get('clip', '?'))} references "
                f"unknown section {section!r}"
            )

        grouped[section].append(row)

    return grouped


def _check_master_audio(
    proj: Path,
    path: Path,
) -> None:
    """Validate the required programme audio before video assembly."""
    if not path.exists():
        sys.exit(
            "[prompt2render] no build/master.m4a — "
            "run `prompt2render voice`"
        )

    if path.stat().st_size <= 2048:
        sys.exit(
            f"[prompt2render] master audio is empty/truncated: {path} — "
            "run `prompt2render voice`"
        )


def _mux_final(
    video: Path,
    master: Path,
    srt: Path,
    metadata: Path,
    final: Path,
) -> None:
    """Mux the silent picture, master audio, captions and chapters."""
    final.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary = final.with_name(
        final.stem + ".part.mp4"
    )
    temporary.unlink(
        missing_ok=True
    )

    try:
        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",

                "-i", str(video),
                "-i", str(master),
                "-i", str(srt),
                "-i", str(metadata),

                "-map", "0:v:0",
                "-map", "1:a:0",
                "-map", "2:s:0",
                "-map_metadata", "3",

                "-c:v", "copy",
                "-c:a", "copy",
                "-c:s", "mov_text",

                "-metadata:s:s:0",
                "language=eng",

                "-movflags", "+faststart",
                str(temporary),
            ]
        )

        if not temporary.exists() or temporary.stat().st_size <= 2048:
            raise RuntimeError(
                f"ffmpeg produced an invalid final output: {temporary}"
            )

        try:
            temporary.replace(final)
        except OSError:
            shutil.copyfile(
                temporary,
                final,
            )
            temporary.unlink(
                missing_ok=True
            )

    except BaseException:
        temporary.unlink(
            missing_ok=True
        )
        raise


def finish(
    proj: Path,
    script: Script,
    burn: bool = False,
    style: str = "srt",
) -> Path:
    """Build and return ``out/final.mp4``."""
    cfg.need(
        "ffmpeg",
        "ffprobe",
    )

    plan = timeline.load(
        proj
    )

    rows = plan.get(
        "clips",
        []
    )

    if not isinstance(rows, list):
        raise RuntimeError(
            "timeline plan has an invalid 'clips' field"
        )

    build = proj / "build"
    out = proj / "out"

    out.mkdir(
        parents=True,
        exist_ok=True
    )
    (proj / "sections").mkdir(
        parents=True,
        exist_ok=True
    )

    _preflight(
        proj,
        rows,
    )

    amap = voice.audio_map(
        proj
    )

    master = build / "master.m4a"
    _check_master_audio(
        proj,
        master,
    )

    # 1. clips -> one silent MP4 per section.
    #
    # Every section is a stream-copy concatenation of its own clips. This
    # preserves the existing sections/<stem>.mp4 contract and keeps legacy
    # import/assemble paths compatible.
    by_section = _section_rows(
        script,
        rows,
    )

    for section in script.sections:
        if not by_section[section.stem]:
            sys.exit(
                f"[prompt2render] no clips planned for section "
                f"{section.stem}"
            )

    def join(section) -> int:
        destination = (
            proj
            / "sections"
            / f"{section.stem}.mp4"
        )

        # The concat list lives in build/clips, so these names are relative to
        # that directory. Use only basenames here; timeline paths are already
        # validated by preflight.
        filenames = [
            Path(row["clip"]).name
            for row in by_section[section.stem]
        ]

        _concat(
            filenames,
            destination,
            build / "clips",
        )

        return cfg.frame_count(
            destination
        )

    counts = cfg.parallel(
        join,
        list(script.sections),
        cfg.env_int(
            "P2R_CONCAT_JOBS",
            4,
        ),
        "concat",
    )

    if len(counts) != len(
        script.sections
    ):
        raise RuntimeError(
            "section concat returned an unexpected number of results"
        )

    for section, got in zip(
        script.sections,
        counts,
    ):
        try:
            target_duration = float(
                amap["sections"][section.stem]["dur"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"audio map has no valid duration for "
                f"section {section.stem}"
            ) from exc

        want = round(
            target_duration * cfg.FPS
        )

        if got != want:
            sys.exit(
                f"[prompt2render] section {section.stem} is "
                f"{got} frames but its audio is {want} — "
                "the plan and the encode disagree; re-run "
                "`prompt2render plan` then "
                "`prompt2render encode --all`"
            )

        cfg.say(
            f"section {section.stem}: "
            f"{len(by_section[section.stem])} clips "
            f"-> {got} frames"
        )

    # 2. sections -> full silent picture.
    section_files = [
        str(
            Path("..")
            / ".."
            / "sections"
            / f"{section.stem}.mp4"
        )
        for section in script.sections
    ]

    video = build / "video.mp4"

    _concat(
        section_files,
        video,
        build / "clips",
    )

    # 3. Captions and chapter metadata.
    srt = captions.write_srt(
        proj,
        script,
        out / "captions.srt",
    )

    metadata = _chapters(
        proj,
        script,
        build / "chapters.txt",
    )

    if not srt.exists() or srt.stat().st_size == 0:
        cfg.warn(
            "caption file is empty; final video will contain an empty "
            "subtitle stream"
        )

    final_video = video

    # Optional caption burn-in is intentionally a separate encode. Once
    # captions are burned, the resulting video is no longer the original
    # stream-copy video profile, but no later concatenation occurs.
    if burn:
        normalized_style = style.lower().strip()

        if normalized_style not in {
            "srt",
            "ass",
        }:
            raise ValueError(
                f"unsupported caption style {style!r}; "
                "expected 'srt' or 'ass'"
            )

        subtitle = (
            captions.write_ass(
                proj,
                script,
                out / "captions.ass",
            )
            if normalized_style == "ass"
            else srt
        )

        if normalized_style == "ass":
            vf = (
                f"ass={cfg.filter_path(subtitle)}"
            )
        else:
            vf = (
                f"subtitles={cfg.filter_path(subtitle)}:"
                "force_style='"
                f"FontName={cfg.CAPTION_FONT},"
                "FontSize=22,"
                "PrimaryColour=&HFFFFFF&,"
                "OutlineColour=&H80000000&,"
                "BorderStyle=3,"
                "Outline=1,"
                "MarginV=40'"
            )

        burned = build / "video_burned.mp4"
        burned.unlink(
            missing_ok=True
        )

        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i", str(video),
                "-vf", vf,
                *cfg.pick_vopts(),
                str(burned),
            ]
        )

        if not burned.exists() or burned.stat().st_size <= 2048:
            raise RuntimeError(
                f"caption burn-in produced an invalid video: {burned}"
            )

        final_video = burned

    # 4. Mux once. Audio is the single programme-level master, and is copied
    # without another encode. Subtitles remain selectable unless burn=True.
    _mux_final(
        final_video,
        master,
        srt,
        metadata,
        out / "final.mp4",
    )

    final = out / "final.mp4"

    total = cfg.duration(
        final
    )

    _thumbnail(
        proj,
        rows,
        out / "thumb_source.png",
    )

    cfg.say(
        f"final: {final}  "
        f"({total / 60:.2f} min)"
    )

    return final


def finish_manim(
    proj: Path,
    script: Script,
    section_clips: dict[str, Path],
    burn: bool = False,
    style: str = "srt",
) -> Path:
    """Build and return ``out/final.mp4`` from Manim's own per-section clips.

    Tier 2 Phase 8-9 (docs/ARCHITECTURE_AUDIT.md SS17, F12: "--manim disables
    the production tail... not shippable"). Unlike ``finish()``, this does
    not depend on ``timeline.load()``'s per-frame clip plan at all -- Manim
    already renders one complete video per section, so there is no per-frame
    Ken-Burns concatenation stage to run first (that stage, and the
    ``stills.manifest()`` it reads, is exactly the piece that made the
    production tail stills-only). Reuses the same renderer-agnostic building
    blocks ``finish()`` itself already uses for its own final assembly --
    ``_concat``, ``_check_master_audio``, ``captions.write_srt``,
    ``_chapters``, and ``_mux_final`` -- confirmed by reading them directly:
    none touch ``stills.*`` or the per-frame clip plan.

    Deliberately smaller in scope than ``finish()``: no thumbnail extraction
    (``_thumbnail`` needs the stills-specific per-frame ``rows``, which
    doesn't exist here) -- a known, non-blocking gap, not an oversight.
    """

    cfg.need(
        "ffmpeg",
        "ffprobe",
    )

    out = proj / "out"
    build = proj / "build"
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    for section in script.sections:
        clip = section_clips.get(section.stem)

        if clip is None or not clip.exists():
            sys.exit(
                f"[prompt2render] no rendered clip for section "
                f"{section.stem} -- run the Manim renderer first"
            )

    master = build / "master.m4a"
    _check_master_audio(
        proj,
        master,
    )

    # Manim clips live under scattered per-section directories
    # (build/manim/videos/scene_<stem>/...); _concat's ffmpeg concat demuxer
    # needs every input in one directory, so stage flat copies first -- the
    # same "one flat directory of clips" shape build/clips/ already has for
    # the stills pipeline.
    stage = build / "manim_finish"
    stage.mkdir(
        parents=True,
        exist_ok=True,
    )

    filenames: list[str] = []

    for section in script.sections:
        destination = stage / f"{section.stem}.mp4"
        shutil.copyfile(
            section_clips[section.stem],
            destination,
        )
        filenames.append(destination.name)

    video = build / "video.mp4"
    _concat(
        filenames,
        video,
        stage,
    )

    srt = captions.write_srt(
        proj,
        script,
        out / "captions.srt",
    )

    metadata = _chapters(
        proj,
        script,
        build / "chapters.txt",
    )

    if not srt.exists() or srt.stat().st_size == 0:
        cfg.warn(
            "caption file is empty; final video will contain an empty "
            "subtitle stream"
        )

    final_video = video

    if burn:
        normalized_style = style.lower().strip()

        if normalized_style not in {
            "srt",
            "ass",
        }:
            raise ValueError(
                f"unsupported caption style {style!r}; "
                "expected 'srt' or 'ass'"
            )

        subtitle = (
            captions.write_ass(
                proj,
                script,
                out / "captions.ass",
            )
            if normalized_style == "ass"
            else srt
        )

        if normalized_style == "ass":
            vf = (
                f"ass={cfg.filter_path(subtitle)}"
            )
        else:
            vf = (
                f"subtitles={cfg.filter_path(subtitle)}:"
                "force_style='"
                f"FontName={cfg.CAPTION_FONT},"
                "FontSize=22,"
                "PrimaryColour=&HFFFFFF&,"
                "OutlineColour=&H80000000&,"
                "BorderStyle=3,"
                "Outline=1,"
                "MarginV=40'"
            )

        burned = build / "video_burned.mp4"
        burned.unlink(
            missing_ok=True
        )

        cfg.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i", str(video),
                "-vf", vf,
                *cfg.pick_vopts(),
                str(burned),
            ]
        )

        if not burned.exists() or burned.stat().st_size <= 2048:
            raise RuntimeError(
                f"caption burn-in produced an invalid video: {burned}"
            )

        final_video = burned

    _mux_final(
        final_video,
        master,
        srt,
        metadata,
        out / "final.mp4",
    )

    final = out / "final.mp4"

    total = cfg.duration(
        final
    )

    cfg.say(
        f"final (manim): {final}  "
        f"({total / 60:.2f} min)"
    )

    return final


__all__ = [
    "finish",
    "finish_manim",
]