"""In-memory job tracking + subprocess runner for the web dashboard.

Every pipeline stage is invoked as its own `python fdx.py <stage> <slug>
...` subprocess -- never imported and called directly -- because nearly
every stage module calls `sys.exit()` on its failure paths
(`cfg.project_dir`, `project.parse_script`, `voice.audio_map`,
`align.load`, `scenes._keys`, ...). `SystemExit` is a `BaseException`, not
an `Exception`, and isn't guaranteed to be caught cleanly by ordinary
exception-handling middleware if it escapes inside a request handler.
Subprocessing sidesteps that entirely -- a `SystemExit` there just becomes
a normal nonzero exit code -- and it's also *why live log streaming works
for free*: `cfg.say()`/`cfg.warn()` already `print(..., flush=True)` at
every meaningful step, so reading the child process's stdout line by line
gives exactly the same live progress a terminal would show, with zero
changes needed to `cfg.py`/`voice.py`/etc. beyond what the speed-up work
already added.

Only one job may run at a time, server-wide (not per project): this
machine is weak enough on its own that two concurrent stages would fight
the parallelism already spent inside a single stage (see `fdx/encode.py`,
`fdx/qc.py`).
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .. import cfg
from . import progress as progress_mod

FDX_PY = str(cfg.ROOT / "fdx.py")
MAX_HISTORY = 20


@dataclass
class Job:
    id: str
    slug: str
    stage: str
    cmd: list[str]
    started_at: float
    ended_at: float | None = None
    status: str = "running"          # running | done | failed | cancelled
    returncode: int | None = None
    cancelled: bool = False
    log_lines: list[str] = field(default_factory=list)
    progress: dict = field(default_factory=lambda: {
        "done": 0, "total": 0, "pct": 0.0, "mode": "indeterminate", "note": ""})
    # Per-job bookkeeping the progress parsers use to count each
    # section/clip/gate exactly once regardless of retries.
    seen: set = field(default_factory=set)
    drift_seen: set = field(default_factory=set)
    drift_total: list = field(default_factory=list)

    def snapshot(self) -> dict:
        return {
            "id": self.id, "slug": self.slug, "stage": self.stage,
            "status": self.status, "returncode": self.returncode,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "progress": self.progress,
        }


class JobConflict(RuntimeError):
    """Raised when a job is requested while another is already running."""


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current: Job | None = None
        self._history: dict[str, Job] = {}
        self._history_order: list[str] = []
        self._procs: dict[str, subprocess.Popen] = {}
        self._subscribers: dict[str, list[queue.Queue]] = {}

    def get(self, job_id: str) -> Job | None:
        if self.current is not None and self.current.id == job_id:
            return self.current
        return self._history.get(job_id)

    def start(self, slug: str, stage: str, args: list[str] | None = None,
              total: int = 0, drift_total: list[str] | None = None) -> Job:
        args = args or []
        with self._lock:
            if self.current is not None:
                raise JobConflict(
                    f"a job is already running: {self.current.stage} on "
                    f"{self.current.slug} (job {self.current.id})")
            job = Job(id=uuid.uuid4().hex[:12], slug=slug, stage=stage,
                     cmd=[sys.executable, FDX_PY, stage, slug, *args],
                     started_at=time.time())
            job.progress["total"] = total
            if drift_total:
                job.drift_total = list(drift_total)
            self.current = job
            self._subscribers[job.id] = []
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def subscribe(self, job_id: str) -> queue.Queue | None:
        with self._lock:
            if job_id not in self._subscribers:
                return None
            q: queue.Queue = queue.Queue()
            self._subscribers[job_id].append(q)
            return q

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id)
            if subs and q in subs:
                subs.remove(q)

    def cancel(self, job_id: str) -> bool:
        proc = self._procs.get(job_id)
        if proc is None or proc.poll() is not None:
            return False
        job = self.get(job_id)
        if job is not None:
            job.cancelled = True
        proc.terminate()
        return True

    def _publish(self, job_id: str, event: str, data: dict) -> None:
        with self._lock:
            subs = list(self._subscribers.get(job_id, ()))
        for q in subs:
            q.put((event, data))

    def _run(self, job: Job) -> None:
        parser = progress_mod.PARSERS.get(job.stage)
        # Force the child's own stdout to UTF-8 regardless of the Windows
        # console's default codepage, so log lines with em-dashes etc.
        # render correctly in the browser instead of as mangled bytes.
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen(
            job.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            cwd=str(cfg.ROOT), env=env)
        self._procs[job.id] = proc
        self._publish(job.id, "status", {"status": "running", "returncode": None})
        try:
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                job.log_lines.append(line)
                self._publish(job.id, "log", {"line": line, "ts": time.time()})
                if parser is not None:
                    parser(job, line)
                    self._publish(job.id, "progress", job.progress)
        finally:
            rc = proc.wait()
            job.returncode = rc
            job.ended_at = time.time()
            job.status = "cancelled" if job.cancelled else (
                "done" if rc == 0 else "failed")
            self._publish(job.id, "status",
                         {"status": job.status, "returncode": rc})
            with self._lock:
                if self.current is not None and self.current.id == job.id:
                    self.current = None
                self._history[job.id] = job
                self._history_order.append(job.id)
                while len(self._history_order) > MAX_HISTORY:
                    old = self._history_order.pop(0)
                    self._history.pop(old, None)
                self._procs.pop(job.id, None)
                self._subscribers.pop(job.id, None)


manager = JobManager()
