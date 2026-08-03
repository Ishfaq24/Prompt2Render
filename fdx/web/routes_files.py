"""Generic project-relative file server, with a path-traversal guard.

Backs scene thumbnails, the final video, the thumbnail image, and the
upload.md preview -- anything under a project directory a page needs to
reference by URL.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import cfg

router = APIRouter()


@router.get("/projects/{slug}/files/{path:path}")
def get_file(slug: str, path: str):
    proj = (cfg.PROJECTS / slug).resolve()
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    target = (proj / path).resolve()
    if target != proj and proj not in target.parents:
        raise HTTPException(403, "path escapes the project directory")
    if not target.is_file():
        raise HTTPException(404, f"no such file: {path}")
    return FileResponse(target)
