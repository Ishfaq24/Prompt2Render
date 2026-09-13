"""Prompt2Render local web dashboard application.

Provides a fast, local inspection dashboard for projects, generated video previews,
audio mastering verification, and QC gate reports.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from prompt2render import cfg, project

app = FastAPI(
    title="Prompt2Render Studio",
    description="Local studio dashboard for mathematical explainer video synthesis",
    version="1.0.0",
)


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
        except Exception:
            pass

    # Pipeline stage checkpoints
    has_audio = (proj_dir / "build" / "master.wav").exists() or (proj_dir / "build" / "master.m4a").exists()
    align_count = len(list((proj_dir / "build" / "align").glob("*.json"))) if (proj_dir / "build" / "align").is_dir() else 0
    scenes_count = len(list((proj_dir / "build" / "scenes").glob("scene_*.py"))) if (proj_dir / "build" / "scenes").is_dir() else 0
    
    final_video = proj_dir / "out" / "final.mp4"
    has_video = final_video.is_file() and final_video.stat().st_size > 1024
    video_size_mb = round(final_video.stat().st_size / (1024 * 1024), 2) if has_video else 0.0

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

    return {
        "slug": clean_slug,
        "title": title,
        "topic": topic,
        "sections_count": sections_count,
        "has_audio": has_audio,
        "align_count": align_count,
        "scenes_count": scenes_count,
        "has_video": has_video,
        "video_size_mb": video_size_mb,
        "qc_status": qc_status,
        "qc_data": qc_data,
    }


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


@app.get("/projects/{slug}/video")
def get_project_video(slug: str):
    """Stream final master video."""
    try:
        clean_slug = cfg.validate_slug(slug, exit_on_error=False)
    except (ValueError, SystemExit):
        raise HTTPException(status_code=400, detail="Invalid project slug")

    video_path = cfg.PROJECTS / clean_slug / "out" / "final.mp4"
    if not video_path.is_file():
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


@app.get("/", response_class=HTMLResponse)
def dashboard_html() -> str:
    """Render the responsive studio dashboard HTML."""
    projects_list = api_list_projects()
    cards_html = ""
    for p in projects_list:
        status_badge = (
            '<span class="badge badge-success">SHIPPABLE</span>'
            if p["qc_status"] in ("passed", "warning") and p["has_video"]
            else ('<span class="badge badge-warning">IN PROGRESS</span>' if p["has_audio"] else '<span class="badge badge-muted">SCAFFOLDED</span>')
        )
        video_btn = (
            f'<a href="/projects/{p["slug"]}/video" target="_blank" class="btn btn-primary">Play Final Video ({p["video_size_mb"]} MB)</a>'
            if p["has_video"]
            else '<span class="btn btn-disabled">No Video Yet</span>'
        )
        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">{p["title"]}</h3>
                {status_badge}
            </div>
            <p class="card-slug"><code>{p["slug"]}</code> &bull; {p["sections_count"]} sections</p>
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
            </div>
        </div>
        """

    if not cards_html:
        cards_html = "<p class='empty-text'>No projects found. Create one using <code>python prompt2render.py new &lt;slug&gt;</code></p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prompt2Render Studio</title>
    <style>
        :root {{
            --bg: #0B0F19;
            --card-bg: #131B2E;
            --border: #1E293B;
            --accent: #388BFD;
            --text: #F8FAFC;
            --dim: #94A3B8;
            --success: #10B981;
            --warning: #F59E0B;
        }}
        body {{
            margin: 0;
            padding: 2rem;
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .header {{
            max-width: 1000px;
            margin: 0 auto 2.5rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
        }}
        .header h1 {{ margin: 0 0 0.5rem; font-size: 1.8rem; font-weight: 700; color: #FFF; }}
        .header p {{ margin: 0; color: var(--dim); }}
        .container {{ max-width: 1000px; margin: 0 auto; display: grid; grid-gap: 1.5rem; }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
        }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
        .card-title {{ margin: 0; font-size: 1.25rem; font-weight: 600; }}
        .card-slug {{ margin: 0 0 0.5rem; font-size: 0.85rem; color: var(--dim); }}
        .card-topic {{ margin: 0 0 1rem; font-size: 0.95rem; color: #CBD5E1; }}
        .badge {{
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-weight: 600;
        }}
        .badge-success {{ background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.4); }}
        .badge-warning {{ background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .badge-muted {{ background: #1E293B; color: #94A3B8; }}
        .pipeline-progress {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin: 1rem 0;
            font-size: 0.85rem;
            color: var(--dim);
        }}
        .step {{ padding: 0.2rem 0.5rem; border-radius: 4px; background: #0F172A; border: 1px solid #1E293B; }}
        .step-done {{ background: rgba(56, 139, 253, 0.15); color: #60A5FA; border-color: #388BFD; }}
        .card-actions {{ margin-top: 1.2rem; display: flex; gap: 0.75rem; }}
        .btn {{
            text-decoration: none;
            display: inline-block;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
        }}
        .btn-primary {{ background: var(--accent); color: white; border: none; }}
        .btn-primary:hover {{ background: #2563EB; }}
        .btn-disabled {{ background: #1E293B; color: #64748B; cursor: not-allowed; }}
        .empty-text {{ color: var(--dim); text-align: center; padding: 3rem 0; }}
        code {{ background: #0F172A; padding: 0.2rem 0.4rem; border-radius: 4px; color: #388BFD; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎬 Prompt2Render Studio</h1>
        <p>Industrial, frame-accurate mathematical explainer video workbench</p>
    </div>
    <div class="container">
        {cards_html}
    </div>
</body>
</html>"""
