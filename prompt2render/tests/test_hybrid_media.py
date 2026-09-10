"""Unit tests for 3D Animations & Mixed-Media Hybrid Video Architecture."""

from __future__ import annotations

import tempfile
from pathlib import Path

from prompt2render import project, scenes
from prompt2render.assets.mobjects.stages import MediaCard, SplitStage
from prompt2render.video_conform import (
    conform_video_for_section,
    create_placeholder_video,
    resolve_video_asset,
)


def test_script_multimedia_parsing():
    content = """---
title: Hybrid Video Test
---

## 1 - Real World Observation
> VIDEO: assets/videos/microscope.mp4
Observing the physical cells under high resolution.

## 2 - 3D Molecular Geometry
> 3D: A rotating 3D parametric surface of the binding site
Now let us examine the mathematical structure in three dimensions.

## 3 - Split Screen Analysis
> SPLIT: Left side micrograph, right side stress vector field
Notice the correlation between physical morphology and mechanical shear.

## 4 - Algorithmic Decision Boundary
> ANIM: [3d] A 3D coordinate space showing non-linear hyperplane
The hyperplane bends non-linearly across the z-axis.

## 5 - Legacy 2D Section
> ANIM: Standard vector diagram of linear equation
A simple 2D line separates the two clusters.
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_file = Path(tmpdir) / "script.md"
        script_file.write_text(content, encoding="utf-8")

        script = project.parse_script(script_file)
        assert len(script.sections) == 5

        # Section 1: Video
        sec1 = script.sections[0]
        assert sec1.media_type == "video"
        assert sec1.source_media == Path("assets/videos/microscope.mp4")
        assert scenes.select_renderer(sec1) == "video"

        # Section 2: 3D
        sec2 = script.sections[1]
        assert sec2.media_type == "manim_3d"
        assert scenes.select_renderer(sec2) == "manim_3d"
        assert scenes.is_manim_renderer(scenes.select_renderer(sec2))

        # Section 3: Split
        sec3 = script.sections[2]
        assert sec3.media_type == "split"
        assert scenes.select_renderer(sec3) == "split"
        assert scenes.is_manim_renderer(scenes.select_renderer(sec3))

        # Section 4: Inline [3d] tag
        sec4 = script.sections[3]
        assert sec4.media_type == "manim_3d"
        assert scenes.select_renderer(sec4) == "manim_3d"

        # Section 5: Standard 2D
        sec5 = script.sections[4]
        assert sec5.media_type == "auto"
        assert scenes.select_renderer(sec5) == "matplotlib"


def test_manim_3d_prompt_specification():
    content = """---
title: Neural Folding
---

## 1 - 3D Surface
> 3D: Rotating loss surface
Examining optimization landscape.
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        script_file = Path(tmpdir) / "script.md"
        script_file.write_text(content, encoding="utf-8")
        script = project.parse_script(script_file)
        sec = script.sections[0]

        sents = [{"start": 0.0, "end": 4.0, "text": "Examining optimization landscape."}]
        prompt = scenes.build_manim_prompt(script, sec, sents)

        assert "ThreeDScene" in prompt
        assert "set_camera_orientation" in prompt
        assert "orbit_3d_camera" in prompt


def test_media_card_creation():
    from manim import Rectangle
    media = Rectangle(width=4.5, height=2.8)
    card = MediaCard(media, label="Microscope Micrograph")
    assert card is not None
    assert len(card.submobjects) >= 2


def test_split_stage_with_media_card():
    from manim import Rectangle
    left_media = Rectangle(width=4.0, height=2.5)
    left_card = MediaCard(left_media, label="Clinical Specimen")
    right_graphic = Rectangle(width=4.0, height=2.5)

    stage = SplitStage(left=left_card, right=right_graphic, left_title="Observation", right_title="Simulation")
    assert stage is not None
    assert stage.left_item == left_card
    assert stage.right_item == right_graphic


def test_video_conformer_placeholder():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        out_mp4 = tmp_path / "scene_01.mp4"
        create_placeholder_video(out_mp4, duration_s=1.0, title="Ultrasound Clip")
        assert out_mp4.is_file()
        assert out_mp4.stat().st_size > 0


def test_resolve_video_asset():
    with tempfile.TemporaryDirectory() as tmpdir:
        proj = Path(tmpdir)
        assets_dir = proj / "assets" / "videos"
        assets_dir.mkdir(parents=True)
        sample_vid = assets_dir / "beating_heart.mp4"
        sample_vid.write_bytes(b"dummy video content")

        sec = project.Section(index=1, title="Beating Heart In Vivo", source_media=Path("beating_heart.mp4"))
        resolved = resolve_video_asset(proj, sec)
        assert resolved == sample_vid.resolve()
