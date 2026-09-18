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

