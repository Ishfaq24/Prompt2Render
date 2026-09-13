"""Unit tests for project slug and path traversal validation security."""
from __future__ import annotations

import pytest
from prompt2render import cfg, project


def test_validate_slug_valid():
    assert cfg.validate_slug("binary-search") == "binary-search"
    assert cfg.validate_slug("neural_network_123") == "neural_network_123"
    assert cfg.validate_slug("Project.v2") == "Project.v2"


@pytest.mark.parametrize("bad_slug", [
    "../outside",
    r"..\outside",
    "../../etc",
    "/etc/passwd",
    r"C:\Windows\System32",
    "folder/subfolder",
    r"folder\subfolder",
    "slug:colon",
    "slug\0null",
    "",
    "   ",
    "..",
    ".hidden",
])
def test_validate_slug_invalid(bad_slug):
    with pytest.raises((ValueError, SystemExit)):
        cfg.validate_slug(bad_slug, exit_on_error=False)


def test_project_dir_blocks_traversal():
    with pytest.raises(SystemExit) as exc_info:
        cfg.project_dir("../escaped_project")
    assert "invalid project slug" in str(exc_info.value)


def test_scaffold_dirs_blocks_traversal():
    with pytest.raises(SystemExit) as exc_info:
        project._scaffold_dirs("../../malicious")
    assert "invalid project slug" in str(exc_info.value)


def test_safe_subprocess_env_strips_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super_secret_gemini_key")
    monkeypatch.setenv("PIXABAY_API_KEY", "pixabay_secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws_secret")
    monkeypatch.setenv("DATABASE_PASSWORD", "db_pass")
    monkeypatch.setenv("AUTH_TOKEN", "auth_tok")
    monkeypatch.setenv("PATH", "C:\\Windows\\system32")

    env = cfg.safe_subprocess_env({"PYTHONPATH": "C:\\projects\\Prompt2Render"})
    assert "PATH" in env
    assert env["PYTHONPATH"] == "C:\\projects\\Prompt2Render"
    assert "GEMINI_API_KEY" not in env
    assert "PIXABAY_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "DATABASE_PASSWORD" not in env
    assert "AUTH_TOKEN" not in env


def test_validate_scene_security(tmp_path):
    from prompt2render.stills import validate_scene_security

    # Safe scene passes
    safe_file = tmp_path / "safe_scene.py"
    safe_file.write_text("import numpy as np\nimport math\n\ndef draw(): pass\n", encoding="utf-8")
    validate_scene_security(safe_file)

    # Malicious import is blocked
    bad_import = tmp_path / "bad_import.py"
    bad_import.write_text("import subprocess\nsubprocess.run(['dir'])\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        validate_scene_security(bad_import)
    assert "security rejection" in str(exc.value)

    # Malicious eval call is blocked
    bad_call = tmp_path / "bad_call.py"
    bad_call.write_text("eval('print(1)')\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        validate_scene_security(bad_call)
    assert "security rejection" in str(exc.value)

