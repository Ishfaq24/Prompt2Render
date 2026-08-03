"""Upload panel: your own narration recordings (for --backend own), or
pre-made section clips via the `fdx import` escape hatch.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import cfg, project, visuals, voice
from .templating import templates

router = APIRouter()

# .m4a is deliberately excluded: voice.find_recording() reserves
# audio/<stem>.m4a for the auto-generated preview slice and refuses to
# treat it as a source, so an m4a upload under that name would silently
# never be picked up.
_UPLOAD_EXTS = tuple(e for e in voice.RAW_EXTS if e != ".m4a")


class ImportIn(BaseModel):
    src_dir: str


def _proj(slug: str):
    proj = cfg.PROJECTS / slug
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    return proj


@router.get("/projects/{slug}/upload", response_class=HTMLResponse)
def upload_page(request: Request, slug: str):
    proj = _proj(slug)
    try:
        script = project.parse_script(proj / "script.md")
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return templates.TemplateResponse(
        request, "upload.html",
        {"slug": slug, "exts": _UPLOAD_EXTS,
         "sections": [{"index": s.index, "stem": s.stem, "title": s.title}
                      for s in script.sections]})


@router.post("/api/projects/{slug}/audio/{stem}")
async def upload_audio(slug: str, stem: str, file: UploadFile):
    proj = _proj(slug)
    name = file.filename or ""
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in _UPLOAD_EXTS:
        raise HTTPException(400, f"unsupported extension '{ext}' — use one "
                                 f"of {', '.join(_UPLOAD_EXTS)}")
    audio_dir = proj / "audio"
    audio_dir.mkdir(exist_ok=True)
    dst = audio_dir / f"{stem}{ext}"
    dst.write_bytes(await file.read())
    return {"saved": str(dst.relative_to(proj))}


@router.post("/api/projects/{slug}/import")
def import_clips(slug: str, body: ImportIn):
    proj = _proj(slug)
    src = Path(body.src_dir).expanduser()
    if not src.is_dir():
        raise HTTPException(400, f"not a directory: {src}")
    try:
        made = visuals.import_sections(proj, src.resolve())
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return {"imported": [str(p.relative_to(proj)) for p in made]}
