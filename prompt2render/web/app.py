"""Prompt2Render local web dashboard application.

Provides a fast, local inspection dashboard for projects, generated video previews,
audio mastering verification, and QC gate reports.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from prompt2render import cfg, project
from prompt2render.web import library

STATIC_DIR = Path(__file__).resolve().parent / "static"
_TERMINAL_STATUSES = ("completed", "failed", "cancelled")

app = FastAPI(
    title="Prompt2Render Studio",
    description="Local studio dashboard for mathematical explainer video synthesis",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class StudioJob:
    def __init__(self, job_id: str, command: list[str], description: str,
                 meta: dict[str, Any] | None = None):
        self.job_id = job_id
        self.command = command
        self.description = description
        self.meta: dict[str, Any] = meta or {}
        self.status = "queued"
        self.exit_code: int | None = None
        self.logs: list[str] = []
        self.listeners: list[tuple[asyncio.Queue, asyncio.AbstractEventLoop | None]] = []
        self.created_at = time.time()
        self.started_at: float | None = None
        self.completed_at: float | None = None
        self.proc: subprocess.Popen | None = None
        self.cancel_requested = False

    def to_dict(self) -> dict[str, Any]:
        end = self.completed_at or time.time()
        return {
            "job_id": self.job_id,
            "description": self.description,
            "status": self.status,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_s": round(end - self.started_at, 1) if self.started_at else 0.0,
            "command": " ".join(_display_arg(c) for c in self.command),
            **self.meta,
        }


def _display_arg(arg: str) -> str:
    """Render a command argument for display (python path shortened, quoted if spaced)."""
    if arg == sys.executable:
        return "python"
    return f'"{arg}"' if " " in arg else arg


class StudioJobManager:
    def __init__(self):
        self.jobs: dict[str, StudioJob] = {}
        self.lock = threading.Lock()

    def create_job(self, command: list[str], description: str,
                   meta: dict[str, Any] | None = None) -> StudioJob:
        job_id = str(uuid.uuid4())[:8]
        job = StudioJob(job_id, command, description, meta)
        with self.lock:
            self.jobs[job_id] = job
        thread = threading.Thread(target=self._run_job, args=(job,), daemon=True)
        thread.start()
        return job

    def running_for_slug(self, slug: str) -> StudioJob | None:
        with self.lock:
            for job in self.jobs.values():
                if job.meta.get("slug") == slug and job.status in ("queued", "running"):
                    return job
        return None

    def cancel(self, job: StudioJob) -> bool:
        """Terminate a running job and its whole process tree."""
        proc = job.proc
        if job.status not in ("queued", "running") or proc is None:
            return False
        job.cancel_requested = True
        try:
            if sys.platform == "win32":
                # Manim/ffmpeg children would otherwise survive a plain terminate().
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=15)
            else:
                proc.terminate()
        except Exception:
            try:
                proc.kill()
            except Exception:
                return False
        return True

    def _run_job(self, job: StudioJob):
        job.status = "running"
        job.started_at = time.time()
        self._broadcast(job, f"[START] {job.description}\n")
        # Unbuffered + UTF-8 so logs stream line-by-line and non-ASCII output
        # (em dashes, Devanagari, Nastaliq) never crashes the reader thread.
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            proc = subprocess.Popen(
                job.command,
                cwd=str(cfg.ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            job.proc = proc
            for line in iter(proc.stdout.readline, ""):
                job.logs.append(line)
                self._broadcast(job, line)
            proc.stdout.close()
            job.exit_code = proc.wait()
            if job.cancel_requested:
                job.status = "cancelled"
            else:
                job.status = "completed" if job.exit_code == 0 else "failed"
                if job.status == "completed" and job.meta.get("slug"):
                    try:
                        pdir = cfg.PROJECTS / str(job.meta["slug"])
                        vpath = _resolve_project_video(pdir)
                        if vpath:
                            exported = library.export_project_video(
                                pdir, vpath, title=job.meta.get("topic") or None
                            )
                            if exported:
                                msg = f"[LIBRARY] Saved final video to Final Results/{exported['filename']}\n"
                                job.logs.append(msg)
                                self._broadcast(job, msg)
                    except Exception:
                        pass
        except Exception as exc:
            job.logs.append(f"\n[ERROR] Execution failed: {exc}\n")
            self._broadcast(job, f"\n[ERROR] {exc}\n")
            job.status = "failed"
            job.exit_code = -1
        finally:
            job.completed_at = time.time()
            self._broadcast(job, f"[DONE] Status: {job.status} (exit code: {job.exit_code})\n")

    def _broadcast(self, job: StudioJob, text: str):
        # Called from the worker thread: asyncio.Queue is not thread-safe, so
        # hand each line to the listener's own event loop.
        for q, loop in list(job.listeners):
            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, text)
                else:
                    q.put_nowait(text)
            except Exception:
                pass


job_manager = StudioJobManager()


def _resolve_project_video(proj_dir: Path) -> Path | None:
    """Locate the finished video for *proj_dir* (`out/final.mp4` or renamed `.mp4` in `out/`)."""
    out_dir = proj_dir / "out"
    if not out_dir.is_dir():
        return None
    primary = out_dir / "final.mp4"
    if primary.is_file() and primary.stat().st_size > 1024:
        return primary
    candidates = [
        p for p in out_dir.glob("*.mp4")
        if p.is_file() and p.stat().st_size > 1024 and "copy" not in p.stem.lower()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _get_project_summary(slug: str) -> dict[str, Any] | None:
    """Return summary dictionary for a single project directory."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        return None

    proj_dir = cfg.PROJECTS / clean_slug
    if not proj_dir.is_dir():
        return None

    script_path = proj_dir / "script.md"
    title = clean_slug.replace("-", " ").title()
    topic = ""
    sections_count = 0
    if script_path.is_file():
        try:
            s = project.parse_script(script_path)
            title = s.meta.get("title", title)
            topic = s.meta.get("topic", "")
            sections_count = len(s.sections)
        except (Exception, SystemExit):
            pass

    # Pipeline stage checkpoints
    has_audio = (proj_dir / "build" / "master.wav").exists() or (proj_dir / "build" / "master.m4a").exists()
    align_count = len(list((proj_dir / "build" / "align").glob("*.json"))) if (proj_dir / "build" / "align").is_dir() else 0
    scenes_count = len(list((proj_dir / "build" / "scenes").glob("scene_*.py"))) if (proj_dir / "build" / "scenes").is_dir() else 0
    
    final_video = _resolve_project_video(proj_dir)
    has_video = final_video is not None
    video_size_mb = round(final_video.stat().st_size / (1024 * 1024), 2) if final_video else 0.0

    qc_path = proj_dir / "out" / "qc.json"
    qc_data = None
    qc_status = "untested"
    if qc_path.is_file():
        try:
            qc_data = json.loads(qc_path.read_text(encoding="utf-8"))
            gates = qc_data.get("gates", [])
            if any(g.get("status") == "fail" for g in gates):
                qc_status = "failed"
            elif any(g.get("status") == "warn" for g in gates):
                qc_status = "warning"
            elif gates:
                qc_status = "passed"
        except Exception:
            pass

    hitl_file = proj_dir / "hitl_feedback.json"
    hitl_rejects = 0
    if hitl_file.is_file():
        try:
            hdata = json.loads(hitl_file.read_text(encoding="utf-8"))
            hitl_rejects = sum(1 for v in hdata.values() if isinstance(v, dict) and v.get("status") == "reject")
        except Exception:
            pass

    # Multilingual metadata
    lang = "en"
    script = "Latn"
    spec_file = proj_dir / "multilingual_spec.json"
    if spec_file.is_file():
        try:
            sdata = json.loads(spec_file.read_text(encoding="utf-8"))
            lang = sdata.get("target_language", lang)
            script = sdata.get("target_script", script)
        except Exception:
            pass
    elif script_path.is_file():
        try:
            s = project.parse_script(script_path)
            lang = s.meta.get("language", lang)
            script = s.meta.get("script", script)
        except (Exception, SystemExit):
            pass

    from prompt2render.multilingual import FontManager, LanguageRegistry
    is_rtl = False
    font_name = "Segoe UI"
    try:
        is_rtl = LanguageRegistry.is_rtl(lang, script)
        font_name = FontManager.resolve_best_font(lang, script)
    except Exception:
        pass

    return {
        "slug": clean_slug,
        "title": title,
        "topic": topic,
        "language": lang,
        "script": script,
        "is_rtl": is_rtl,
        "font": font_name,
        "sections_count": sections_count,
        "has_audio": has_audio,
        "align_count": align_count,
        "scenes_count": scenes_count,
        "has_video": has_video,
        "video_size_mb": video_size_mb,
        "qc_status": qc_status,
        "qc_data": qc_data,
        "hitl_rejects": hitl_rejects,
    }


def _get_project_sections(slug: str) -> list[dict[str, Any]]:
    """Return parsed sections with rendered status and HITL feedback."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        return []

    proj_dir = cfg.PROJECTS / clean_slug
    script_path = proj_dir / "script.md"
    if not script_path.is_file():
        return []

    try:
        s = project.parse_script(script_path)
    except (Exception, SystemExit):
        return []

    hitl_file = proj_dir / "hitl_feedback.json"
    hitl_data = {}
    if hitl_file.is_file():
        try:
            hitl_data = json.loads(hitl_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    out = []
    for sec in s.sections:
        stem = sec.stem
        sec_mp4 = proj_dir / "sections" / f"{stem}.mp4"
        has_clip = sec_mp4.is_file() and sec_mp4.stat().st_size > 0
        hitl_info = hitl_data.get(stem, {})
        out.append({
            "index": sec.index,
            "stem": stem,
            "title": sec.title,
            "anim": sec.anim,
            "narration": sec.narration,
            "has_clip": has_clip,
            "hitl_status": hitl_info.get("status", "none"),
            "hitl_reason": hitl_info.get("reason", ""),
        })
    return out


@app.get("/api/projects")
def api_list_projects() -> list[dict[str, Any]]:
    """List all projects found in projects/ directory with stage status."""
    if not cfg.PROJECTS.is_dir():
        return []

    summaries = []
    for item in sorted(cfg.PROJECTS.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            summary = _get_project_summary(item.name)
            if summary:
                summaries.append(summary)
    return summaries


@app.get("/api/projects/{slug}")
def api_get_project(slug: str) -> dict[str, Any]:
    """Get detailed project state and QC report."""
    summary = _get_project_summary(slug)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return summary


@app.get("/api/projects/{slug}/sections")
def api_get_project_sections(slug: str) -> list[dict[str, Any]]:
    """Get sections list with HITL review state for a project."""
    sections = _get_project_sections(slug)
    if not sections and not (cfg.PROJECTS / slug).is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return sections


@app.post("/api/projects/{slug}/hitl")
def api_submit_hitl_feedback(slug: str, payload: dict[str, Any]):
    """Record human-in-the-loop repair feedback or acceptance into hitl_feedback.json."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    stem = str(payload.get("stem", "")).strip()
    status = str(payload.get("status", "reject")).strip().lower()
    reason = str(payload.get("reason", "")).strip()

    if not stem:
        raise HTTPException(status_code=400, detail="stem is required")
    if status not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="status must be 'accept' or 'reject'")

    proj_dir = cfg.PROJECTS / clean_slug
    if not proj_dir.is_dir():
        raise HTTPException(status_code=404, detail="Project not found")

    hitl_file = proj_dir / "hitl_feedback.json"
    hitl_data = {}
    if hitl_file.is_file():
        try:
            hitl_data = json.loads(hitl_file.read_text(encoding="utf-8"))
        except Exception:
            hitl_data = {}

    if status == "reject" and not reason:
        reason = "Human reviewer requested repair."

    hitl_data[stem] = {"status": status}
    if status == "reject":
        hitl_data[stem]["reason"] = reason

    hitl_file.write_text(json.dumps(hitl_data, indent=2), encoding="utf-8")
    return {"ok": True, "stem": stem, "feedback": hitl_data[stem]}


@app.delete("/api/projects/{slug}/hitl/{stem}")
def api_clear_hitl_feedback(slug: str, stem: str):
    """Remove a section's entry from hitl_feedback.json."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    proj_dir = cfg.PROJECTS / clean_slug
    hitl_file = proj_dir / "hitl_feedback.json"
    if not hitl_file.is_file():
        return {"ok": True, "cleared": False}

    try:
        hitl_data = json.loads(hitl_file.read_text(encoding="utf-8"))
    except Exception:
        hitl_data = {}

    if stem in hitl_data:
        del hitl_data[stem]
        if hitl_data:
            hitl_file.write_text(json.dumps(hitl_data, indent=2), encoding="utf-8")
        else:
            hitl_file.unlink(missing_ok=True)
        return {"ok": True, "cleared": True}
    return {"ok": True, "cleared": False}


@app.get("/projects/{slug}/sections/{stem}/clip")
def get_section_clip(slug: str, stem: str):
    """Stream section MP4 clip."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    clean_stem = "".join(c for c in stem if c.isalnum())
    sec_mp4 = cfg.PROJECTS / clean_slug / "sections" / f"{clean_stem}.mp4"
    if sec_mp4.is_file():
        return FileResponse(str(sec_mp4), media_type="video/mp4")

    from prompt2render.visuals import latest_manim_clip
    cand = latest_manim_clip(cfg.PROJECTS / clean_slug, clean_stem)
    if cand and cand.is_file():
        return FileResponse(str(cand), media_type="video/mp4")

    raise HTTPException(status_code=404, detail=f"No clip found for section {stem}")


@app.get("/projects/{slug}/video")
def get_project_video(slug: str):
    """Stream final master video."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    video_path = _resolve_project_video(cfg.PROJECTS / clean_slug)
    if not video_path:
        raise HTTPException(status_code=404, detail="No final.mp4 generated for this project")
    return FileResponse(str(video_path), media_type="video/mp4")


@app.get("/projects/{slug}/audio")
def get_project_audio(slug: str):
    """Stream mastered project audio."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    for cand in ("build/master.m4a", "build/master.wav"):
        audio_path = cfg.PROJECTS / clean_slug / cand
        if audio_path.is_file():
            mime = "audio/mp4" if cand.endswith(".m4a") else "audio/wav"
            return FileResponse(str(audio_path), media_type=mime)

    raise HTTPException(status_code=404, detail="No master audio found")


@app.get("/api/jobs/{job_id}/stream")
async def api_stream_job(job_id: str):
    """Server-Sent Events stream for real-time process logs."""
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # Cursor-based tailing of job.logs: no lines are lost or duplicated
        # when a client (re)attaches mid-run, and no cross-thread queue access.
        cursor = 0
        idle = 0.0
        while True:
            logs = job.logs
            while cursor < len(logs):
                yield f"data: {json.dumps({'text': logs[cursor], 'status': job.status})}\n\n"
                cursor += 1
                idle = 0.0
            if job.status in _TERMINAL_STATUSES and cursor >= len(job.logs):
                yield f"data: {json.dumps({'text': '', 'status': job.status, 'exit_code': job.exit_code, 'done': True})}\n\n"
                return
            await asyncio.sleep(0.2)
            idle += 0.2
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/projects/{slug}/build")
def api_trigger_project_build(slug: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Trigger background build/repair pipeline with real-time SSE streaming."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    payload = payload or {}
    mode = str(payload.get("mode", "build")).strip()
    use_manim = bool(payload.get("manim", True))
    use_harness = bool(payload.get("harness", True))
    section = payload.get("section")

    allowed_modes = {"build", "auto", "repair", "voice", "stills", "encode", "finish", "check"}
    if mode not in allowed_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of {allowed_modes}")

    cmd = [sys.executable, "prompt2render.py", mode, clean_slug]
    if use_manim and mode in ("build", "auto", "repair"):
        cmd.append("--manim")
    if use_harness and mode in ("build", "auto", "repair"):
        cmd.append("--harness")
    if section is not None:
        cmd.extend(["--section", str(section)])

    job = job_manager.create_job(cmd, f"Running 'prompt2render {mode}' on {clean_slug}")
    return {"ok": True, "job_id": job.job_id, "command": cmd}


@app.get("/api/projects/{slug}/sections/{stem}/code")
def api_get_section_code(slug: str, stem: str) -> dict[str, Any]:
    """Retrieve scene drawing code for in-browser editing."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    proj_dir = cfg.PROJECTS / clean_slug
    clean_stem = "".join(c for c in stem if c.isalnum())
    cand1 = proj_dir / "build" / "scenes" / f"scene_{clean_stem}.py"
    cand2 = proj_dir / "scenes" / f"scene_{clean_stem}.py"

    target_file = cand1 if cand1.is_file() else (cand2 if cand2.is_file() else None)
    if not target_file:
        raise HTTPException(status_code=404, detail=f"No scene code found for section {stem}")

    return {
        "slug": clean_slug,
        "stem": clean_stem,
        "path": str(target_file.relative_to(cfg.ROOT)),
        "code": target_file.read_text(encoding="utf-8"),
    }


@app.put("/api/projects/{slug}/sections/{stem}/code")
def api_save_section_code(slug: str, stem: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Save updated scene drawing code from in-browser editor."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    code = payload.get("code", "")
    if not code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    clean_stem = "".join(c for c in stem if c.isalnum())
    proj_dir = cfg.PROJECTS / clean_slug
    target_file = proj_dir / "build" / "scenes" / f"scene_{clean_stem}.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(code, encoding="utf-8")

    return {"ok": True, "saved": True, "stem": clean_stem}


@app.get("/api/multilingual/languages")
def api_get_supported_languages() -> list[dict[str, Any]]:
    """Return registry of supported languages, scripts, fonts, and text direction."""
    from prompt2render.multilingual import LanguageRegistry
    return LanguageRegistry.list_languages()


@app.post("/api/multilingual/validate")
def api_validate_multilingual_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate language and script combination, font availability, and RTL status."""
    from prompt2render.multilingual import FontManager, LanguageRegistry
    lang = payload.get("language", "en")
    script = payload.get("script")

    try:
        lspec = LanguageRegistry.get_language(lang)
        sspec = lspec.get_script(script)
        best_font = FontManager.resolve_best_font(lang, script)
        return {
            "valid": True,
            "language": lspec.name,
            "script": sspec.name,
            "direction": sspec.direction,
            "font": best_font,
            "font_installed": FontManager.verify_font_availability(best_font),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/multilingual/generate")
def api_generate_multilingual(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate multilingual educational scenes and specification."""
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    target_lang = payload.get("target_language", "en").strip().lower()
    target_script = payload.get("target_script")
    input_lang = payload.get("input_language")
    slug = payload.get("slug")
    duration = float(payload.get("duration_minutes", 2.0))
    enable_narr = bool(payload.get("enable_narration", True))
    enable_sub = bool(payload.get("enable_subtitles", True))

    from prompt2render.multilingual import MultilingualPipeline
    try:
        result = MultilingualPipeline.execute_pipeline(
            prompt=prompt,
            target_lang=target_lang,
            target_script=target_script,
            input_lang=input_lang,
            slug=slug,
            duration_minutes=duration,
            enable_narration=enable_narr,
            enable_subtitles=enable_sub,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Multilingual generation failed: {exc}")


# --------------------------------------------------------------- studio ---
#
# Endpoints behind the redesigned Studio front-end (static/index.html):
#   * Create  -> type a topic, run `build` (existing project) or the
#                end-to-end harness (`auto ... --harness`), watch live logs.
#   * Library -> browse/play the curated videos in `Final Results/`.

_project_title_cache: dict[str, tuple[float, str]] = {}


def _light_project(proj_dir: Path) -> dict[str, Any]:
    """Cheap per-project summary for the Create view's topic resolver."""
    slug = proj_dir.name
    script_path = proj_dir / "script.md"
    has_script = script_path.is_file()
    title = slug.replace("-", " ").title()
    if has_script:
        mtime = script_path.stat().st_mtime
        cached = _project_title_cache.get(slug)
        if cached and cached[0] == mtime:
            title = cached[1]
        else:
            try:
                title = str(project.parse_script(script_path).meta.get("title") or title)
            except (Exception, SystemExit):
                pass
            _project_title_cache[slug] = (mtime, title)

    final_video = _resolve_project_video(proj_dir)
    has_video = final_video is not None
    return {
        "slug": slug,
        "title": title,
        "has_script": has_script,
        "has_video": has_video,
        "video_url": f"/projects/{slug}/video" if has_video else None,
        "video_size_mb": round(final_video.stat().st_size / (1024 * 1024), 1) if final_video else 0.0,
        "updated": int(final_video.stat().st_mtime) if final_video else None,
    }


def _match_existing_project(query_slug: str) -> str | None:
    """Resolve a topic slug like `binary-search` to an existing project like `binary-search-visualized`."""
    if not cfg.PROJECTS.is_dir():
        return None
    exact = cfg.PROJECTS / query_slug
    if (exact / "script.md").is_file():
        return query_slug
    tokens = [t for t in query_slug.split("-") if t]
    best_slug: str | None = None
    best_score = 0
    for item in sorted(cfg.PROJECTS.iterdir()):
        if not item.is_dir() or item.name.startswith(".") or not (item / "script.md").is_file():
            continue
        name = item.name.lower()
        score = 0
        if name.startswith(query_slug):
            score = 80
        elif tokens and all(t in name for t in tokens):
            score = 40
        if score > best_score:
            best_score = score
            best_slug = item.name
    return best_slug


@app.get("/api/studio/projects")
def api_studio_projects() -> list[dict[str, Any]]:
    """Lightweight project index (slug, title, script/video presence)."""
    if not cfg.PROJECTS.is_dir():
        return []
    out = []
    for item in sorted(cfg.PROJECTS.iterdir()):
        if not item.is_dir() or item.name.startswith("."):
            continue
        try:
            cfg.validate_slug(item.name, exit_on_error=False)
        except (ValueError, SystemExit):
            continue
        out.append(_light_project(item))
    return out


@app.post("/api/studio/run")
def api_studio_run(payload: dict[str, Any]) -> dict[str, Any]:
    """Start a Studio run.

    ``mode="build"``   -> ``prompt2render build <slug>`` on an existing project.
    ``mode="harness"`` -> ``prompt2render auto <slug> --harness`` end to end
                          (outline -> draft -> voice -> scenes -> QC + repair).
    """
    topic = str(payload.get("topic", "")).strip()
    mode = str(payload.get("mode", "build")).strip().lower()
    if mode not in ("build", "harness"):
        raise HTTPException(status_code=400, detail="mode must be 'build' or 'harness'")
    if not topic and not payload.get("slug"):
        raise HTTPException(status_code=400, detail="Please type a topic first.")

    raw_slug = str(payload.get("slug") or cfg.slugify(topic))
    try:
        slug = cfg.validate_slug(raw_slug, exit_on_error=False)
    except (ValueError, SystemExit) as exc:
        raise HTTPException(status_code=400, detail=str(exc).replace("[prompt2render] ", ""))

    use_manim = bool(payload.get("manim", True))
    strict = bool(payload.get("strict", mode == "harness"))
    dialogue = bool(payload.get("dialogue", False))
    language = str(payload.get("language") or "en").strip().lower()
    proj_dir = cfg.PROJECTS / slug

    running = job_manager.running_for_slug(slug)
    if running:
        raise HTTPException(
            status_code=409,
            detail=f"A run for '{slug}' is already in progress (job {running.job_id}).",
        )

    cmd = [sys.executable, "prompt2render.py"]
    if mode == "build":
        if not (proj_dir / "script.md").is_file():
            matched = _match_existing_project(slug)
            if matched:
                slug = matched
                proj_dir = cfg.PROJECTS / slug
        if not (proj_dir / "script.md").is_file():
            raise HTTPException(
                status_code=404,
                detail=(f"No existing project named '{slug}'. "
                        "Switch to Harness to create it end to end."),
            )
        cmd += ["build", slug]
        description = f"Building existing project '{slug}'"
    else:
        cmd += ["auto", slug, "--harness"]
        if topic and not proj_dir.is_dir():
            cmd += ["--title", topic[:1].upper() + topic[1:]]
        if dialogue:
            cmd.append("--dialogue")
        if language and language != "en":
            cmd += ["--lang", language]
        minutes = payload.get("minutes")
        if minutes not in (None, ""):
            try:
                m = float(minutes)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="minutes must be a number")
            if not 0.5 <= m <= 30:
                raise HTTPException(status_code=400, detail="minutes must be between 0.5 and 30")
            cmd += ["--minutes", f"{m:g}"]
        description = f"Harness end-to-end run for '{slug}'"

    if use_manim:
        cmd.append("--manim")
    if strict:
        cmd.append("--strict")

    job = job_manager.create_job(
        cmd, description,
        meta={"slug": slug, "mode": mode, "topic": topic or slug},
    )
    return {"ok": True, **job.to_dict()}


@app.get("/api/jobs")
def api_list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """Most recent Studio jobs first."""
    with job_manager.lock:
        jobs = sorted(job_manager.jobs.values(), key=lambda j: j.created_at, reverse=True)
    return [j.to_dict() for j in jobs[: max(1, min(limit, 100))]]


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str) -> dict[str, Any]:
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str) -> dict[str, Any]:
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job_manager.cancel(job):
        raise HTTPException(status_code=409, detail=f"Job is not running (status: {job.status})")
    return {"ok": True, "job_id": job_id}


# -------------------------------------------------------------- library ---

@app.post("/api/projects/{slug}/publish-library")
def api_publish_project_to_library(slug: str) -> dict[str, Any]:
    """Copy a project's finished MP4 into `Final Results/` so it appears in the Library."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    proj_dir = cfg.PROJECTS / clean_slug
    if not proj_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{clean_slug}' not found")

    video_path = _resolve_project_video(proj_dir)
    if not video_path:
        raise HTTPException(status_code=404, detail=f"No finished video found for '{clean_slug}'")

    summary = _light_project(proj_dir)
    exported = library.export_project_video(proj_dir, video_path, title=summary.get("title"))
    if not exported:
        raise HTTPException(status_code=500, detail="Failed to export video to library")
    return {"ok": True, "item": exported}


@app.get("/api/library")
def api_library() -> dict[str, Any]:
    """Every finished video in `Final Results/` with title, size and duration."""
    items = library.list_videos()
    return {
        "directory": library.LIBRARY_DIR.name,
        "count": len(items),
        "total_size_mb": round(sum(i["size_mb"] for i in items), 1),
        "total_duration_s": round(sum(i["duration_s"] or 0 for i in items), 1),
        "items": items,
    }


@app.get("/library/{filename}/video")
def get_library_video(filename: str, download: bool = False):
    """Stream (HTTP range) or download a library video."""
    path = library.resolve_video(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found in library")
    media = "video/webm" if path.suffix.lower() == ".webm" else "video/mp4"
    if download:
        return FileResponse(str(path), media_type=media, filename=path.name)
    return FileResponse(str(path), media_type=media)


@app.get("/library/{filename}/thumbnail")
def get_library_thumbnail(filename: str):
    """Cached JPEG poster frame for a library video."""
    path = library.resolve_video(filename)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found in library")
    thumb = library.thumbnail_path(path)
    if not thumb:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable (is ffmpeg installed?)")
    return FileResponse(str(thumb), media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/", include_in_schema=False)
def studio_index():
    """Serve the Studio single-page front-end (Create + Library)."""
    return FileResponse(str(STATIC_DIR / "index.html"), media_type="text/html",
                        headers={"Cache-Control": "no-cache"})


@app.get("/workbench", response_class=HTMLResponse)
def dashboard_html() -> str:
    """Render the per-project review workbench (HITL, scene code, QC)."""
    projects_list = api_list_projects()
    cards_html = ""
    for p in projects_list:
        slug = p["slug"]
        status_badge = (
            '<span class="badge badge-success">SHIPPABLE</span>'
            if p["qc_status"] in ("passed", "warning") and p["has_video"]
            else ('<span class="badge badge-warning">IN PROGRESS</span>' if p["has_audio"] else '<span class="badge badge-muted">SCAFFOLDED</span>')
        )
        if p["hitl_rejects"] > 0:
            status_badge += f' <span class="badge badge-reject">REPAIR NEEDED ({p["hitl_rejects"]})</span>'

        video_btn = (
            f'<a href="/projects/{slug}/video" target="_blank" class="btn btn-primary">Play Final Video ({p["video_size_mb"]} MB)</a>'
            if p["has_video"]
            else '<span class="btn btn-disabled">No Video Yet</span>'
        )
        
        # Build sections review table
        sections = _get_project_sections(slug)
        sec_rows = ""
        for s in sections:
            stem = s["stem"]
            st_badge = '<span class="badge badge-muted">Unreviewed</span>'
            if s["hitl_status"] == "reject":
                st_badge = '<span class="badge badge-reject">Rejected</span>'
            elif s["hitl_status"] == "accept":
                st_badge = '<span class="badge badge-success">Accepted</span>'

            clip_link = (
                f'<a href="/projects/{slug}/sections/{stem}/clip" target="_blank" class="sec-link">Clip MP4</a>'
                if s["has_clip"] else '<span class="dim">No Clip</span>'
            )

            sec_rows += f"""
            <tr id="sec-row-{slug}-{stem}">
                <td><strong>{s["index"]}</strong></td>
                <td>
                    <div class="sec-title">{s["title"]}</div>
                    <div class="sec-narr">{s["narration"][:100]}...</div>
                </td>
                <td>{clip_link}</td>
                <td id="sec-badge-{slug}-{stem}">{st_badge}</td>
                <td>
                    <div class="hitl-ctrls">
                        <button class="btn btn-sm btn-accept" onclick="sendHitl('{slug}', '{stem}', 'accept')">&#10003; Accept</button>
                        <input type="text" id="reason-{slug}-{stem}" placeholder="Repair instructions..." value="{s['hitl_reason']}" class="input-reason" />
                        <button class="btn btn-sm btn-reject" onclick="sendHitl('{slug}', '{stem}', 'reject')">&#8634; Reject</button>
                        <button class="btn btn-sm btn-secondary" onclick="openCodeEditor('{slug}', '{stem}')">&#9998; Code</button>
                    </div>
                </td>
            </tr>
            """

        sections_panel = f"""
        <div id="review-{slug}" class="review-panel" style="display:none;">
            <h4>Section Review & Human-in-the-Loop Feedback</h4>
            <table class="sec-table">
                <thead>
                    <tr>
                        <th width="40">#</th>
                        <th>Title & Narration</th>
                        <th width="90">Media</th>
                        <th width="100">Status</th>
                        <th width="420">Feedback & Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {sec_rows}
                </tbody>
            </table>
        </div>
        """ if sections else ""

        review_btn = (
            f'<button class="btn btn-secondary" onclick="toggleReview(\'{slug}\')">Review Sections ({len(sections)})</button>'
            if sections else ""
        )

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">{p["title"]}</h3>
                <div>{status_badge}</div>
            </div>
            <p class="card-slug"><code>{slug}</code> &bull; <span class="badge badge-lang">{p.get("language", "en").upper()}-{p.get("script", "Latn")} ({p.get("font", "Segoe UI")})</span> &bull; {p["sections_count"]} sections</p>
            <p class="card-topic">{p["topic"] or "Topic unassigned"}</p>
            <div class="pipeline-progress">
                <span class="step {'step-done' if p['sections_count'] else ''}">Script</span> &rarr;
                <span class="step {'step-done' if p['has_audio'] else ''}">Voice</span> &rarr;
                <span class="step {'step-done' if p['align_count'] else ''}">Align</span> &rarr;
                <span class="step {'step-done' if p['scenes_count'] else ''}">Scenes</span> &rarr;
                <span class="step {'step-done' if p['has_video'] else ''}">Final MP4</span>
            </div>
            <div class="card-actions">
                {video_btn}
                {review_btn}
                <button class="btn btn-primary" onclick="triggerBuild('{slug}', 'build')">&#9889; Build</button>
                <button class="btn btn-warning" onclick="triggerBuild('{slug}', 'auto')">&#8635; Auto Repair</button>
            </div>
            {sections_panel}
        </div>
        """

    if not cards_html:
        cards_html = "<p class='empty-text'>No projects found. Create one using <code>python prompt2render.py new &lt;slug&gt;</code></p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prompt2Render Studio &middot; Workbench</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
    <style>
        :root {{
            --bg: #F8FCFF;
            --card-bg: #FFFFFF;
            --border: #E3EEF8;
            --accent: #0EA5E9;
            --text: #0B2440;
            --dim: #64809E;
            --success: #10B981;
            --warning: #D97706;
            --reject: #E11D48;
        }}
        body {{
            margin: 0;
            padding: 2rem;
            background: radial-gradient(900px 520px at 12% -8%, rgba(125, 211, 252, .35), transparent 60%), var(--bg);
            color: var(--text);
            font-family: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .header {{
            max-width: 1100px;
            margin: 0 auto 2.5rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
        }}
        .header h1 {{ margin: 0 0 0.5rem; font-size: 1.8rem; font-weight: 800; color: var(--text); letter-spacing: -0.02em; }}
        .header p {{ margin: 0; color: var(--dim); }}
        .container {{ max-width: 1100px; margin: 0 auto; display: grid; grid-gap: 1.5rem; }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1.5rem;
            box-shadow: 0 1px 2px rgba(11, 36, 64, .04), 0 8px 24px -6px rgba(14, 116, 180, .09);
        }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
        .card-title {{ margin: 0; font-size: 1.25rem; font-weight: 700; color: var(--text); }}
        .card-slug {{ margin: 0 0 0.5rem; font-size: 0.85rem; color: var(--dim); }}
        .card-topic {{ margin: 0 0 1rem; font-size: 0.95rem; color: #234061; }}
        .badge {{
            font-size: 0.75rem;
            padding: 0.25rem 0.65rem;
            border-radius: 9999px;
            font-weight: 700;
        }}
        .badge-success {{ background: #E8FBF4; color: #047857; border: 1px solid #A7F3D0; }}
        .badge-warning {{ background: #FFF6E6; color: #B45309; border: 1px solid #FDE68A; }}
        .badge-reject {{ background: #FFEFF3; color: #BE123C; border: 1px solid #FECDD3; }}
        .badge-muted {{ background: #F0F8FF; color: #64809E; border: 1px solid var(--border); }}
        .pipeline-progress {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin: 1rem 0;
            font-size: 0.85rem;
            color: var(--dim);
        }}
        .step {{ padding: 0.25rem 0.6rem; border-radius: 8px; background: #F7FBFF; border: 1px solid var(--border); }}
        .step-done {{ background: #E0F2FE; color: #0369A1; border-color: #7DD3FC; font-weight: 600; }}
        .card-actions {{ margin-top: 1.2rem; display: flex; gap: 0.75rem; flex-wrap: wrap; }}
        .btn {{
            text-decoration: none;
            display: inline-block;
            padding: 0.55rem 1.05rem;
            border-radius: 10px;
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            border: none;
        }}
        .btn-primary {{ background: linear-gradient(180deg, #38BDF8, #0EA5E9 55%, #0284C7); color: white; box-shadow: 0 6px 16px -6px rgba(14, 165, 233, .55); }}
        .btn-primary:hover {{ background: #0284C7; }}
        .btn-secondary {{ background: #FFFFFF; color: #234061; border: 1px solid #D3E5F5; }}
        .btn-secondary:hover {{ background: #F0F8FF; border-color: #7DD3FC; color: #0369A1; }}
        .btn-warning {{ background: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; }}
        .btn-warning:hover {{ background: #BAE6FD; }}
        .btn-disabled {{ background: #F0F8FF; color: #94AAC2; cursor: not-allowed; border: 1px solid var(--border); }}
        .btn-sm {{ padding: 0.3rem 0.65rem; font-size: 0.8rem; border-radius: 8px; }}
        .btn-accept {{ background: #10B981; color: white; }}
        .btn-accept:hover {{ background: #059669; }}
        .btn-reject {{ background: #E11D48; color: white; }}
        .btn-reject:hover {{ background: #BE123C; }}
        .review-panel {{ margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border); }}
        .review-panel h4 {{ margin: 0 0 1rem; font-size: 1rem; color: var(--text); }}
        .sec-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        .sec-table th {{ text-align: left; padding: 0.5rem; color: var(--dim); border-bottom: 1px solid var(--border); }}
        .sec-table td {{ padding: 0.65rem 0.5rem; border-bottom: 1px solid #F0F8FF; vertical-align: middle; }}
        .sec-title {{ font-weight: 600; color: var(--text); margin-bottom: 0.2rem; }}
        .sec-narr {{ color: var(--dim); font-size: 0.78rem; }}
        .sec-link {{ color: #0284C7; text-decoration: none; font-weight: 600; }}
        .hitl-ctrls {{ display: flex; gap: 0.4rem; align-items: center; }}
        .badge-lang {{ background: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; }}
        .generator-card {{ background: #FFFFFF; border: 1px solid #D3E5F5; border-radius: 18px; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 1px 2px rgba(11, 36, 64, .04), 0 8px 24px -6px rgba(14, 116, 180, .1); }}
        .form-row {{ display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 1rem; margin-bottom: 1rem; align-items: end; }}
        .form-group {{ display: flex; flex-direction: column; gap: 0.35rem; }}
        .form-group label {{ font-size: 0.8rem; color: var(--dim); font-weight: 600; }}
        .form-control {{ background: #F7FBFF; border: 1px solid #D3E5F5; border-radius: 10px; color: var(--text); padding: 0.55rem 0.75rem; font-size: 0.875rem; font-family: inherit; }}
        .toggles-row {{ display: flex; gap: 1.5rem; align-items: center; margin-bottom: 1.2rem; font-size: 0.85rem; color: #234061; font-weight: 500; }}
        .preview-box {{ background: #F0F8FF; border: 1px dashed #BAE6FD; border-radius: 10px; padding: 0.75rem; font-size: 0.85rem; color: #0369A1; margin-bottom: 1rem; }}
        .input-reason {{ background: #F7FBFF; border: 1px solid #D3E5F5; border-radius: 6px; color: var(--text); padding: 0.3rem 0.55rem; font-size: 0.8rem; flex-grow: 1; }}
        .empty-text {{ color: var(--dim); text-align: center; padding: 3rem 0; }}
        .dim {{ color: #94AAC2; }}
        code {{ background: #F0F8FF; padding: 0.2rem 0.45rem; border-radius: 6px; color: #0369A1; font-family: "JetBrains Mono", monospace; }}
        .terminal-drawer {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 320px;
            background: #FFFFFF;
            border-top: 2px solid var(--accent);
            box-shadow: 0 -8px 30px rgba(14, 116, 180, 0.18);
            display: flex;
            flex-direction: column;
            z-index: 1000;
        }}
        .terminal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.6rem 1.2rem;
            background: #F0F8FF;
            border-bottom: 1px solid var(--border);
            font-size: 0.85rem;
            color: var(--text);
        }}
        .terminal-output {{
            flex-grow: 1;
            padding: 1rem 1.2rem;
            font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.82rem;
            line-height: 1.55;
            color: #234061;
            background: #FFFFFF;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .modal-backdrop {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(224, 242, 254, 0.6);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 2000;
        }}
        .modal-box {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: 0 24px 60px -12px rgba(14, 116, 180, .25);
            width: 800px;
            max-width: 90vw;
            max-height: 85vh;
            display: flex;
            flex-direction: column;
        }}
        .modal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
        }}
        .modal-body {{
            padding: 1.2rem 1.5rem;
            flex-grow: 1;
            overflow-y: auto;
        }}
        .code-editor-textarea {{
            width: 100%;
            height: 380px;
            box-sizing: border-box;
            background: #F7FBFF;
            color: var(--text);
            font-family: "JetBrains Mono", ui-monospace, monospace;
            font-size: 0.88rem;
            border: 1px solid #D3E5F5;
            border-radius: 10px;
            padding: 1rem;
            line-height: 1.55;
            resize: vertical;
        }}
        .modal-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 0.75rem;
            padding: 1rem 1.5rem;
            border-top: 1px solid var(--border);
        }}
    </style>
    <script>
        function toggleReview(slug) {{
            const p = document.getElementById('review-' + slug);
            p.style.display = p.style.display === 'none' ? 'block' : 'none';
        }}
        function updateScriptOptions() {{
            const lang = document.getElementById('target-lang').value;
            const scriptSel = document.getElementById('target-script');
            scriptSel.innerHTML = '';
            if (lang === 'hi') {{
                scriptSel.innerHTML = '<option value="Deva">Devanagari (Standard)</option>';
                document.getElementById('preview-text').innerText = 'रैखिक प्रतिगमन और न्यूरल नेटवर्क की कार्यप्रणाली';
            }} else if (lang === 'ur') {{
                scriptSel.innerHTML = '<option value="Arab">Urdu Nastaliq / Arabic (RTL)</option>';
                document.getElementById('preview-text').innerText = 'بائنری سرچ الگورتھم اور ڈیٹا ڈھانچے';
            }} else if (lang === 'ar') {{
                scriptSel.innerHTML = '<option value="Arab">Arabic (RTL)</option>';
                document.getElementById('preview-text').innerText = 'الانحدار الخطي وشبكات الأعصاب الاصطناعية';
            }} else if (lang === 'ks') {{
                scriptSel.innerHTML = '<option value="Arab">Perso-Arabic (RTL)</option><option value="Deva">Devanagari</option>';
                document.getElementById('preview-text').innerText = 'کٲشُر زَبانہِ مَنٛز الگورتھم / कॉशुर ज़बानि मंज़ एल्गोरिदम';
            }} else {{
                scriptSel.innerHTML = '<option value="Latn">Latin (Standard)</option>';
                document.getElementById('preview-text').innerText = 'Gradient Descent Optimization and Neural Networks';
            }}
        }}
        async function runMultilingualGen() {{
            const prompt = document.getElementById('gen-prompt').value.trim();
            if (!prompt) return alert('Please enter an educational topic or prompt.');
            const targetLang = document.getElementById('target-lang').value;
            const targetScript = document.getElementById('target-script').value;
            const btn = document.getElementById('gen-btn');
            btn.disabled = true;
            btn.innerText = 'Synthesizing Multilingual Video...';
            try {{
                const res = await fetch('/api/multilingual/generate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        prompt: prompt,
                        target_language: targetLang,
                        target_script: targetScript,
                        enable_narration: true,
                        enable_subtitles: true
                    }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Generation failed');
                alert('Multilingual video project created: ' + data.slug + ' (' + data.scenes.length + ' scenes)');
                window.location.reload();
            }} catch(err) {{
                alert('Generation error: ' + err.message);
            }} finally {{
                btn.disabled = false;
                btn.innerText = 'Generate Multilingual Video';
            }}
        }}
        async function sendHitl(slug, stem, status) {{
            const reasonInput = document.getElementById('reason-' + slug + '-' + stem);
            const reason = reasonInput ? reasonInput.value : '';
            try {{
                const res = await fetch('/api/projects/' + slug + '/hitl', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ stem: stem, status: status, reason: reason }})
                }});
                if (!res.ok) throw new Error('Failed to update HITL');
                const badgeCell = document.getElementById('sec-badge-' + slug + '-' + stem);
                if (status === 'accept') {{
                    badgeCell.innerHTML = '<span class="badge badge-success">Accepted</span>';
                }} else {{
                    badgeCell.innerHTML = '<span class="badge badge-reject">Rejected</span>';
                }}
            }} catch (e) {{
                alert('Error submitting feedback: ' + e.message);
            }}
        }}

        let activeEventSource = null;
        let currentEditingSlug = null;
        let currentEditingStem = null;

        async function triggerBuild(slug, mode) {{
            const term = document.getElementById('terminal-drawer');
            const termOut = document.getElementById('terminal-output');
            const jobStatus = document.getElementById('job-status');
            term.style.display = 'flex';
            termOut.innerText = 'Initializing ' + mode + ' pipeline for ' + slug + '...\\n';
            jobStatus.innerText = 'STARTING';
            jobStatus.className = 'badge badge-warning';

            try {{
                const res = await fetch('/api/projects/' + slug + '/build', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ mode: mode, manim: true, harness: true }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Build start failed');
                
                if (activeEventSource) activeEventSource.close();
                activeEventSource = new EventSource('/api/jobs/' + data.job_id + '/stream');
                activeEventSource.onmessage = function(e) {{
                    const msg = JSON.parse(e.data);
                    if (msg.text) {{
                        termOut.innerText += msg.text;
                        termOut.scrollTop = termOut.scrollHeight;
                    }}
                    if (msg.status === 'completed') {{
                        jobStatus.innerText = 'COMPLETED';
                        jobStatus.className = 'badge badge-success';
                    }} else if (msg.status === 'failed') {{
                        jobStatus.innerText = 'FAILED';
                        jobStatus.className = 'badge badge-reject';
                    }}
                    if (msg.done) {{
                        activeEventSource.close();
                        activeEventSource = null;
                    }}
                }};
            }} catch (err) {{
                termOut.innerText += '\\n[ERROR] ' + err.message + '\\n';
                jobStatus.innerText = 'ERROR';
                jobStatus.className = 'badge badge-reject';
            }}
        }}

        function closeTerminal() {{
            document.getElementById('terminal-drawer').style.display = 'none';
        }}

        async function openCodeEditor(slug, stem) {{
            currentEditingSlug = slug;
            currentEditingStem = stem;
            try {{
                const res = await fetch('/api/projects/' + slug + '/sections/' + stem + '/code');
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to load code');
                document.getElementById('modal-title').innerText = 'Edit Scene Code (' + slug + ' / Section ' + stem + ')';
                document.getElementById('code-editor-text').value = data.code;
                document.getElementById('code-modal').style.display = 'flex';
            }} catch (e) {{
                alert('Could not open code: ' + e.message);
            }}
        }}

        function closeCodeEditor() {{
            document.getElementById('code-modal').style.display = 'none';
        }}

        async function saveSectionCode() {{
            if (!currentEditingSlug || !currentEditingStem) return;
            const code = document.getElementById('code-editor-text').value;
            try {{
                const res = await fetch('/api/projects/' + currentEditingSlug + '/sections/' + currentEditingStem + '/code', {{
                    method: 'PUT',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ code: code }})
                }});
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Save failed');
                alert('Code saved successfully for Section ' + currentEditingStem);
            }} catch (e) {{
                alert('Save failed: ' + e.message);
            }}
        }}

        async function saveAndRerender() {{
            await saveSectionCode();
            closeCodeEditor();
            triggerBuild(currentEditingSlug, 'repair');
        }}
    </script>
</head>
<body>
    <div class="header">
        <p style="margin-bottom:0.75rem;"><a href="/" class="sec-link">&larr; Back to Studio</a></p>
        <h1>🎬 Prompt2Render Studio &mdash; Workbench</h1>
        <p>Industrial, frame-accurate multilingual educational video workbench</p>
    </div>
    <div class="container">
        <div class="generator-card">
            <h3 style="margin-top:0;margin-bottom:1rem;color:var(--text);">🌐 Generate Multilingual Educational Video</h3>
            <div class="form-row">
                <div class="form-group">
                    <label>Educational Topic / Prompt</label>
                    <input type="text" id="gen-prompt" class="form-control" placeholder="e.g. Explain linear regression with gradient descent" />
                </div>
                <div class="form-group">
                    <label>Target Language</label>
                    <select id="target-lang" class="form-control" onchange="updateScriptOptions()">
                        <option value="en">English (en)</option>
                        <option value="hi">Hindi (hi)</option>
                        <option value="ur">Urdu (ur)</option>
                        <option value="ar">Arabic (ar)</option>
                        <option value="ks">Kashmiri (ks)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Writing Script</label>
                    <select id="target-script" class="form-control">
                        <option value="Latn">Latin (Standard)</option>
                    </select>
                </div>
                <div class="form-group">
                    <button id="gen-btn" class="btn btn-primary" onclick="runMultilingualGen()" style="height:38px;">Generate Video</button>
                </div>
            </div>
            <div class="toggles-row">
                <label><input type="checkbox" id="chk-narr" checked /> Neural Audio Narration</label>
                <label><input type="checkbox" id="chk-subs" checked /> Frame-Synchronized Subtitles</label>
                <label><input type="checkbox" id="chk-audit" checked /> Closed-Loop Visual QA & Collision Repair</label>
            </div>
            <div class="preview-box">
                <strong>Language Script Preview:</strong> <span id="preview-text">Gradient Descent Optimization and Neural Networks</span>
            </div>
        </div>
        {cards_html}
    </div>

    <div id="terminal-drawer" class="terminal-drawer" style="display:none;">
        <div class="terminal-header">
            <div><strong>⚡ Live Build Terminal</strong> &bull; <span id="job-status" class="badge badge-warning">RUNNING</span></div>
            <button class="btn btn-sm btn-secondary" onclick="closeTerminal()">Close</button>
        </div>
        <div id="terminal-output" class="terminal-output"></div>
    </div>

    <div id="code-modal" class="modal-backdrop" style="display:none;">
        <div class="modal-box">
            <div class="modal-header">
                <h3 id="modal-title" style="margin:0;">Edit Scene Code</h3>
                <button class="btn btn-sm btn-secondary" onclick="closeCodeEditor()">✕</button>
            </div>
            <div class="modal-body">
                <textarea id="code-editor-text" class="code-editor-textarea" spellcheck="false"></textarea>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeCodeEditor()">Cancel</button>
                <button class="btn btn-primary" onclick="saveSectionCode()">Save Changes</button>
                <button class="btn btn-warning" onclick="saveAndRerender()">Save & Re-render</button>
            </div>
        </div>
    </div>
</body>
</html>"""

