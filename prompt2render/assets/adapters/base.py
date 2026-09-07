"""Base contracts for multi-format animation adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AnimationAdapter(ABC):
    """Abstract interface implemented by all format-specific animation engines."""

    @abstractmethod
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
        """Render animation to an ordered sequence of transparent RGBA PNG frames."""
        raise NotImplementedError
