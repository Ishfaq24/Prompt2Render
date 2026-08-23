"""Snapshot/restore seam for Prompt2Render SceneContext.

The implementation remains in ``context.py`` because snapshot/restore operate
directly on the canonical ``SceneContext`` dataclass.

This module intentionally re-exports the functions so that the harness
runner, repair machinery, and tests have a stable import boundary without
coupling callers to the implementation location.
"""

from __future__ import annotations

from .context import (
    SceneContext,
    restore,
    snapshot,
)

__all__ = [
    "SceneContext",
    "snapshot",
    "restore",
]