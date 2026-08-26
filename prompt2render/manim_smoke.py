"""A minimal, deterministic Manim scene for verifying the installed release.

Shared by ``prompt2render doctor --render-test`` and
``tests/test_manim_smoke.py`` so the two never diverge. This deliberately
does not touch the rest of the Prompt2Render pipeline (no script.md, no
narration, no section contract) -- it only proves that Manim itself starts,
renders, and produces a real 1920x1080 @ 30 fps clip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import cfg

SCENE_CLASS = "P2RSmokeScene"

_SCENE_SOURCE = f'''
from manim import *


class {SCENE_CLASS}(Scene):
    def construct(self):
        title = Text("Prompt2Render Manim Smoke Test", font_size=36)
        title.to_edge(UP)

        box = Rectangle(width=3, height=1.5, color=BLUE)
        label = Text("box", font_size=24)
        label.next_to(box, DOWN, buff=0.2)
        group = VGroup(box, label)

        formula = MathTex(r"E = mc^2")
        formula.next_to(group, DOWN)

        arrow = Arrow(start=LEFT * 3, end=RIGHT * 3)
        arrow.next_to(formula, DOWN)

        snippet = Code(
            code_string="def add(a, b):\\n    return a + b",
            language="python",
            formatter_style="monokai",
            add_line_numbers=True,
            paragraph_config={{"font_size": 18}},
        )
        snippet.scale_to_fit_width(6)
        snippet.next_to(arrow, DOWN)

        self.play(Write(title))
        self.play(Create(box), Write(label))
        self.play(Write(formula))
        self.play(Create(arrow))
        self.play(FadeIn(snippet))
        self.play(Transform(box, box.copy().set_color(GREEN)))
        self.wait(0.2)
'''


def render_smoke_scene(work_dir: Path) -> Path:
    """Render the smoke scene into ``work_dir`` and return the produced mp4."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    scene_file = work_dir / "smoke_scene.py"
    scene_file.write_text(_SCENE_SOURCE, encoding="utf-8")

    media_dir = work_dir / "media"

    cmd = [
        sys.executable, "-m", "manim", "-ql", "--format", "mp4",
        "--fps", str(cfg.FPS), "-r", f"{cfg.WIDTH},{cfg.HEIGHT}",
        "--media_dir", str(media_dir), str(scene_file), SCENE_CLASS,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    if proc.returncode != 0:
        diagnostics = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"manim smoke render crashed: {diagnostics}")

    found = sorted(
        media_dir.rglob(f"{SCENE_CLASS}.mp4"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    if not found:
        raise RuntimeError(
            f"manim produced no {SCENE_CLASS}.mp4 under {media_dir}"
        )

    return found[-1]


def probe_clip(path: Path) -> dict:
    """Return width/height/fps/size_bytes for a rendered clip via ffprobe."""
    info = cfg.probe(path)

    video = next(
        (
            stream
            for stream in info.get("streams", [])
            if stream.get("codec_type") == "video"
        ),
        None,
    )
    if video is None:
        raise RuntimeError(f"no video stream in {path}")

    num, _, den = str(video.get("r_frame_rate", "0/1")).partition("/")
    fps = (float(num) / float(den)) if den and float(den) else float(num or 0)

    return {
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "size_bytes": Path(path).stat().st_size,
    }


__all__ = ["SCENE_CLASS", "probe_clip", "render_smoke_scene"]
