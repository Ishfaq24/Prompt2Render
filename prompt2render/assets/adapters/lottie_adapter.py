"""Headless offline Lottie JSON animation rasterizer and adapter."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageColor

from .base import AnimationAdapter


def _interpolate_keyframe(keyframes: list[dict[str, Any]], frame_t: float) -> list[float]:
    """Interpolate multi-dimensional keyframe value at time frame_t."""
    if not keyframes:
        return [0.0, 0.0, 0.0]

    # If static single value
    if "s" not in keyframes[0]:
        return keyframes

    # Check boundaries
    if frame_t <= keyframes[0]["t"]:
        return list(keyframes[0].get("s", [0.0]))

    for i in range(len(keyframes) - 1):
        k1 = keyframes[i]
        k2 = keyframes[i + 1]
        t1, t2 = k1["t"], k2["t"]

        if t1 <= frame_t <= t2:
            span = t2 - t1
            factor = (frame_t - t1) / span if span > 0 else 0.0
            # Linear / ease factor
            s1 = k1.get("s", [0.0])
            s2 = k1.get("e", k2.get("s", s1))
            res = []
            for a, b in zip(s1, s2):
                res.append(a + (b - a) * factor)
            return res

    # After last keyframe
    last = keyframes[-1]
    return list(last.get("e", last.get("s", [0.0])))


class LottieAdapter(AnimationAdapter):
    """Headless Lottie JSON animation adapter rendering transparent RGBA frames."""

    def render_frames(
        self,
        asset_file: Path,
        target_width: int,
        target_height: int,
        duration_seconds: float,
        fps: int,
        output_dir: Path,
        tint_color: str | None = None,
        state_inputs: dict[str, Any] | None = None,
    ) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        data = json.loads(asset_file.read_text(encoding="utf-8"))

        native_w = float(data.get("w", 400))
        native_h = float(data.get("h", 300))
        native_fps = float(data.get("fr", 60))
        native_ip = float(data.get("ip", 0))
        native_op = float(data.get("op", 120))
        native_duration = (native_op - native_ip) / native_fps if native_fps > 0 else 2.0

        scale_x = target_width / native_w if native_w > 0 else 1.0
        scale_y = target_height / native_h if native_h > 0 else 1.0

        total_frames = max(1, int(duration_seconds * fps))
        frame_paths: list[Path] = []

        parsed_tint = ImageColor.getrgb(tint_color) if tint_color else None

        for f_idx in range(total_frames):
            # Calculate corresponding animation time in native Lottie frames
            progress = (f_idx / total_frames) if total_frames > 1 else 0.0
            # Loop progress if duration_seconds > native_duration
            lottie_t = native_ip + (progress * (duration_seconds / native_duration) % 1.0) * (native_op - native_ip)

            # Create transparent RGBA frame
            img = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img, "RGBA")

            for layer in data.get("layers", []):
                ks = layer.get("ks", {})
                # Layer opacity
                opacity_val = 100.0
                if "o" in ks:
                    if ks["o"].get("a") == 1:
                        o_res = _interpolate_keyframe(ks["o"]["k"], lottie_t)
                        opacity_val = o_res[0] if o_res else 100.0
                    else:
                        opacity_val = float(ks["o"].get("k", 100))

                alpha_mult = max(0.0, min(1.0, opacity_val / 100.0))
                if alpha_mult <= 0.01:
                    continue

                # Position
                pos = [native_w / 2.0, native_h / 2.0]
                if "p" in ks:
                    if ks["p"].get("a") == 1:
                        pos = _interpolate_keyframe(ks["p"]["k"], lottie_t)[:2]
                    else:
                        pos = list(ks["p"].get("k", [native_w / 2.0, native_h / 2.0]))[:2]

                # Draw shapes in layer
                for shape in layer.get("shapes", []):
                    stype = shape.get("ty")
                    if stype == "rc":  # Rectangle
                        s_dims = shape.get("s", {}).get("k", [40, 40])
                        s_pos = shape.get("p", {}).get("k", [0, 0])
                        rx = shape.get("r", {}).get("k", 0)

                        cx = (pos[0] + s_pos[0]) * scale_x
                        cy = (pos[1] + s_pos[1]) * scale_y
                        w = s_dims[0] * scale_x
                        h = s_dims[1] * scale_y

                        x0, y0 = cx - w / 2.0, cy - h / 2.0
                        x1, y1 = cx + w / 2.0, cy + h / 2.0

                        fill_col = parsed_tint or (31, 111, 235)
                        stroke_col = parsed_tint or (88, 166, 255)
                        fill_rgba = (fill_col[0], fill_col[1], fill_col[2], int(255 * alpha_mult))
                        stroke_rgba = (stroke_col[0], stroke_col[1], stroke_col[2], int(255 * alpha_mult))

                        draw.rounded_rectangle([x0, y0, x1, y1], radius=rx * scale_x, fill=fill_rgba, outline=stroke_rgba, width=max(1, int(2 * scale_x)))

                    elif stype == "el":  # Ellipse / Circle
                        s_dims = shape.get("s", {}).get("k", [20, 20])
                        s_pos = shape.get("p", {}).get("k", [0, 0])

                        cx = (pos[0] + s_pos[0]) * scale_x
                        cy = (pos[1] + s_pos[1]) * scale_y
                        r_x = (s_dims[0] / 2.0) * scale_x
                        r_y = (s_dims[1] / 2.0) * scale_y

                        fill_col = parsed_tint or (63, 185, 80)
                        fill_rgba = (fill_col[0], fill_col[1], fill_col[2], int(255 * alpha_mult))

                        draw.ellipse([cx - r_x, cy - r_y, cx + r_x, cy + r_y], fill=fill_rgba)

            frame_file = output_dir / f"frame_{f_idx:04d}.png"
            img.save(frame_file, format="PNG")
            frame_paths.append(frame_file)

        return frame_paths
