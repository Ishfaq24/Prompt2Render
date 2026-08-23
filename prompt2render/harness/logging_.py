"""Structured JSONL evidence logging for the Prompt2Render harness.

This module records experimental evidence rather than ordinary debug output.

Two artifacts are produced:

1. JSONL invocation log
   One record per plugin invocation containing:
       plugin
       input/output context hashes
       success/failure
       diagnostics
       duration
       token usage
       timestamp

2. self_correction_report.json
   Machine-readable summary of the complete self-correction run.

The logger deliberately does not alter SceneContext. Logging must remain
observational so that instrumentation cannot change pipeline behavior.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .context import SceneContext


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _jsonable(
    obj: Any,
) -> Any:
    """Convert harness objects into deterministic JSON-compatible values."""

    if obj is None or isinstance(
        obj,
        (str, int, float, bool),
    ):
        return obj

    if isinstance(
        obj,
        enum.Enum,
    ):
        return obj.value

    if isinstance(
        obj,
        (datetime, date),
    ):
        return obj.isoformat()

    if isinstance(
        obj,
        Path,
    ):
        return str(
            obj
        )

    if dataclasses.is_dataclass(
        obj
    ) and not isinstance(
        obj,
        type,
    ):
        return {
            str(key): _jsonable(
                value
            )
            for key, value in dataclasses.asdict(
                obj
            ).items()
        }

    if isinstance(
        obj,
        dict,
    ):
        return {
            str(key): _jsonable(
                value
            )
            for key, value in obj.items()
        }

    if isinstance(
        obj,
        (list, tuple),
    ):
        return [
            _jsonable(
                value
            )
            for value in obj
        ]

    if isinstance(
        obj,
        (set, frozenset),
    ):
        return sorted(
            (
                _jsonable(
                    value
                )
                for value in obj
            ),
            key=lambda value: repr(
                value
            ),
        )

    # Last-resort representation. Logging must never crash the pipeline merely
    # because an unexpected object entered the context.
    return repr(
        obj
    )


def context_hash(
    ctx: SceneContext,
) -> str:
    """Return a deterministic content hash of a SceneContext.

    The hash is deliberately short enough for readable JSONL while retaining
    sufficient entropy for before/after experiment comparisons.
    """

    blob = json.dumps(
        _jsonable(ctx),
        sort_keys=True,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        blob
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Repair evidence
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RepairRecord:
    """Machine-readable evidence for one repair attempt."""

    cycle_id: int
    scene_id: str
    finding_type: str
    mismatch_subtype: str | None
    routed_to: list[str]
    diagnostic_message: str
    pre_repair_context_hash: str
    post_repair_context_hash: str
    outcome: str
    cycles_used: int
    timestamp: str


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class SelfCorrectionReport:
    """Machine-readable final summary of one self-correction run."""

    project: str
    final_pass: bool
    iterations: int
    detected_issues: list[dict[str, Any]]
    repairs: list[dict[str, Any]]
    verification_results: dict[
        str,
        list[dict[str, Any]],
    ]
    findings_by_category: dict[
        str,
        int,
    ]


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return (
        datetime.now(
            timezone.utc
        ).isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


# ``timezone`` is imported separately to keep the timestamp helper explicit.
from datetime import timezone


def _count_iterations(
    ctx: SceneContext,
) -> int:
    """Count actual recorded execution/repair events.

    Prefer explicit repair records plus history entries. This preserves the
    existing evidence model while avoiding the misleading implication that
    every history entry is a repair iteration.
    """

    return len(
        ctx.history
    ) + len(
        ctx.repair_records
    )


def write_self_correction_report(
    ctx: SceneContext,
    final_pass: bool,
) -> Path:
    """Persist the complete machine-readable self-correction report."""

    all_findings: list[
        dict[str, Any]
    ] = []

    for results in (
        ctx.check_results.values()
    ):
        if not isinstance(
            results,
            list,
        ):
            continue

        for finding in results:
            if isinstance(
                finding,
                dict,
            ):
                all_findings.append(
                    dict(
                        finding
                    )
                )

    findings_by_category: dict[
        str,
        int,
    ] = {}

    for finding in all_findings:
        category = str(
            finding.get(
                "category",
                "TECHNICAL",
            )
        )

        findings_by_category[
            category
        ] = (
            findings_by_category.get(
                category,
                0,
            )
            + 1
        )

    project = (
        ctx.project_dir.name
        if ctx.project_dir
        else "unknown"
    )

    report = SelfCorrectionReport(
        project=project,
        final_pass=bool(
            final_pass
        ),
        iterations=_count_iterations(
            ctx
        ),
        detected_issues=all_findings,
        repairs=[
            dict(record)
            for record in ctx.repair_records
            if isinstance(
                record,
                dict,
            )
        ],
        verification_results={
            str(name): list(
                results
            )
            for name, results in (
                ctx.check_results.items()
            )
            if isinstance(
                results,
                list,
            )
        },
        findings_by_category=dict(
            sorted(
                findings_by_category.items()
            )
        ),
    )

    out = (
        ctx.project_dir / "out"
        if ctx.project_dir
        else Path(".")
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        out
        / "self_correction_report.json"
    )

    path.write_text(
        json.dumps(
            dataclasses.asdict(
                report
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """Append-only JSONL experiment logger."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(
            path
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._lock = threading.Lock()

    def log_invocation(
        self,
        *,
        plugin: str,
        input_ctx: SceneContext,
        output_ctx: SceneContext,
        ok: bool,
        diagnostics: str = "",
        duration_s: float = 0.0,
        token_usage: int | None = None,
    ) -> None:
        """Append one immutable plugin invocation record."""

        duration = max(
            0.0,
            float(
                duration_s
            ),
        )

        if token_usage is not None:
            token_usage = max(
                0,
                int(
                    token_usage
                ),
            )

        record = {
            "event": "plugin.invocation",
            "plugin": str(
                plugin
            ),
            "input_context_hash": context_hash(
                input_ctx
            ),
            "output_context_hash": context_hash(
                output_ctx
            ),
            "ok": bool(
                ok
            ),
            "diagnostics": str(
                diagnostics
                or ""
            ),
            "duration_s": round(
                duration,
                4,
            ),
            "token_usage": token_usage,
            "timestamp": _utc_timestamp(),
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
        }

        line = json.dumps(
            record,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

        # A single process may execute multiple verifier/render jobs in
        # parallel. Protect append operations so records do not interleave.
        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    line
                )
                handle.write(
                    "\n"
                )

    def log_repair(
        self,
        record: RepairRecord,
    ) -> None:
        """Append a repair event to the same JSONL evidence stream."""

        payload = {
            "event": "repair",
            **dataclasses.asdict(
                record
            ),
        }

        line = json.dumps(
            _jsonable(
                payload
            ),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    line
                )
                handle.write(
                    "\n"
                )


__all__ = [
    "RepairRecord",
    "SelfCorrectionReport",
    "StructuredLogger",
    "context_hash",
    "write_self_correction_report",
]