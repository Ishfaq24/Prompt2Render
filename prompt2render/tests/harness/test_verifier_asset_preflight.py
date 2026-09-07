"""Tests for Preflight Asset & Parameter Schema Validation in verifier_execution."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from prompt2render.harness.context import CodeArtifact, SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.verifier_execution import (
    VerifierExecutionPlugin,
    _validate_asset_invocations,
    check_scene_artifact,
)


def test_valid_asset_invocation(tmp_path: Path):
    """Ensure valid asset call passes preflight check."""
    code = """
def draw(ax, cue):
    k.draw_asset(ax, "cpu_core", x=2.0, y=3.0, width=2.5)
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert errors == []


def test_missing_required_asset_param(tmp_path: Path):
    """Ensure missing required 'y' param triggers error."""
    code = """
def draw(ax, cue):
    k.draw_asset(ax, "cpu_core", x=2.0)
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert len(errors) == 1
    assert "Missing required parameter 'y'" in errors[0]


def test_unknown_asset_param(tmp_path: Path):
    """Ensure invalid kwarg name triggers preflight error."""
    code = """
def draw(ax, cue):
    k.draw_asset(ax, "cpu_core", x=2.0, y=3.0, invalid_flag=True)
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert len(errors) == 1
    assert "Unknown parameter 'invalid_flag'" in errors[0]


def test_missing_svg_file_in_manim_mode(tmp_path: Path):
    """Ensure SVGMobject with missing file triggers preflight error."""
    code = """
from manim import *

class Scene01(Scene):
    def construct(self):
        icon = SVGMobject("assets/missing_chip_xyz.svg")
        self.play(FadeIn(icon))
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert len(errors) == 1
    assert "missing_chip_xyz.svg" in errors[0]


def test_check_scene_artifact_emits_blocking_finding_on_bad_asset(tmp_path: Path):
    """Verify check_scene_artifact emits blocking finding for schema defect."""
    scene_file = tmp_path / "scene_01.py"
    scene_file.write_text("""
def draw(ax, cue):
    k.draw_asset(ax, "cpu_core", x=5.0, bogus_param=123)
""", encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path)
    entry = ScenePlanEntry(index=1, stem="01", title="Test")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=scene_file, generated=True)
    findings = check_scene_artifact(ctx, entry, gate=True)
    blocking = [f for f in findings if f.get("status") == "fail"]
    assert len(blocking) >= 1
    assert any("bogus_param" in f.get("message", "") for f in blocking)


def test_valid_animate_asset_invocation(tmp_path: Path):
    """Ensure valid animate_asset call passes preflight."""
    code = """
def draw(ax, cue):
    k.animate_asset(ax, "packet_stream", x=5.0, y=4.0, start_time=1.0, duration=2.5, scale=1.2)
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert errors == []


def test_invalid_animate_asset_param(tmp_path: Path):
    """Ensure unknown kwarg in animate_asset triggers error."""
    code = """
def draw(ax, cue):
    k.animate_asset(ax, "packet_stream", x=5.0, y=4.0, non_existent_prop=99)
"""
    errors = _validate_asset_invocations(code, tmp_path)
    assert len(errors) == 1
    assert "non_existent_prop" in errors[0]
