"""Script editor: read/write script.md through project.parse_script() /
scriptio.render_script_md(), plus the opt-in, never-auto-saving
'Draft with AI' endpoint.
"""
from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import cfg, project
from . import draft as draft_mod
from . import scriptio
from .templating import templates

router = APIRouter()


class SectionIn(BaseModel):
    index: int
    title: str = ""
    anim: str = ""
    narration: str = ""


class ScriptIn(BaseModel):
    meta: dict
    sections: list[SectionIn]


class DraftIn(BaseModel):
    meta: dict = {}
    sections: list[SectionIn] = []


def _proj(slug: str):
    proj = cfg.PROJECTS / slug
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    return proj


def _to_editor_shape(script) -> dict:
    return {
        "meta": script.meta,
        "sections": [{"index": s.index, "title": s.title,
                     "anim": s.anim, "narration": s.narration}
                    for s in script.sections],
    }


@router.get("/projects/{slug}/script", response_class=HTMLResponse)
def script_page(request: Request, slug: str):
    proj = _proj(slug)
    try:
        script = project.parse_script(proj / "script.md")
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return templates.TemplateResponse(
        request, "editor.html", {"slug": slug, "script": _to_editor_shape(script)})


@router.get("/api/projects/{slug}/script")
def get_script(slug: str):
    proj = _proj(slug)
    try:
        script = project.parse_script(proj / "script.md")
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return _to_editor_shape(script)


@router.put("/api/projects/{slug}/script")
def put_script(slug: str, body: ScriptIn):
    proj = _proj(slug)
    md_path = proj / "script.md"
    text = scriptio.render_script_md(
        body.meta, [s.model_dump() for s in body.sections])
    if md_path.exists():
        shutil.copyfile(md_path, md_path.with_suffix(".md.bak"))
    md_path.write_text(text, encoding="utf-8")
    # Round-trip through the real parser so the response reflects exactly
    # what the next load will see, and a bad save surfaces immediately
    # rather than silently writing something that won't reparse.
    try:
        script = project.parse_script(md_path)
    except SystemExit as e:
        raise HTTPException(400, f"saved, but failed to re-parse: {e}")
    return _to_editor_shape(script)


@router.post("/api/projects/{slug}/script/draft")
def draft_script(slug: str, body: DraftIn):
    _proj(slug)  # 404s cleanly if the project doesn't exist
    try:
        data = draft_mod.draft(
            body.meta.get("title", ""), body.meta.get("topic", ""),
            body.meta.get("audience", ""),
            [s.model_dump() for s in body.sections])
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:                          # noqa: BLE001
        raise HTTPException(502, f"draft request failed: {e}")
    return data
