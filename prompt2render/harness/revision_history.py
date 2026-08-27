"""Persisted per-scene revision history.

``SceneContext.scene_versions`` (see :mod:`lineage`) is the authoritative
*current* revision, but it lives only in memory -- it does not survive a
process restart, and it records no more than an integer. There is no
answer on disk to "what changed between revision 1 and revision 2 of scene
07, and why", short of grepping ``repair_log.jsonl`` for matching
``candidate_revision`` values.

This module is the durable counterpart: one JSON file per project,
``build/harness/revisions.json``, recording every repair attempt for every
scene -- not just the accepted ones, so a rejected attempt's reasoning is
not lost the moment ``workspace.discard`` removes its sidecar files.

Deliberately kept separate from :mod:`lineage`: that module's own docstring
states its design discipline plainly -- "No plugin imports and no side
effects beyond mutating the ``SceneContext`` fields it is explicitly asked
to mutate" (with one documented exception). Adding file I/O there would
break that discipline for every caller, not just the ones that want
persisted history.

Automatic migration: :func:`seed_from_context` populates a synthetic
revision-1 entry for any scene that has a positive ``scene_versions`` value
but no history yet -- an existing project gains history from its current
state rather than needing anything hand-edited.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .context import SceneContext

REVISION_HISTORY_SCHEMA_VERSION = "1.0"


@dataclass
class RevisionEntry:
    """One repair attempt's outcome for one scene."""

    revision: int
    parent_revision: int
    timestamp: str
    reason: str
    decision: str
    repair_contract: dict[str, Any] = field(default_factory=dict)
    finding_diff: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _path(project_dir: Path) -> Path:
    return Path(project_dir) / "build" / "harness" / "revisions.json"


def _empty() -> dict[str, Any]:
    return {"schema_version": REVISION_HISTORY_SCHEMA_VERSION, "scenes": {}}


def load_revision_history(project_dir: Path | None) -> dict[str, Any]:
    """Read ``revisions.json``. Never raises: a missing or corrupt file
    degrades to an empty structure, matching ``experience.load_experience``'s
    fail-safe posture -- history is explanatory, not load-bearing."""

    if project_dir is None:
        return _empty()

    path = _path(project_dir)

    if not path.exists():
        return _empty()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, dict) and isinstance(data.get("scenes"), dict):
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass

    return _empty()


def save_revision_history(project_dir: Path, data: dict[str, Any]) -> None:
    """Write ``revisions.json``. Never raises."""

    try:
        path = _path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def record_revision(
    project_dir: Path | None,
    stem: str,
    entry: RevisionEntry,
    *,
    accepted: bool,
) -> None:
    """Append one attempt to a scene's persisted history. Never raises.

    ``accepted`` advances the scene's ``current``/``accepted`` pointer;
    a rejected attempt is still appended to ``revisions`` (the audit trail
    the brief asks for -- "what was attempted" survives even when nothing
    changed), but does not move the pointer.
    """

    if project_dir is None:
        return

    try:
        data = load_revision_history(project_dir)
        scenes = data.setdefault("scenes", {})
        record = scenes.setdefault(
            str(stem), {"current": 0, "accepted": 0, "revisions": []}
        )

        record["revisions"].append(entry.to_dict())
        record["current"] = int(entry.revision)

        if accepted:
            record["accepted"] = int(entry.revision)

        save_revision_history(project_dir, data)
    except Exception:
        # Never let a persistence failure derail a repair cycle.
        return


def seed_from_context(project_dir: Path | None, context: "SceneContext") -> None:
    """Automatic migration for a project with no ``revisions.json`` yet.

    For every scene whose in-memory ``scene_versions`` is already positive
    (i.e. it has been generated/accepted at least once, in this run or a
    prior one whose lineage survived some other way) but which has no
    history entry, seed a synthetic revision-1 record. No manual project
    editing is required for existing projects to gain history going
    forward.
    """

    if project_dir is None:
        return

    try:
        data = load_revision_history(project_dir)
        scenes = data.setdefault("scenes", {})
        changed = False

        for stem, revision in (context.scene_versions or {}).items():
            revision = int(revision or 0)

            if revision <= 0 or str(stem) in scenes:
                continue

            scenes[str(stem)] = {
                "current": revision,
                "accepted": revision,
                "revisions": [
                    RevisionEntry(
                        revision=revision,
                        parent_revision=0,
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        reason="seeded: pre-existing revision at first harness run "
                        "with revision_history enabled",
                        decision="accepted",
                    ).to_dict()
                ],
            }
            changed = True

        if changed:
            save_revision_history(project_dir, data)
    except Exception:
        return


__all__ = [
    "REVISION_HISTORY_SCHEMA_VERSION",
    "RevisionEntry",
    "load_revision_history",
    "record_revision",
    "save_revision_history",
    "seed_from_context",
]
