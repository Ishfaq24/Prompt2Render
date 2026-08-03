"""Project list, creation, status, and environment-doctor endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import cfg, doctor, project
from .status import project_status
from .templating import templates

router = APIRouter()


class NewProject(BaseModel):
    slug: str
    title: str | None = None


def _list_projects() -> list[dict]:
    out = []
    if not cfg.PROJECTS.exists():
        return out
    for d in sorted(cfg.PROJECTS.iterdir()):
        script_md = d / "script.md"
        if not d.is_dir() or not script_md.exists():
            continue
        try:
            script = project.parse_script(script_md)
        except SystemExit:
            continue
        out.append({"slug": d.name, **project_status(d, script)})
    return out


@router.get("/", response_class=HTMLResponse)
def projects_page(request: Request):
    return templates.TemplateResponse(
        request, "projects.html", {"projects": _list_projects()})


@router.get("/api/projects")
def api_list_projects():
    return {"projects": _list_projects()}


@router.post("/api/projects")
def api_create_project(body: NewProject):
    if not body.slug or "/" in body.slug or "\\" in body.slug:
        raise HTTPException(400, "invalid slug")
    try:
        d = project.new_project(body.slug, body.title)
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return {"slug": d.name}


@router.get("/api/doctor")
def api_doctor():
    r = doctor.Report()
    doctor._check_ffmpeg(r)
    doctor._check_render(r)
    doctor._check_voice(r)
    doctor._check_align(r)
    doctor._check_scenes(r)
    doctor._check_optional(r)
    doctor._check_disk(r)
    return {
        "rows": [{"status": s, "name": n, "detail": d} for s, n, d in r.rows],
        "failed": r.failed,
    }
