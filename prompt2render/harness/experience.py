"""Cross-run experience memory -- Tier 3 Phase 15.

The audit's own grounding (SS3, "State ownership" gaps: "there is no field
for... cross-run experience/memory (``repair_context`` is per-run and is
actively *deleted* on success, ``runner.py:744-748``)"). Confirmed further
by reading ``logging_.write_self_correction_report``: it ``path.write_text``
-overwrites ``out/self_correction_report.json`` every single run, and
nothing anywhere reads that file back in on a later run. A project that
hits the same class of problem across two separate builds starts the
second build's repair loop with zero memory of the first ever having
happened.

This module is the durable half: an append-only, per-project experience
log (``build/harness/experience_memory.jsonl``, sibling to
``repair_router``'s own per-run ``repair_log.jsonl``) that survives across
builds, plus a pure summarizer surfacing which finding_type/
mismatch_subtype combinations recur most often for this specific project.

Deliberately **not** wired into any live prompt or repair decision yet --
the same "accumulate first, decide what to do with it later" discipline
Phase 10 established for ``quality_report.py`` (Phase 13 only designed the
real scoring formula once the aggregation existed to design it against). A
future phase can feed :func:`summarize_recurring`'s output into
``planner_llm``/``generator_code``'s repair prompts once this module exists
to feed from -- this phase's job is making the memory durable and
inspectable, not yet acting on it.

Deliberately excludes ``scene_id``/stem from what it persists: a stem
identifier is per-run arbitrary noise (section numbering shifts across
script edits), not a portable insight across builds. ``finding_type``/
``mismatch_subtype`` are the portable signal -- "this project's storyboard
tends to trigger ``spatial_conflict``/overlap" survives a section being
renumbered; "stem 03 had a problem" does not.
"""

from __future__ import annotations

import dataclasses
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Experience record schema version.
EXPERIENCE_SCHEMA_VERSION = "1.0"


@dataclass
class ExperienceRecord:
    """One resolved-or-exhausted repair episode, durable across runs."""

    finding_type: str
    mismatch_subtype: str
    routed_to: list[str]
    outcome: str
    cycles_used: int
    diagnostic_message: str
    recorded_at: str
    schema_version: str = EXPERIENCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ExperienceRecord":
        return ExperienceRecord(
            finding_type=str(data.get("finding_type", "")),
            mismatch_subtype=str(data.get("mismatch_subtype", "") or ""),
            routed_to=[str(t) for t in (data.get("routed_to") or [])],
            outcome=str(data.get("outcome", "")),
            cycles_used=int(data.get("cycles_used", 0) or 0),
            diagnostic_message=str(data.get("diagnostic_message", "") or ""),
            recorded_at=str(data.get("recorded_at", "")),
            schema_version=str(
                data.get("schema_version", EXPERIENCE_SCHEMA_VERSION)
            ),
        )


def from_repair_records(
    repair_records: list[dict[str, Any]],
    *,
    recorded_at: str | None = None,
) -> list[ExperienceRecord]:
    """Convert one run's ``ctx.repair_records`` into durable records.

    Pure function -- no file I/O, no ``SceneContext``. Skips malformed
    entries defensively rather than raising: ``repair_records`` is a plain,
    unvalidated ``list[dict]`` written by ``repair_router``, the same
    defensive posture ``write_self_correction_report`` already applies to
    it.
    """

    timestamp = recorded_at or time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    )

    records: list[ExperienceRecord] = []

    for entry in repair_records:
        if not isinstance(entry, dict):
            continue

        finding_type = entry.get("finding_type")

        if not finding_type:
            continue

        records.append(
            ExperienceRecord(
                finding_type=str(finding_type),
                mismatch_subtype=str(
                    entry.get("mismatch_subtype", "") or ""
                ),
                routed_to=[
                    str(t) for t in (entry.get("routed_to") or [])
                ],
                outcome=str(entry.get("outcome", "")),
                cycles_used=int(entry.get("cycles_used", 0) or 0),
                diagnostic_message=str(
                    entry.get("diagnostic_message", "") or ""
                ),
                recorded_at=timestamp,
            )
        )

    return records


def from_decision_records(
    decisions: "list[Any]",
) -> list[ExperienceRecord]:
    """Convert the CURRENT repair controller's decision log into durable records.

    Bug fix: :func:`from_repair_records` was always fed ``ctx.repair_records``,
    a list only the *old* router-owned repair path ever populated. Since
    :class:`~prompt2render.harness.repair_controller.RepairController`
    replaced that path, ``ctx.repair_records`` has stayed permanently
    empty and no project has ever produced a real
    ``experience_memory.jsonl``. The authoritative record of what actually
    happened during repair is
    ``RepairController.decisions`` (``list[RepairDecisionRecord]``); this
    is the adapter for that shape, kept separate from
    :func:`from_repair_records` rather than changing its contract, since
    that function has its own callers/tests built against the older
    dict shape and may still see it from historical/replayed data.

    Accepts ``RepairDecisionRecord`` instances or their ``.to_dict()``
    dicts, so a caller reading decisions back from ``repair_log.jsonl``
    can reuse this without re-inflating dataclasses first.
    """

    records: list[ExperienceRecord] = []

    for entry in decisions:
        data = entry.to_dict() if hasattr(entry, "to_dict") else entry

        if not isinstance(data, dict):
            continue

        finding_type = data.get("trigger_finding_type")

        if not finding_type:
            continue

        triggering = data.get("triggering_findings") or []
        first = triggering[0] if triggering and isinstance(triggering[0], dict) else {}

        records.append(
            ExperienceRecord(
                finding_type=str(finding_type),
                mismatch_subtype=str(first.get("mismatch_subtype", "") or ""),
                routed_to=[str(t) for t in (data.get("routed_to") or [])],
                outcome=str(data.get("decision", "")),
                # Each RepairDecisionRecord is exactly one repair cycle --
                # unlike the old router shape, there is no separate
                # per-finding-type cumulative counter to report instead.
                cycles_used=1,
                diagnostic_message=str(data.get("rejection_reason", "") or ""),
                recorded_at=str(
                    data.get("timestamp", "")
                ) or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
        )

    return records


def _experience_path(project_dir: Path) -> Path:
    return Path(project_dir) / "build" / "harness" / "experience_memory.jsonl"


def load_experience(
    project_dir: Path | None,
) -> list[ExperienceRecord]:
    """All durable experience records for this project, oldest first.

    Never raises: a missing or corrupt file degrades to ``[]`` -- experience
    memory is advisory context, not a load-bearing dependency for any build.
    """

    if project_dir is None:
        return []

    path = _experience_path(Path(project_dir))

    if not path.exists():
        return []

    records: list[ExperienceRecord] = []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            records.append(ExperienceRecord.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    return records


def append_experience(
    project_dir: Path | None,
    records: list[ExperienceRecord],
) -> Path | None:
    """Append this run's records to the project's durable experience log.

    Append-only by design -- accumulation across runs is the entire point,
    unlike ``self_correction_report.json``'s per-run overwrite. Never
    raises: a logging bug here must not mask the real outcome of a harness
    run, same posture as ``quality_report.write_quality_report``.
    """

    if project_dir is None or not records:
        return None

    try:
        path = _experience_path(Path(project_dir))
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(
                    json.dumps(record.to_dict(), sort_keys=True) + "\n"
                )

        return path
    except Exception:
        return None


def summarize_recurring(
    records: list[ExperienceRecord],
) -> list[dict[str, Any]]:
    """Which ``(finding_type, mismatch_subtype)`` pairs recur most often.

    Pure. Most-frequent first. A pair seen only once is not "recurring" and
    is excluded -- surfacing every one-off would just relocate the noise
    ``self_correction_report.json`` already produces per-run, not add
    anything a reader couldn't already see there.
    """

    counter: Counter[tuple[str, str]] = Counter(
        (record.finding_type, record.mismatch_subtype)
        for record in records
    )

    return [
        {
            "finding_type": finding_type,
            "mismatch_subtype": mismatch_subtype,
            "occurrences": occurrences,
        }
        for (finding_type, mismatch_subtype), occurrences in counter.most_common()
        if occurrences > 1
    ]


__all__ = [
    "EXPERIENCE_SCHEMA_VERSION",
    "ExperienceRecord",
    "append_experience",
    "from_decision_records",
    "from_repair_records",
    "load_experience",
    "summarize_recurring",
]
