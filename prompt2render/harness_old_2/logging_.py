"""Structured JSONL logging — the experimental evidence layer, not debug output.

One line per plugin invocation: plugin name, input/output context hash, pass/fail, diagnostics,
duration, token usage.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path

from .context import SceneContext


def _jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def context_hash(ctx: SceneContext) -> str:
    """A stable content hash of a SceneContext, for before/after comparison in the log."""
    blob = json.dumps(_jsonable(ctx), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class StructuredLogger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_invocation(self, *, plugin: str, input_ctx: SceneContext, output_ctx: SceneContext,
                        ok: bool, diagnostics: str = "", duration_s: float = 0.0,
                        token_usage: int | None = None) -> None:
        record = {
            "plugin": plugin,
            "input_context_hash": context_hash(input_ctx),
            "output_context_hash": context_hash(output_ctx),
            "ok": ok,
            "diagnostics": diagnostics,
            "duration_s": round(duration_s, 4),
            "token_usage": token_usage,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
