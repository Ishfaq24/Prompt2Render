"""SVG Vector animation and static asset adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from .base import AnimationAdapter


class SvgAdapter(AnimationAdapter):
    """Adapter for static and animated vector SVG assets."""

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
        # For SVG assets, return asset path directly or copy as frame
        dest_file = output_dir / asset_file.name
        if not dest_file.exists():
            import shutil
            shutil.copy2(asset_file, dest_file)
        return [dest_file]
