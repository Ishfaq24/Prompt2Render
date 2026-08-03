"""Per-stage stdout line parsers -> progress updates.

Every pipeline stage already prints one line per meaningful unit of work
via `cfg.say()` (flushed immediately) -- a section during voice/align/
scenes/stills/plan, a clip during encode, a gate during check. These
parsers turn that stdout, which the job runner (see jobs.py) is already
reading line by line from the stage's own subprocess, into a `{done,
total, pct, mode}` update the browser renders as a progress bar.

`total` is never guessed from stdout: the caller (routes_pipeline.py)
computes it once, before the job starts, from files already on disk (e.g.
`len(script.sections)`, or the clip count in `build/plan.json`) and seeds
`job.progress["total"]`. A parser is only ever invoked against lines from
its own stage's job (`PARSERS[job.stage]`), so there is no cross-stage
ambiguity even though several stages print similarly-shaped
"section NN: ..." lines.

`build` runs the whole chain inside one subprocess with no clean
structural separator between stages in its combined stdout, so rather than
guess at a fragile cross-stage fraction, its progress stays indeterminate
-- the live log panel (which shows every line verbatim) already carries
the real detail, and anyone wanting a precise bar can run stages
individually from the pipeline panel.
"""
from __future__ import annotations

import re
from typing import Callable

_SECTION_LINE = re.compile(r"^\[fdx\] section (\w+): ")
_SECTION_ACCEPTED = re.compile(r"^\[fdx\] section (\w+): accepted — ")
_STILLS_DONE = re.compile(r"^\[fdx\] section (\w+): \d+ stills")
_PLAN_DONE = re.compile(r"^\[fdx\] section (\w+): \d+ stills over")
_CLIP_DONE = re.compile(r"^\[fdx\]  (\S+\.mp4)\s+[\d.]+s\s+\w+$")
_FINISH_SECTION = re.compile(r"^\[fdx\] (\w+): \d+ clips -> \d+ frames$")
_GATE_LINE = re.compile(r"^\[fdx\] gate: (.+)$")
_DRIFT_SECTION = re.compile(r"^\[fdx\] caption drift: section (\w+) checked$")
_ALIGN_CONF = re.compile(r"^\[fdx\] section (\w+): \S+\s+conf ")
_SLOW_STEP = "this is the slow step"


def _advance(job, key: str) -> None:
    """Count `key` toward `done` exactly once per job, however many times
    a matching line appears (retries, re-announcements, etc.)."""
    if key in job.seen:
        return
    job.seen.add(key)
    job.progress["done"] = len(job.seen)
    total = job.progress.get("total") or 0
    job.progress["pct"] = round(100 * job.progress["done"] / total, 1) if total else 0.0
    job.progress["mode"] = "determinate"


def _voice(job, line: str) -> None:
    if m := _SECTION_LINE.match(line):
        _advance(job, m.group(1))


def _align(job, line: str) -> None:
    if _SLOW_STEP in line:
        # The one big whole-programme whisper pass: no per-item fraction
        # exists yet, so say so rather than sitting at "0%" for the ~80
        # minutes this can take on a slow machine.
        job.progress["mode"] = "indeterminate"
        return
    if m := _ALIGN_CONF.match(line):
        _advance(job, m.group(1))


def _scenes(job, line: str) -> None:
    if m := _SECTION_ACCEPTED.match(line):
        _advance(job, m.group(1))


def _stills(job, line: str) -> None:
    if m := _STILLS_DONE.match(line):
        _advance(job, m.group(1))


def _plan(job, line: str) -> None:
    if m := _PLAN_DONE.match(line):
        _advance(job, m.group(1))


def _encode(job, line: str) -> None:
    if m := _CLIP_DONE.match(line):
        _advance(job, m.group(1))


def _finish(job, line: str) -> None:
    if m := _FINISH_SECTION.match(line):
        _advance(job, m.group(1))


def _check(job, line: str) -> None:
    if m := _GATE_LINE.match(line):
        _advance(job, m.group(1))
        job.progress["note"] = f"running gate: {m.group(1)}"
    elif m := _DRIFT_SECTION.match(line):
        # Sub-progress within the caption-drift gate -- by far the longest
        # one -- surfaced as a note rather than a second progress bar.
        job.drift_seen.add(m.group(1))
        total = len(job.drift_total) if job.drift_total else "?"
        job.progress["note"] = (
            f"caption drift: {len(job.drift_seen)}/{total} sections checked")


def _build(job, line: str) -> None:
    return None  # deliberately indeterminate; see module docstring


PARSERS: dict[str, Callable[["object", str], None]] = {
    "voice": _voice, "align": _align, "scenes": _scenes, "stills": _stills,
    "plan": _plan, "encode": _encode, "finish": _finish, "check": _check,
    "build": _build,
}
