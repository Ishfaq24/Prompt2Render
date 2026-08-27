"""Durable, append-only build event journal.

``events.py`` is the *live* in-process bus: synchronous, strict, and gone the
moment the process exits. Nothing about the harness currently survives a
crash or a later "why did this happen" question except the plugin-invocation
log (``logging_.StructuredLogger``) and the repair decision log
(``repair_controller._write``) -- both are real, but neither is a single
ordered timeline of what happened to *each scene*, and neither is meant to
be replayed.

This module is the durable counterpart -- the Prompt2Render analogue of
DeepSeek Harness's ``session/event`` stream. One :class:`EventJournal` per
project run appends one JSON line per event to
``<project>/build/harness/events.jsonl``. It is deliberately a separate file
from ``log.jsonl``/``repair_log.jsonl`` rather than a reformatting of either:
those two are plugin- and repair-cycle-scoped; this one is scene-lifecycle
scoped and is what :mod:`lifecycle`, :mod:`selfcheck`, and the ``events``/
``scene-history`` CLI commands read back.

Design constraints, in order of importance:

1. **Never raises.** Matches the existing precedent set by
   ``quality_report.write_quality_report`` and
   ``repair_controller.RepairController._write`` -- instrumentation must not
   change pipeline behavior. A journal write failure is swallowed, not
   propagated.
2. **Append-only, one JSON object per line**, thread-safe (multiple verifier
   workers may log concurrently, same as ``StructuredLogger``).
3. **No binary payloads.** ``payload`` fields must be small and JSON-native
   (paths as strings, counts, short strings). This mirrors the module's own
   documented intent: "store references to artifacts instead."
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: The complete durable event vocabulary. Deliberately broader than
#: ``EventBus.VALID_EVENTS`` (which only covers the live control-flow
#: signals a subscriber reacts to *during* a run) -- this is the full
#: lifecycle a human or a future UI needs to reconstruct *after* a run.
VALID_EVENT_TYPES = frozenset(
    {
        "build.started",
        "build.completed",
        "build.failed",
        "scene.planned",
        "scene.generated",
        "scene.render.started",
        "scene.render.completed",
        "scene.verify.started",
        "scene.verify.completed",
        "scene.repair.started",
        "scene.repair.candidate",
        "scene.repair.rendered",
        "scene.repair.verified",
        "scene.accepted",
        "scene.rejected",
        "scene.rollback",
        "scene.state",
        "cache.hit",
        "cache.invalidated",
        "harness.selfcheck",
    }
)

#: Statuses a build event may carry. Kept small and closed -- this is a
#: machine-read field, not free text (``payload`` is for free text).
VALID_STATUSES = frozenset({"ok", "fail", "pending", "skip"})


def _utc_timestamp() -> str:
    """Second-resolution UTC ISO-8601 timestamp, ``Z``-suffixed.

    A local, tiny re-implementation rather than importing
    ``logging_._utc_timestamp`` -- that name is underscore-prefixed and no
    other harness module reaches across a package boundary for a private
    helper (confirmed: nothing does). Keeping the journal's serialization
    self-contained also means it can be reused outside the harness (e.g. by
    a future CLI) without pulling in ``logging_``'s heavier surface.
    """

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _json_safe(value: Any) -> Any:
    """Best-effort conversion of a payload value into JSON-native data.

    Deliberately shallow and forgiving -- callers are expected to pass
    already-simple values (strings, numbers, small dicts/lists of the
    same). Anything that would otherwise blow up ``json.dumps`` (a
    ``Path``, an ``Enum``, a dataclass) is downgraded to a string rather
    than raising, so a journal write is never the reason a repair cycle
    fails.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]

    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        # Enum-shaped (str, Enum) members without importing every enum type
        # this module has no business depending on.
        return value.value

    return str(value)


class EventJournal:
    """Append-only durable event log for one project's harness runs.

    Multiple :class:`EventJournal` instances pointed at the same path are
    safe to use concurrently within one process (each holds its own lock,
    but the underlying ``open(..., "a")`` append is itself atomic for the
    small writes this module produces); across processes, JSONL append is
    the same safety model ``StructuredLogger`` already relies on.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = self._recover_seq()

    def _recover_seq(self) -> int:
        """Resume the monotonic sequence counter after a process restart.

        Without this, a fresh process would restart ``seq`` at 0 and
        produce duplicate sequence numbers in an existing journal --
        exactly the kind of silent corruption :mod:`selfcheck` (P1-3) is
        meant to catch, so the journal must not introduce it itself.
        """

        if not self.path.exists():
            return 0

        highest = 0

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        highest = max(highest, int(record.get("seq", 0)))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
        except OSError:
            return 0

        return highest

    def append(
        self,
        *,
        event_type: str,
        project: str,
        scene_id: str,
        revision: int = 0,
        status: str = "ok",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Append one durable event. Returns the record, or ``None`` on failure.

        Never raises -- see the module docstring. A malformed ``event_type``
        or ``status`` is itself recorded as a best-effort diagnostic rather
        than silently dropped, since a caller passing a bad event type is
        exactly the kind of bug this journal exists to make visible.
        """

        try:
            event_type = str(event_type).strip()
            status = str(status).strip().lower() or "ok"

            if event_type not in VALID_EVENT_TYPES:
                # Do not raise -- but do not pretend the event was valid
                # either. Record it under a reserved type so a bad call
                # site is discoverable without ever crashing the run that
                # is trying to log its own failure.
                payload = dict(payload or {})
                payload["_invalid_event_type"] = event_type
                event_type = "harness.selfcheck"

            if status not in VALID_STATUSES:
                status = "ok"

            with self._lock:
                self._seq += 1
                seq = self._seq

                record = {
                    "event_id": f"{seq:08d}-{uuid.uuid4().hex[:8]}",
                    "seq": seq,
                    "timestamp": _utc_timestamp(),
                    "project": str(project),
                    "scene_id": str(scene_id),
                    "event_type": event_type,
                    "revision": int(revision),
                    "status": status,
                    "payload": _json_safe(payload or {}),
                }

                line = json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )

                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")

                return record
        except Exception:
            # Instrumentation must never be the reason a build fails.
            return None

    def read(
        self,
        *,
        scene_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read back events, optionally filtered, oldest first.

        ``limit`` keeps the *last* N matching events (most useful for a
        CLI tail), not the first N -- matching how ``--limit`` reads in
        every other Prompt2Render command that takes one.
        """

        if not self.path.exists():
            return []

        records: list[dict[str, Any]] = []

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if scene_id is not None and record.get("scene_id") != str(scene_id):
                        continue

                    if event_type is not None and record.get("event_type") != event_type:
                        continue

                    records.append(record)
        except OSError:
            return []

        if limit is not None and limit > 0:
            records = records[-limit:]

        return records


# ---------------------------------------------------------------------------
# Replay (P2-2)
# ---------------------------------------------------------------------------

#: Event types that mark a candidate's final outcome for one scene.
_DECISION_EVENT_TYPES = frozenset({"scene.accepted", "scene.rejected", "scene.rollback"})


@dataclass
class SceneReplayState:
    """One scene's lifecycle, reconstructed purely from durable events."""

    stem: str
    state: str | None = None
    current_revision: int = 0
    accepted_revision: int = 0
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stem": self.stem,
            "state": self.state,
            "current_revision": self.current_revision,
            "accepted_revision": self.accepted_revision,
            "decisions": list(self.decisions),
        }


@dataclass
class ReplayState:
    """The harness's own state, reconstructed purely from durable events.

    "Purely" is the point: nothing here reads ``SceneContext``,
    ``repair_log.jsonl``, or ``revisions.json`` -- if this disagrees with
    any of those, either the journal is missing events or one of the
    other artifacts drifted, and that disagreement is itself the kind of
    fact :mod:`selfcheck` exists to catch.
    """

    scenes: dict[str, SceneReplayState] = field(default_factory=dict)
    build_status: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes": {stem: scene.to_dict() for stem, scene in self.scenes.items()},
            "build_status": self.build_status,
        }


def replay(events: list[dict[str, Any]]) -> ReplayState:
    """Reconstruct per-scene lifecycle state and decision history from a
    plain list of event dicts (as returned by :meth:`EventJournal.read`).

    Processes events in ``seq`` order regardless of the order they were
    passed in -- a caller that filtered or otherwise reordered a
    :meth:`EventJournal.read` result still replays correctly.
    """

    result = ReplayState()

    for record in sorted(events, key=lambda r: int(r.get("seq", 0) or 0)):
        event_type = str(record.get("event_type", ""))
        stem = str(record.get("scene_id", ""))

        if event_type in ("build.started", "build.completed", "build.failed"):
            result.build_status = {
                "build.started": "running",
                "build.completed": "ok",
                "build.failed": "fail",
            }[event_type]
            continue

        if not stem or stem == "__all__":
            continue

        scene = result.scenes.setdefault(stem, SceneReplayState(stem=stem))

        try:
            revision = int(record.get("revision", 0) or 0)
        except (TypeError, ValueError):
            revision = 0

        if revision > scene.current_revision:
            scene.current_revision = revision

        if event_type == "scene.state":
            payload = record.get("payload") or {}
            to_state = payload.get("to")

            if to_state:
                scene.state = str(to_state)

        elif event_type in _DECISION_EVENT_TYPES:
            payload = record.get("payload") or {}
            is_dry_run = bool(payload.get("dry_run"))

            scene.decisions.append(
                {
                    "seq": record.get("seq"),
                    "timestamp": record.get("timestamp"),
                    "event_type": event_type,
                    "decision": payload.get("decision"),
                    "reason": payload.get("reason"),
                    "dry_run": is_dry_run,
                }
            )

            if event_type == "scene.accepted" and not is_dry_run:
                scene.accepted_revision = revision

    return result


__all__ = [
    "EventJournal",
    "ReplayState",
    "SceneReplayState",
    "VALID_EVENT_TYPES",
    "VALID_STATUSES",
    "replay",
]
