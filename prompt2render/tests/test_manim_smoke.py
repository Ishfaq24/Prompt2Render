"""Real Manim render smoke test -- slow, needs manim + LaTeX on PATH.

Skipped by default; opt in with:
    P2R_MANIM_SMOKE=1 pytest prompt2render/tests/test_manim_smoke.py

Shares its scene and verification logic with `prompt2render doctor
--render-test` (see manim_smoke.py) so the two never diverge.
"""

import os
import tempfile
from pathlib import Path

import pytest

from prompt2render import cfg, manim_smoke

pytestmark = pytest.mark.skipif(
    os.environ.get("P2R_MANIM_SMOKE", "") != "1",
    reason="set P2R_MANIM_SMOKE=1 to run the real Manim render",
)


def test_manim_smoke_renders_1920x1080_30fps():
    with tempfile.TemporaryDirectory(prefix="p2r-manim-smoke-test-") as tmp:
        clip = manim_smoke.render_smoke_scene(Path(tmp))

        assert clip.exists()
        assert clip.stat().st_size > 10_000

        info = manim_smoke.probe_clip(clip)
        assert info["width"] == cfg.WIDTH
        assert info["height"] == cfg.HEIGHT
        assert abs(info["fps"] - cfg.FPS) < 0.01
