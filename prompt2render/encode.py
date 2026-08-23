"""Encode timeline stills into independent, resumable video clips.

Each timeline row becomes exactly one clip. Motion is baked into that clip so
later stages can concatenate or stream-copy clips without knowing how the
transition was produced.

Transition policy is intentionally small:
* first clip: fade in from black;
* ordinary state/reveal/section changes: dissolve;
* chapter/section changes can use the longer ``section`` dissolve.

The implementation is resumable and concurrency-safe:
* stale clips are detected from source modification times;
* every encode is written to a ``.part.mp4`` sidecar first;
* missing inputs fail before ffmpeg is launched;
* worker failures propagate to the caller;
* completion is reported only after the output has been atomically installed.
"""

from __future__ import annotations

import shutil
import sys
import threading
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from pathlib import Path

from . import cfg


DISSOLVE = {
    "state": 0.35,
    "reveal": 0.20,
    "section": 0.50,
}

OPEN_FADE = 0.60

# ffmpeg subprocesses release the GIL while waiting, so threads provide useful
# concurrency without process-pickling overhead.
_LOG_LOCK = threading.Lock()


def _clip_paths(
    proj: Path,
    row: dict,
) -> tuple[Path, Path, Path | None]:
    """Resolve the clip, current still, and optional previous still."""
    try:
        clip = proj / row["clip"]
        png = proj / row["png"]
    except KeyError as exc:
        raise ValueError(
            f"timeline clip row is missing required key {exc.args[0]!r}: {row!r}"
        ) from exc

    prev_value = row.get("prev_png")
    prev = (
        proj / prev_value
        if prev_value
        else None
    )

    return clip, png, prev


def _duration_from_row(row: dict) -> float:
    """Return the requested clip duration in seconds."""
    try:
        frames = int(row["frames"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid/missing frames in timeline row: {row!r}"
        ) from exc

    if frames <= 0:
        raise ValueError(
            f"timeline row has non-positive frame count: {frames}"
        )

    fps = float(cfg.FPS)

    if fps <= 0:
        raise ValueError(
            f"cfg.FPS must be positive, got {cfg.FPS!r}"
        )

    return frames / fps


def _cmd(
    row: dict,
    png: Path,
    prev: Path | None,
    out: Path,
    vopts: list[str],
) -> list[str]:
    """Build the deterministic ffmpeg command for one timeline row."""
    n = int(row["frames"])
    secs = _duration_from_row(row)

    base = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
    ]

    if prev is None:
        # First clip: fade in from black.
        duration = min(
            OPEN_FADE,
            secs / 2.0,
        )

        filters = [
            f"fps={cfg.FPS}",
            "format=yuv420p",
        ]

        if duration > 0:
            filters.append(
                f"fade=t=in:st=0:d={duration:.3f}"
            )

        return base + [
            "-loop", "1",
            "-framerate", str(cfg.FPS),
            "-i", str(png),
            "-vf", ",".join(filters),
            "-frames:v", str(n),
            *vopts,
            str(out),
        ]

    duration = float(
        DISSOLVE.get(
            row.get("kind"),
            DISSOLVE["state"],
        )
    )

    # xfade requires both inputs to have a compatible time base and enough
    # frames for the transition. Clamp the dissolve to the clip duration while
    # keeping at least one frame available.
    frame_time = 1.0 / float(cfg.FPS)
    duration = min(
        duration,
        max(secs / 2.0, frame_time),
    )

    graph = (
        f"[0:v]settb=AVTB,fps={cfg.FPS},format=yuv420p[a];"
        f"[1:v]settb=AVTB,fps={cfg.FPS},format=yuv420p[b];"
        f"[a][b]xfade="
        f"transition=fade:"
        f"duration={duration:.3f}:"
        f"offset=0[v]"
    )

    return base + [
        "-loop", "1",
        "-framerate", str(cfg.FPS),
        "-t", f"{duration:.3f}",
        "-i", str(prev),

        "-loop", "1",
        "-framerate", str(cfg.FPS),
        "-t", f"{secs:.3f}",
        "-i", str(png),

        "-filter_complex", graph,
        "-map", "[v]",
        "-frames:v", str(n),
        *vopts,
        str(out),
    ]


def _needs_encode(
    proj: Path,
    row: dict,
) -> bool:
    """Return whether a clip is missing, invalid, or older than its sources."""
    clip, png, prev = _clip_paths(
        proj,
        row,
    )

    try:
        clip_stat = clip.stat()
    except OSError:
        return True

    if clip_stat.st_size <= 2048:
        return True

    # A current clip can only be trusted if all of its required sources exist
    # and are no newer than the clip. Missing sources are handled explicitly by
    # _encode_one rather than silently treating the old clip as valid.
    sources = [png]

    if prev is not None:
        sources.append(prev)

    for source in sources:
        try:
            source_stat = source.stat()
        except OSError:
            return True

        if source_stat.st_mtime_ns > clip_stat.st_mtime_ns:
            return True

    return False


def _validate_inputs(
    png: Path,
    prev: Path | None,
) -> None:
    """Fail with an actionable message before spawning ffmpeg."""
    if not png.exists():
        raise FileNotFoundError(
            f"missing still {png} — run `prompt2render stills`"
        )

    if not png.is_file():
        raise FileNotFoundError(
            f"still is not a regular file: {png}"
        )

    if prev is not None:
        if not prev.exists():
            raise FileNotFoundError(
                f"missing previous still {prev} — "
                "run `prompt2render stills`"
            )
        if not prev.is_file():
            raise FileNotFoundError(
                f"previous still is not a regular file: {prev}"
            )


def _encode_one(
    row: dict,
    proj: Path,
    vopts: list[str],
) -> None:
    """Encode one clip transactionally."""
    clip, png, prev = _clip_paths(
        proj,
        row,
    )

    _validate_inputs(
        png,
        prev,
    )

    clip.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # A unique-ish per-process sidecar prevents an interrupted encode from
    # being mistaken for a completed clip. Do not use the final path directly.
    part = clip.with_name(
        clip.stem + ".part.mp4"
    )

    # Remove a stale partial file from an earlier interrupted run.
    part.unlink(
        missing_ok=True
    )

    command = _cmd(
        row,
        png,
        prev,
        part,
        vopts,
    )

    try:
        cfg.run(command)

        # A successful ffmpeg invocation should have produced a meaningful
        # output. Treat an empty/truncated sidecar as failure.
        try:
            size = part.stat().st_size
        except OSError as exc:
            raise RuntimeError(
                f"ffmpeg reported success but produced no output: {part}"
            ) from exc

        if size <= 2048:
            raise RuntimeError(
                f"ffmpeg produced a suspiciously small clip "
                f"({size} bytes): {part}"
            )

        # Path.replace is atomic when source and destination are on the same
        # filesystem. On Windows it may fail if another process has the target
        # open; retain the copy fallback used by the original implementation.
        try:
            part.replace(clip)
        except OSError:
            shutil.copyfile(
                part,
                clip,
            )
            part.unlink(
                missing_ok=True
            )

    except BaseException:
        # Never leave a failed/aborted partial file behind.
        part.unlink(
            missing_ok=True
        )
        raise

    seconds = row.get(
        "seconds",
        f"{_duration_from_row(row):.3f}",
    )

    with _LOG_LOCK:
        cfg.say(
            f"  {clip.name}  {seconds}s  "
            f"{row.get('kind', 'state')}"
        )


def encode(
    proj: Path,
    limit: int | None = None,
    preview: bool = False,
    jobs: int = 1,
) -> int:
    """Encode all stale timeline clips and return the number remaining."""
    from . import timeline

    plan = timeline.load(proj)

    rows = plan.get("clips", [])

    if not isinstance(rows, list):
        raise ValueError(
            "timeline.load() returned a plan whose 'clips' field is not a list"
        )

    (
        proj
        / "build"
        / "clips"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        workers = max(
            1,
            int(jobs),
        )
    except (TypeError, ValueError):
        workers = 1

    vopts = cfg.pick_vopts(
        preview
    )

    if preview:
        cfg.warn(
            "preview encode (nvenc) — do not mix these clips with a "
            "final render; re-encode before `prompt2render finish`"
        )

    # Selection remains deterministic and in timeline order. Encoding itself
    # is safe to parallelize because every clip depends only on its own still
    # and the previous still.
    todo: list[dict] = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(
                f"invalid timeline clip row: {row!r}"
            )

        if not _needs_encode(
            proj,
            row,
        ):
            continue

        if (
            limit is not None
            and len(todo) >= max(0, int(limit))
        ):
            break

        todo.append(row)

    done = 0

    if todo:
        with ThreadPoolExecutor(
            max_workers=workers
        ) as pool:
            futures = [
                pool.submit(
                    _encode_one,
                    row,
                    proj,
                    vopts,
                )
                for row in todo
            ]

            try:
                for future in as_completed(
                    futures
                ):
                    future.result()
                    done += 1
            except BaseException:
                # Fail fast. Cancel futures that have not started; running
                # ffmpeg processes cannot be forcibly cancelled by Future.cancel,
                # but their exceptions will not be silently swallowed.
                for future in futures:
                    future.cancel()
                raise

    remaining = sum(
        1
        for row in rows
        if _needs_encode(
            proj,
            row,
        )
    )

    cfg.say(
        f"encoded {done} this pass, "
        f"{remaining} remaining"
    )

    return remaining


__all__ = [
    "encode",
]