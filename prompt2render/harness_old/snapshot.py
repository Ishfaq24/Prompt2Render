"""Copy-on-write snapshot/restore for SceneContext.

Implementation lives on context.py (snapshot() needs no knowledge beyond the dataclass itself);
this module is the named seam the plan calls for and what `runner.py`/tests import.
"""
from __future__ import annotations

from .context import SceneContext, restore, snapshot

__all__ = ["SceneContext", "snapshot", "restore"]
