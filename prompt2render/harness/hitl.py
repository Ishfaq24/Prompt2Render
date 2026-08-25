"""Shared Human-in-the-Loop (HITL) support -- Tier 4.

Closes part of SS14's documented duplication ("HITL file reading —
feedback_hitl and hitl_status_sets... both parse hitl_feedback.json
independently, for different purposes") by giving every consumer --
``feedback_hitl``, ``renderer_manim``'s original ``hitl_status_sets``, and
this tier's new ``verifier_hitl_approval`` -- one shared parser instead of a
third independent one.

:func:`read_feedback` is the single source of truth for the on-disk shape
(SS18): ``{"<stem>": {"status": "accept"|"reject"|..., "reason": "..."}}``.
Malformed JSON / a missing file / the wrong top-level type all degrade to
``{}`` -- matches both pre-existing consumers' fail-open behavior exactly,
verified by keeping their own tests green after delegating to this module.

Tier 4 also adds :func:`write_review_draft`, for ``HUMAN_ON_FAILURE`` mode
(see ``prompt2render.py``'s ``cmd_harness``): on a hard ``GateFailure``, it
drafts ``hitl_review_needed.json`` listing exactly which stems/reasons need
a human's attention, pre-filled from the failure's own findings -- so the
human doesn't have to hand-author ``reject`` entries from scratch by reading
logs, which is the *only* documented workflow today (``HITL_WORKFLOW.md``).
Deliberately a **separate file** from ``hitl_feedback.json``, using a
distinct ``"needs_review"`` status that ``feedback_hitl``'s own parser
does not treat as actionable (only ``"reject"`` triggers a repair route) --
this never silently overwrites a human's in-progress ``hitl_feedback.json``,
and never auto-triggers a repair cycle without a human actually reviewing it
first, preserving ``HITL_WORKFLOW.md``'s existing "review, then rename/edit"
step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_feedback(
    project_dir: Path | None,
) -> dict[str, dict[str, Any]]:
    """Raw ``hitl_feedback.json`` contents, defensively parsed.

    Returns ``{}`` on any failure (missing file, malformed JSON, wrong
    top-level shape, a non-dict entry for some stem) -- never raises.
    """

    if project_dir is None:
        return {}

    path = Path(project_dir) / "hitl_feedback.json"

    if not path.exists():
        return {}

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        str(stem): entry
        for stem, entry in data.items()
        if isinstance(entry, dict)
    }


def status_sets(
    project_dir: Path | None,
) -> tuple[set[str], set[str]]:
    """``(rejected, locked)`` stems.

    Same contract as ``renderer_manim``'s original ``hitl_status_sets``
    (now a thin wrapper over this function) -- ``"reject"`` forces a fresh
    regenerate+rerender, ``"accept"`` is a hard lock against unrelated
    staleness heuristics ever sweeping the stem back in.
    """

    rejected: set[str] = set()
    locked: set[str] = set()

    for stem, entry in read_feedback(project_dir).items():
        status = entry.get("status")

        if status == "reject":
            rejected.add(stem)
        elif status == "accept":
            locked.add(stem)

    return rejected, locked


def write_review_draft(
    project_dir: Path | None,
    findings: list[dict[str, Any]],
) -> Path | None:
    """Draft ``hitl_review_needed.json`` from a hard gate failure's findings.

    Groups every distinct diagnostic message by stem (a stem can have
    failed more than one verifier) and writes a draft shaped like
    ``hitl_feedback.json`` itself, but with ``status: "needs_review"`` so it
    is inert to every existing consumer until a human reviews and promotes
    it. Never raises; returns ``None`` when ``project_dir`` is unset or
    there is nothing worth drafting (no findings carry a stem).
    """

    if project_dir is None:
        return None

    by_stem: dict[str, list[str]] = {}

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        stem = str(
            finding.get("stem") or finding.get("scene_id") or ""
        ).strip()

        if not stem:
            continue

        detail = str(
            finding.get("detail") or finding.get("message") or ""
        ).strip()

        if not detail:
            detail = "Needs human review."

        reasons = by_stem.setdefault(stem, [])

        if detail not in reasons:
            reasons.append(detail)

    if not by_stem:
        return None

    draft = {
        stem: {
            "status": "needs_review",
            "reason": " | ".join(reasons),
        }
        for stem, reasons in sorted(by_stem.items())
    }

    try:
        path = Path(project_dir) / "hitl_review_needed.json"
        path.write_text(
            json.dumps(draft, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


__all__ = [
    "read_feedback",
    "status_sets",
    "write_review_draft",
]
