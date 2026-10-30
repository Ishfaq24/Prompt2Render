"""Unit tests for the prompt2render.web FastAPI dashboard."""
from __future__ import annotations

from fastapi.testclient import TestClient
from prompt2render.web.app import app

client = TestClient(app)


def test_dashboard_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "Prompt2Render Studio" in response.text


def test_api_list_projects():
    response = client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_project_traversal_blocked():
    response = client.get("/projects/../outside/video")
    # Traversal should result in 400 Bad Request or 404 Not Found, never 200 or 500
    assert response.status_code in (400, 404)


def test_api_hitl_feedback_lifecycle(tmp_path, monkeypatch):
    from prompt2render import cfg
    import json
    monkeypatch.setattr(cfg, "PROJECTS", tmp_path)

    slug = "test-hitl-proj"
    proj_dir = tmp_path / slug
    proj_dir.mkdir(parents=True)
    script_content = """---
title: "HITL Test"
---

## 1 - Intro
> ANIM: sample anim

Welcome to HITL test.
"""
    (proj_dir / "script.md").write_text(script_content, encoding="utf-8")

    # 1. Fetch sections before HITL
    resp = client.get(f"/api/projects/{slug}/sections")
    assert resp.status_code == 200
    sections = resp.json()
    assert len(sections) == 1
    assert sections[0]["stem"] == "01"
    assert sections[0]["hitl_status"] == "none"

    # 2. Submit reject feedback
    post_resp = client.post(
        f"/api/projects/{slug}/hitl",
        json={"stem": "01", "status": "reject", "reason": "Text overlaps diagram"},
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["ok"] is True

    # Verify hitl_feedback.json written to disk
    hitl_file = proj_dir / "hitl_feedback.json"
    assert hitl_file.is_file()
    hitl_data = json.loads(hitl_file.read_text(encoding="utf-8"))
    assert hitl_data["01"]["status"] == "reject"
    assert hitl_data["01"]["reason"] == "Text overlaps diagram"

    # Check that sections query now reflects reject status
    resp_after = client.get(f"/api/projects/{slug}/sections")
    assert resp_after.json()[0]["hitl_status"] == "reject"

    # 3. Submit accept feedback
    accept_resp = client.post(
        f"/api/projects/{slug}/hitl",
        json={"stem": "01", "status": "accept"},
    )
    assert accept_resp.status_code == 200
    hitl_data2 = json.loads(hitl_file.read_text(encoding="utf-8"))
    assert hitl_data2["01"]["status"] == "accept"

    # 4. Clear/Delete HITL feedback
    del_resp = client.delete(f"/api/projects/{slug}/hitl/01")
    assert del_resp.status_code == 200
    assert del_resp.json()["cleared"] is True
    assert not hitl_file.exists()


def test_hitl_invalid_requests():
    # Missing stem
    r1 = client.post("/api/projects/sample/hitl", json={"status": "reject"})
    assert r1.status_code == 400

    # Invalid status
    r2 = client.post("/api/projects/sample/hitl", json={"stem": "01", "status": "unknown"})
    assert r2.status_code == 400

    # Traversal in slug (Starlette url path resolution returns 404, or validator returns 400)
    r3 = client.post("/api/projects/../sample/hitl", json={"stem": "01", "status": "reject"})
    assert r3.status_code in (400, 404)


def test_studio_static_and_workbench():
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "Turn any topic into" in r_home.text
    assert 'data-mode="build"' in r_home.text
    assert 'data-mode="harness"' in r_home.text
    assert 'id="view-library"' in r_home.text

    r_css = client.get("/static/css/studio.css")
    assert r_css.status_code == 200
    assert "--sky-500" in r_css.text

    r_js = client.get("/static/js/studio.js")
    assert r_js.status_code == 200
    assert "/api/studio/run" in r_js.text

    r_wb = client.get("/workbench")
    assert r_wb.status_code == 200
    assert "Workbench" in r_wb.text
    assert "--bg: #F8FCFF" in r_wb.text
    assert 'id="result-save-lib"' in r_home.text
    assert 'id="opt-dialogue"' in r_home.text
    assert 'id="opt-lang"' in r_home.text


def test_library_listing_and_prettify(tmp_path, monkeypatch):
    from prompt2render.web import library

    assert library.prettify_name("GradientDescent") == "Gradient Descent"
    assert library.prettify_name("RSA-Full-Explainer") == "RSA Full Explainer"
    assert library.prettify_name("KashurMl") == "Kashur ML"
    assert library.prettify_name("Virtualmemory") == "Virtual Memory"
    assert library.detect_language("KMeansHindi") == "Hindi"
    assert library.detect_language("QuickSortUrdu") == "Urdu"

    monkeypatch.setattr(library, "LIBRARY_DIR", tmp_path)
    monkeypatch.setattr(library, "CACHE_DIR", tmp_path / "_cache")
    (tmp_path / "FourierTransform.mp4").write_bytes(b"\x00" * 4096)

    resp = client.get("/api/library")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["count"] == 1
    assert payload["items"][0]["title"] == "Fourier Transform"
    assert payload["items"][0]["filename"] == "FourierTransform.mp4"

    vid = client.get("/library/FourierTransform.mp4/video")
    assert vid.status_code == 200
    assert len(vid.content) == 4096

    missing = client.get("/library/does-not-exist.mp4/video")
    assert missing.status_code == 404


def test_studio_projects_and_run_modes(tmp_path, monkeypatch):
    import importlib
    from prompt2render import cfg
    web_app = importlib.import_module("prompt2render.web.app")

    monkeypatch.setattr(cfg, "PROJECTS", tmp_path)
    proj = tmp_path / "binary-search-visualized"
    (proj / "out").mkdir(parents=True)
    (proj / "script.md").write_text("---\ntitle: \"Binary Search Visualized\"\n---\n\n## 1 - Intro\nHi.\n", encoding="utf-8")
    (proj / "out" / "BinarySearch.mp4").write_bytes(b"\x00" * 2048)

    # Renamed MP4 in out/ is still discovered as project video
    r_projs = client.get("/api/studio/projects")
    assert r_projs.status_code == 200
    items = r_projs.json()
    assert len(items) == 1
    assert items[0]["slug"] == "binary-search-visualized"
    assert items[0]["has_video"] is True

    r_vid = client.get("/projects/binary-search-visualized/video")
    assert r_vid.status_code == 200

    recorded = []

    def fake_create_job(command, description, meta=None):
        job = web_app.StudioJob("testjob1", command, description, meta)
        job.status = "completed"
        recorded.append(job)
        return job

    monkeypatch.setattr(web_app.job_manager, "create_job", fake_create_job)

    # Build mode resolves fuzzy topic "binary search" -> "binary-search-visualized"
    r_build = client.post("/api/studio/run", json={"topic": "binary search", "mode": "build"})
    assert r_build.status_code == 200
    assert r_build.json()["slug"] == "binary-search-visualized"
    assert "build" in recorded[-1].command

    # Build mode on unknown topic returns 404 suggesting Harness
    r_miss = client.post("/api/studio/run", json={"topic": "brand new topic", "mode": "build"})
    assert r_miss.status_code == 404

    # Harness mode runs `auto <slug> --harness` end-to-end
    r_harn = client.post(
        "/api/studio/run",
        json={
            "topic": "Quantum Entanglement",
            "mode": "harness",
            "minutes": 3,
            "manim": True,
            "strict": True,
            "dialogue": True,
            "language": "hi",
        },
    )
    assert r_harn.status_code == 200
    assert r_harn.json()["slug"] == "quantum-entanglement"
    cmd = recorded[-1].command
    assert "auto" in cmd and "--harness" in cmd and "--manim" in cmd and "--strict" in cmd
    assert "--dialogue" in cmd and "--lang" in cmd and "hi" in cmd


def test_publish_project_to_library(tmp_path, monkeypatch):
    from prompt2render import cfg
    from prompt2render.web import library

    projects_dir = tmp_path / "projects"
    lib_dir = tmp_path / "Final Results"
    monkeypatch.setattr(cfg, "PROJECTS", projects_dir)
    monkeypatch.setattr(library, "LIBRARY_DIR", lib_dir)
    monkeypatch.setattr(library, "CACHE_DIR", tmp_path / "_cache")

    proj = projects_dir / "llm-evaluations"
    (proj / "out").mkdir(parents=True)
    (proj / "script.md").write_text(
        '---\ntitle: "LLM Evaluations"\n---\n\n## 1 - Intro\n> ANIM: test\n\nHello.\n',
        encoding="utf-8",
    )
    (proj / "out" / "final.mp4").write_bytes(b"\x00" * 4096)

    resp = client.post("/api/projects/llm-evaluations/publish-library")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["item"]["filename"] == "LLMEvaluations.mp4"
    assert (lib_dir / "LLMEvaluations.mp4").is_file()
    assert library.prettify_name("LLMEvaluations") == "LLM Evaluations"


