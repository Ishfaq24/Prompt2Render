"""Scene review: aggregate manifest.json per section, and regenerate one
section's storyboard from scratch when its stills need reworking.
"""
from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .. import cfg, project, stills
from .jobs import JobConflict, manager
from .templating import templates

router = APIRouter()


def _load(slug: str):
    proj = cfg.PROJECTS / slug
    if not proj.is_dir():
        raise HTTPException(404, f"no project '{slug}'")
    try:
        script = project.parse_script(proj / "script.md")
    except SystemExit as e:
        raise HTTPException(400, str(e))
    return proj, script


def _sections_data(proj, script) -> list[dict]:
    out = []
    for sec in script.sections:
        scene_py = stills.scene_path(proj, sec.stem)
        man_path = stills.stills_dir(proj, sec.stem) / "manifest.json"
        rendered = []
        if man_path.exists():
            try:
                man = json.loads(man_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                man = []
            rendered = [
                {**item, "url": f"/projects/{proj.name}/files/build/scenes/"
                                f"{sec.stem}/{item['png']}"}
                for item in man
            ]
        out.append({"index": sec.index, "stem": sec.stem, "title": sec.title,
                   "has_scene": scene_py.exists(), "stills": rendered})
    return out


@router.get("/projects/{slug}/scenes", response_class=HTMLResponse)
def scenes_page(request: Request, slug: str):
    proj, script = _load(slug)
    return templates.TemplateResponse(
        request, "scenes.html",
        {"slug": slug, "sections": _sections_data(proj, script)})


@router.get("/api/projects/{slug}/scenes")
def api_scenes(slug: str):
    proj, script = _load(slug)
    return {"sections": _sections_data(proj, script)}


@router.post("/api/projects/{slug}/scenes/{index}/regenerate")
def regenerate_scene(slug: str, index: int):
    proj, script = _load(slug)
    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        raise HTTPException(404, f"no section {index} in script.md")

    # Mirrors what's done by hand when a storyboard needs reworking: clear
    # the old module and its stale stills so the gallery doesn't show a
    # half-regenerated mix, then let `fdx scenes --section N` rebuild both.
    stills.scene_path(proj, sec.stem).unlink(missing_ok=True)
    still_dir = stills.stills_dir(proj, sec.stem)
    if still_dir.exists():
        shutil.rmtree(still_dir)

    try:
        job = manager.start(slug, "scenes", ["--section", str(index)], total=1)
    except JobConflict as e:
        raise HTTPException(409, str(e))
    return job.snapshot()
