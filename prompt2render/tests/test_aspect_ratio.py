"""Tests for aspect ratio profiles, vertical video support, and canvas boundaries."""

import pytest
from pathlib import Path
from prompt2render import cfg, project, cli
from prompt2render.manim_audit import ManimLayoutAuditor


@pytest.fixture(autouse=True)
def reset_dimensions():
    """Ensure dimensions are reset back to 16:9 default after each test."""
    cfg.set_dimensions("16:9")
    yield
    cfg.set_dimensions("16:9")


def test_set_dimensions_profiles():
    # 16:9 Landscape
    w, h = cfg.set_dimensions("16:9")
    assert (w, h) == (1920, 1080)
    assert (cfg.WIDTH, cfg.HEIGHT) == (1920, 1080)

    # 9:16 Portrait / Shorts
    w, h = cfg.set_dimensions("9:16")
    assert (w, h) == (1080, 1920)
    assert (cfg.WIDTH, cfg.HEIGHT) == (1080, 1920)

    w, h = cfg.set_dimensions("shorts")
    assert (w, h) == (1080, 1920)

    w, h = cfg.set_dimensions("portrait")
    assert (w, h) == (1080, 1920)

    # 1:1 Square
    w, h = cfg.set_dimensions("1:1")
    assert (w, h) == (1080, 1080)
    assert (cfg.WIDTH, cfg.HEIGHT) == (1080, 1080)


def test_set_dimensions_custom_string_and_ints():
    w, h = cfg.set_dimensions("720x1280")
    assert (w, h) == (720, 1280)
    assert (cfg.WIDTH, cfg.HEIGHT) == (720, 1280)

    w, h = cfg.set_dimensions(3840, 2160)
    assert (w, h) == (3840, 2160)
    assert (cfg.WIDTH, cfg.HEIGHT) == (3840, 2160)


def test_project_new_project_with_aspect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cfg, "PROJECTS", tmp_path)
    proj_dir = project.new_project(
        "test-shorts",
        "Quantum Computing",
        minutes=1.0,
        aspect="9:16",
    )
    script_path = proj_dir / "script.md"
    assert script_path.is_file()
    content = script_path.read_text(encoding="utf-8")
    assert "aspect: 9:16" in content


def test_cli_load_applies_aspect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cfg, "PROJECTS", tmp_path)
    slug = "test-load-aspect"
    proj_dir = tmp_path / slug
    proj_dir.mkdir(parents=True)
    script_content = """---
title: "Black Holes"
slug: "test-load-aspect"
aspect: 9:16
---

## 1 - Intro
> ANIM: show black hole

Welcome to quick shorts.
"""
    (proj_dir / "script.md").write_text(script_content, encoding="utf-8")
    
    # Ensure starting in default 16:9
    cfg.set_dimensions("16:9")
    assert (cfg.WIDTH, cfg.HEIGHT) == (1920, 1080)

    # Load project using cli._load
    loaded_dir, loaded_script = cli._load(slug)
    assert loaded_dir == proj_dir
    # Check that dimensions were automatically adjusted
    assert (cfg.WIDTH, cfg.HEIGHT) == (1080, 1920)


def test_manim_auditor_dynamic_bounds():
    # Test 16:9 bounds
    cfg.set_dimensions("16:9")
    x_min, x_max, y_min, y_max, caption_ceiling = ManimLayoutAuditor.get_bounds()
    assert x_min < -6.9 and x_max > 6.9
    assert (y_min, y_max) == (-4.0, 4.0)
    assert caption_ceiling == -2.5

    # Test 9:16 bounds (aspect 0.5625 -> half_width = 2.25)
    cfg.set_dimensions("9:16")
    x_min, x_max, y_min, y_max, caption_ceiling = ManimLayoutAuditor.get_bounds()
    assert -2.2 <= x_min <= -2.1
    assert 2.1 <= x_max <= 2.2
    assert (y_min, y_max) == (-4.0, 4.0)
    assert caption_ceiling == -2.5

    # Test 1:1 bounds (aspect 1.0 -> half_width = 4.0)
    cfg.set_dimensions("1:1")
    x_min, x_max, y_min, y_max, caption_ceiling = ManimLayoutAuditor.get_bounds()
    assert -4.0 <= x_min <= -3.8
    assert 3.8 <= x_max <= 4.0
