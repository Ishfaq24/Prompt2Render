"""Pipeline stage execution: run a stage, run the whole build, stream its
live log + progress via SSE, snapshot a job, or cancel it.

Every stage is launched as its own `python fdx.py <stage> <slug> [flags]`
subprocess through `fdx.web.jobs.manager` -- see that module's docstring
for why (mainly: SystemExit safety, and it's what makes live log streaming
work with zero changes to the pipeline stage modules).
"""
from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from .. import cfg, project
from . import schemas
from .jobs import JobConflict, manager
from .status import project_status
from .templating import templates

router = APIRouter()

STAGES = ("voice", "align", "scenes", "stills", "plan", "encode", "finish", "check")


def _load(slug: str):
    proj = cfg.PROJECTS / slug
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    try:
        script = project.parse_script(proj / "script.md")
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return proj, script


def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _total_for(stage: str, proj: Path, script, opts) -> tuple[int, list[str]]:
    """Server-computed total + (for `check`) the section stems the
    caption-drift sub-progress note counts against -- never guessed from
    a running job's own stdout."""
    stems = [s.stem for s in script.sections]
    # A --section filter (scenes/stills) or --only (voice/align) narrows the
    # job to exactly one section -- the total must reflect that, or a
    # single-section run reports e.g. "1/5" (20%) instead of "1/1" (100%).
    only = getattr(opts, "only", None)
    section = getattr(opts, "section", None)
    if only or section is not None:
        return 1, []

    if stage == "scenes":
        missing = [s for s in stems
                  if not (proj / "build" / "scenes" / f"scene_{s}.py").exists()]
        return (len(missing) or len(stems)), []
    if stage == "encode":
        plan = _read_json(proj / "build" / "plan.json")
        return (len(plan["clips"]) if plan else 0), []
    if stage == "check":
        final_exists = (proj / "out" / "final.mp4").exists()
        return (12 if final_exists else 5), stems
    if stage in ("voice", "align", "finish", "stills", "plan"):
        return len(stems), []
    return 0, []


@router.get("/projects/{slug}/pipeline", response_class=HTMLResponse)
def pipeline_page(request: Request, slug: str):
    proj, script = _load(slug)
    return templates.TemplateResponse(
        request, "pipeline.html",
        {"slug": slug, "status": project_status(proj, script),
         "stages": STAGES,
         "current": manager.current.snapshot() if manager.current else None})


@router.post("/api/projects/{slug}/stages/{stage}/run")
def run_stage(slug: str, stage: str, body: dict | None = None):
    if stage not in STAGES:
        raise HTTPException(404, f"unknown stage '{stage}'")
    proj, script = _load(slug)
    opts = schemas.MODELS[stage](**(body or {}))
    args = schemas.ARG_BUILDERS[stage](opts)
    total, drift_total = _total_for(stage, proj, script, opts)
    try:
        job = manager.start(slug, stage, args, total=total, drift_total=drift_total)
    except JobConflict as e:
        raise HTTPException(409, str(e))
    return job.snapshot()


@router.post("/api/projects/{slug}/build")
def run_build(slug: str, body: dict | None = None):
    _load(slug)  # 404s cleanly if the project/script don't exist
    opts = schemas.BuildOpts(**(body or {}))
    args = schemas.build_args(opts)
    try:
        job = manager.start(slug, "build", args, total=0)
    except JobConflict as e:
        raise HTTPException(409, str(e))
    return job.snapshot()


@router.get("/api/projects/{slug}/jobs/{job_id}")
def job_snapshot(slug: str, job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job.snapshot()


@router.post("/api/projects/{slug}/jobs/{job_id}/cancel")
def cancel_job(slug: str, job_id: str):
    if not manager.cancel(job_id):
        raise HTTPException(409, "job is not running")
    return {"cancelled": True}


@router.get("/api/projects/{slug}/jobs/{job_id}/stream")
async def stream_job(slug: str, job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")

    async def gen():
        # Replay everything collected so far -- a client opening this
        # mid-run (exactly today's manual-polling scenario) sees full
        # history immediately, not just whatever happens next.
        for line in job.log_lines:
            yield f"event: log\ndata: {json.dumps({'line': line})}\n\n"
        yield f"event: progress\ndata: {json.dumps(job.progress)}\n\n"

        if job.status != "running":
            yield ("event: status\ndata: " +
                  json.dumps({"status": job.status, "returncode": job.returncode}) +
                  "\n\n")
            return

        q = manager.subscribe(job_id)
        if q is None:
            yield ("event: status\ndata: " +
                  json.dumps({"status": job.status, "returncode": job.returncode}) +
                  "\n\n")
            return
        try:
            while True:
                try:
                    event, data = await asyncio.to_thread(q.get, True, 15)
                except queue.Empty:
                    yield "event: heartbeat\ndata: {}\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                if event == "status":
                    break
        finally:
            manager.unsubscribe(job_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream")
