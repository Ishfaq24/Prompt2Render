"""Rive state-machine animation adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from .base import AnimationAdapter


class RiveAdapter(AnimationAdapter):
    """Adapter for Rive (.riv) state-machine interactive animations."""

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
        # Rive state machine binding placeholder
        dest_file = output_dir / asset_file.name
        if not dest_file.exists() and asset_file.exists():
            import shutil
            shutil.copy2(asset_file, dest_file)
        return [dest_file]
