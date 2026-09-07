"""Tests for LottieAdapter and headless transparent frame generation."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from prompt2render.assets.adapters.lottie_adapter import LottieAdapter
from prompt2render.assets.loader import DEFAULT_ASSETS_DIR


def test_lottie_adapter_render_frames(tmp_path: Path):
    """Verify that LottieAdapter produces transparent 60fps RGBA frames."""
    lottie_file = DEFAULT_ASSETS_DIR / "lottie" / "packet_stream.json"
    assert lottie_file.is_file()

    adapter = LottieAdapter()
    out_dir = tmp_path / "frames"
    frames = adapter.render_frames(
        asset_file=lottie_file,
        target_width=200,
        target_height=100,
        duration_seconds=0.5,
        fps=30,
        output_dir=out_dir,
        tint_color="#1f6feb",
    )

    assert len(frames) == 15  # 0.5s * 30fps
    for f in frames:
        assert f.is_file()
        with Image.open(f) as img:
            assert img.mode == "RGBA"
            assert img.size == (200, 100)
