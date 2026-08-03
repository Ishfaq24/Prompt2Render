"""Final review: the QC gate table (thin passthrough of out/qc.json) plus
what the review page needs to know about final.mp4/upload.md.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import cfg
from .templating import templates

router = APIRouter()


def _proj(slug: str):
    proj = cfg.PROJECTS / slug
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    return proj


def _read_qc(proj) -> dict | None:
    p = proj / "out" / "qc.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


@router.get("/projects/{slug}/review", response_class=HTMLResponse)
def review_page(request: Request, slug: str):
    proj = _proj(slug)
    qc = _read_qc(proj)
    upload_md = proj / "out" / "upload.md"
    return templates.TemplateResponse(
        request, "review.html",
        {"slug": slug, "gates": qc["gates"] if qc else [],
         "has_final": (proj / "out" / "final.mp4").exists(),
         "upload_md": (upload_md.read_text(encoding="utf-8")
                      if upload_md.exists() else None)})


@router.get("/api/projects/{slug}/qc")
def api_qc(slug: str):
    proj = _proj(slug)
    qc = _read_qc(proj)
    if qc is None:
        raise HTTPException(404, "no out/qc.json yet — run `fdx check`")
    return qc
