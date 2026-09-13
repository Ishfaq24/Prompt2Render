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
