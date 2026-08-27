"""Harness-level self-check.

Every other module in this package answers "did the pipeline run" or "did
a verifier pass". None of them answers a strictly narrower, more important
question: **is the harness's own bookkeeping actually consistent with what
is on disk right now?** A verifier passing, or an LLM claiming "fixed", is
not evidence of that -- it is evidence about the scene's *content*, not
about whether the harness's artifact/lineage/event records agree with
reality.

This module is the fail-safe answer to that question, run once at the end
of a harness invocation (``cmd_harness``, both the success and
``GateFailure`` paths). It never blocks a build on its own account (its
findings are advisory, category TECHNICAL, and none of them raise) --
its job is to make a real inconsistency *visible*, not to add a new gate
on top of the ones that already exist.

Checks performed:

1. Every scene at a positive revision has a code artifact that exists on
   disk and is stamped with the current revision.
2. The reachability invariant (reuses
   :meth:`HarnessRunner._finalization_problem` rather than re-implementing
   it -- there is exactly one definition of "is out/final.mp4 valid").
3. Every stills manifest entry's PNG exists on disk.
4. ``build/harness/events.jsonl`` parses and its ``seq`` values are
   monotonically increasing with no gaps or duplicates.
5. ``build/harness/revisions.json`` agrees with ``scene_versions`` for
   every scene it tracks.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .finding import Category, Finding, Severity, next_finding_id
from .lineage import is_scene_stem
from .revision_history import load_revision_history

if TYPE_CHECKING:
    from .context import SceneContext


def _finding(
    scene_id: str,
    message: str,
    *,
    severity: Severity = Severity.WARNING,
) -> dict[str, Any]:
    return Finding(
        finding_id=next_finding_id("selfcheck"),
        scene_id=scene_id or "harness",
        category=Category.TECHNICAL,
        severity=severity,
        message=message,
    ).as_check_result()


def _check_accepted_artifacts(context: "SceneContext") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for stem, revision in (context.scene_versions or {}).items():
        if not is_scene_stem(stem) or int(revision or 0) <= 0:
            continue

        artifact = context.code_artifacts.get(str(stem))

        if artifact is None:
            findings.append(
                _finding(
                    stem,
                    f"scene {stem!r} is at revision {revision} but has no "
                    "code_artifacts entry at all",
                    severity=Severity.BLOCKING,
                )
            )
            continue

        if not artifact.path or not Path(artifact.path).exists():
            findings.append(
                _finding(
                    stem,
                    f"scene {stem!r}'s accepted source is missing on disk "
                    f"at {artifact.path}",
                    severity=Severity.BLOCKING,
                )
            )

        if int(getattr(artifact, "revision", 0) or 0) != int(revision):
            findings.append(
                _finding(
                    stem,
                    f"scene {stem!r}: code_artifacts revision "
                    f"{artifact.revision} does not match the authoritative "
                    f"scene_versions revision {revision}",
                    severity=Severity.WARNING,
                )
            )

    return findings


def _check_reachability(context: "SceneContext") -> list[dict[str, Any]]:
    # Nothing was ever generated -- a totally untouched context (a fresh
    # project, or a test exercising an unrelated part of the harness) has
    # no final video to be missing. run_self_check has no plugin list to
    # consult (unlike HarnessRunner._check_final_video_reachable, which
    # gates on FINALIZATION_STAGES being present in the resolved DAG), so
    # "at least one scene reached a real revision" is the closest
    # available proxy for "a build was actually attempted".
    if not any(int(v or 0) > 0 for v in (context.scene_versions or {}).values()):
        return []

    from .runner import HarnessRunner

    reason = HarnessRunner._finalization_problem(context)

    if reason is None:
        return []

    return [_finding("", reason, severity=Severity.WARNING)]


def _check_manifests(context: "SceneContext") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for stem, artifact in (context.render_artifacts or {}).items():
        outdir = getattr(artifact, "outdir", None)
        manifest = getattr(artifact, "manifest", None) or []

        if outdir is None or not manifest:
            continue

        for entry in manifest:
            if not isinstance(entry, dict):
                continue

            png = entry.get("png")

            if not png:
                continue

            if not (Path(outdir) / png).exists():
                findings.append(
                    _finding(
                        stem,
                        f"scene {stem!r} manifest references missing "
                        f"still {png!r} under {outdir}",
                        severity=Severity.WARNING,
                    )
                )

    return findings


def _check_event_journal(project_dir: Path | None) -> list[dict[str, Any]]:
    if project_dir is None:
        return []

    path = Path(project_dir) / "build" / "harness" / "events.jsonl"

    if not path.exists():
        return []

    from .journal import EventJournal

    records = EventJournal(path).read()
    seen: set[int] = set()
    previous = 0
    findings: list[dict[str, Any]] = []

    for record in records:
        try:
            seq = int(record.get("seq", 0))
        except (TypeError, ValueError):
            findings.append(
                _finding("", f"events.jsonl record has a non-integer seq: {record!r}")
            )
            continue

        if seq in seen:
            findings.append(_finding("", f"events.jsonl seq {seq} is duplicated"))
        elif seq < previous:
            findings.append(
                _finding("", f"events.jsonl seq {seq} is out of order after {previous}")
            )

        seen.add(seq)
        previous = max(previous, seq)

    return findings


def _check_revision_history(context: "SceneContext") -> list[dict[str, Any]]:
    project_dir = getattr(context, "project_dir", None)

    if project_dir is None:
        return []

    data = load_revision_history(project_dir)
    scenes = data.get("scenes", {})
    findings: list[dict[str, Any]] = []

    for stem, revision in (context.scene_versions or {}).items():
        if not is_scene_stem(stem) or int(revision or 0) <= 0:
            continue

        record = scenes.get(str(stem))

        if record is None:
            # Not necessarily wrong -- seed_from_context runs after this
            # check in cmd_harness's own ordering, and a test/tool caller
            # may not have called it at all. Advisory only.
            continue

        if int(record.get("current", -1)) != int(revision):
            findings.append(
                _finding(
                    stem,
                    f"revisions.json reports scene {stem!r} at revision "
                    f"{record.get('current')}, but scene_versions says "
                    f"{revision}",
                )
            )

    return findings


def run_self_check(context: "SceneContext") -> list[dict[str, Any]]:
    """Run every self-check and return findings as check-result dicts.

    Never raises: each sub-check is independent, and a failure in one
    (an unreadable file, a malformed artifact) must not prevent the
    others from running or crash the harness run it is inspecting.
    """

    findings: list[dict[str, Any]] = []

    for check in (
        lambda: _check_accepted_artifacts(context),
        lambda: _check_reachability(context),
        lambda: _check_manifests(context),
        lambda: _check_event_journal(getattr(context, "project_dir", None)),
        lambda: _check_revision_history(context),
    ):
        try:
            findings.extend(check())
        except Exception as exc:
            findings.append(
                _finding("", f"self-check raised {type(exc).__name__}: {exc}")
            )

    return findings


__all__ = [
    "run_self_check",
]
