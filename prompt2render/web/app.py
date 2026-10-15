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
        except Exception:
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
    except Exception:
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


@app.get("/", response_class=HTMLResponse)
def dashboard_html() -> str:
    """Render the responsive studio dashboard HTML."""
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
                        <th width="360">Feedback Action</th>
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
            --reject: #EF4444;
        }}
        body {{
            margin: 0;
            padding: 2rem;
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        .header {{
            max-width: 1100px;
            margin: 0 auto 2.5rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
        }}
        .header h1 {{ margin: 0 0 0.5rem; font-size: 1.8rem; font-weight: 700; color: #FFF; }}
        .header p {{ margin: 0; color: var(--dim); }}
        .container {{ max-width: 1100px; margin: 0 auto; display: grid; grid-gap: 1.5rem; }}
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
        .badge-reject {{ background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
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
            border: none;
        }}
        .btn-primary {{ background: var(--accent); color: white; }}
        .btn-primary:hover {{ background: #2563EB; }}
        .btn-secondary {{ background: #1E293B; color: #E2E8F0; border: 1px solid #334155; }}
        .btn-secondary:hover {{ background: #334155; }}
        .btn-disabled {{ background: #1E293B; color: #64748B; cursor: not-allowed; }}
        .btn-sm {{ padding: 0.25rem 0.6rem; font-size: 0.8rem; }}
        .btn-accept {{ background: #059669; color: white; }}
        .btn-accept:hover {{ background: #10B981; }}
        .btn-reject {{ background: #DC2626; color: white; }}
        .btn-reject:hover {{ background: #EF4444; }}
        .review-panel {{ margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border); }}
        .review-panel h4 {{ margin: 0 0 1rem; font-size: 1rem; color: #E2E8F0; }}
        .sec-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        .sec-table th {{ text-align: left; padding: 0.5rem; color: var(--dim); border-bottom: 1px solid var(--border); }}
        .sec-table td {{ padding: 0.6rem 0.5rem; border-bottom: 1px solid #1A2234; vertical-align: middle; }}
        .sec-title {{ font-weight: 600; color: #F1F5F9; margin-bottom: 0.2rem; }}
        .sec-narr {{ color: var(--dim); font-size: 0.78rem; }}
        .sec-link {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
        .hitl-ctrls {{ display: flex; gap: 0.4rem; align-items: center; }}
        .badge-lang {{ background: rgba(56, 139, 253, 0.2); color: #60A5FA; border: 1px solid rgba(56, 139, 253, 0.4); }}
        .generator-card {{ background: #151D33; border: 1px solid #2B3A5A; border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; }}
        .form-row {{ display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 1rem; margin-bottom: 1rem; align-items: end; }}
        .form-group {{ display: flex; flex-direction: column; gap: 0.35rem; }}
        .form-group label {{ font-size: 0.8rem; color: var(--dim); font-weight: 500; }}
        .form-control {{ background: #0B0F19; border: 1px solid var(--border); border-radius: 6px; color: #FFF; padding: 0.5rem 0.75rem; font-size: 0.875rem; }}
        .toggles-row {{ display: flex; gap: 1.5rem; align-items: center; margin-bottom: 1.2rem; font-size: 0.85rem; color: #CBD5E1; }}
        .preview-box {{ background: #0B0F19; border: 1px dashed #334155; border-radius: 6px; padding: 0.75rem; font-size: 0.85rem; color: #94A3B8; margin-bottom: 1rem; }}
        .input-reason {{ background: #0F172A; border: 1px solid #334155; border-radius: 4px; color: #FFF; padding: 0.25rem 0.5rem; font-size: 0.8rem; flex-grow: 1; }}
        .empty-text {{ color: var(--dim); text-align: center; padding: 3rem 0; }}
        .dim {{ color: #64748B; }}
        code {{ background: #0F172A; padding: 0.2rem 0.4rem; border-radius: 4px; color: #388BFD; }}
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
    </script>
</head>
<body>
    <div class="header">
        <h1>🎬 Prompt2Render Studio</h1>
        <p>Industrial, frame-accurate multilingual educational video workbench</p>
    </div>
    <div class="container">
        <div class="generator-card">
            <h3 style="margin-top:0;margin-bottom:1rem;color:#FFF;">🌐 Generate Multilingual Educational Video</h3>
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
</body>
</html>"""

