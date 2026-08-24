"""Pedagogical quality-control stages for the Prompt2Render harness.

Pipeline:

    scene_plan
        ↓
    PlannerPedagogyPlugin
        ↓
    pedagogy_review
        ↓
    ReviserScriptPlugin
        ↓
    pedagogy_review (updated)
        ↓
    VerifierPedagogyPlugin
        ↓
    pedagogy_verified / check_results

The stage is intentionally deterministic at the orchestration layer:
the pedagogy module decides WHAT is wrong and HOW to revise;
this plugin controls provenance, iteration limits, invariants, and gates.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..context import SceneContext, ScenePlanEntry
from ..plugin import Plugin
from ... import pedagogy
from ...project import parse_script


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARNESS_DIR = "build/harness"
PROVENANCE_DIR = "build/harness/provenance"

REVIEW_FILE = "pedagogy_review.json"
HISTORY_FILE = "pedagogy_history.json"

DEFAULT_MAX_REVISIONS = 2


# ---------------------------------------------------------------------------
# Small internal data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RevisionRecord:
    """Immutable record of one pedagogical revision cycle."""

    cycle: int
    label: str
    changed: bool
    passed: bool
    score: float | int
    issue_count: int
    blocking_issue_count: int


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _harness_dir(project_dir: Path) -> Path:
    path = project_dir / HARNESS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _provenance_dir(project_dir: Path) -> Path:
    path = project_dir / PROVENANCE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write JSON so an interrupted run does not corrupt artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def _save_review(project_dir: Path, review: dict[str, Any]) -> None:
    """Persist the current pedagogical review."""

    _atomic_write_json(
        _harness_dir(project_dir) / REVIEW_FILE,
        review,
    )


def _save_history(
    project_dir: Path,
    history: list[RevisionRecord],
) -> None:
    """Persist the complete revision history."""

    _atomic_write_json(
        _harness_dir(project_dir) / HISTORY_FILE,
        [asdict(item) for item in history],
    )


def _ensure_original_script(context: SceneContext) -> Path:
    """Preserve the exact initial script once."""

    provenance = _provenance_dir(context.project_dir)
    original = provenance / "script.original.md"

    if not original.exists():
        shutil.copyfile(context.prompt, original)

    return original


def _save_revision_snapshot(
    context: SceneContext,
    cycle: int,
) -> Path:
    """Save an immutable snapshot of the script after a revision."""

    provenance = _provenance_dir(context.project_dir)

    target = provenance / f"script.revision_{cycle:02d}.md"

    shutil.copyfile(context.prompt, target)

    return target


# ---------------------------------------------------------------------------
# Review helpers
# ---------------------------------------------------------------------------

def _normalise_review(review: Any) -> dict[str, Any]:
    """Ensure the harness always works with a predictable review object."""

    if not isinstance(review, dict):
        return {
            "pass": False,
            "score": 0,
            "profile": "standard",
            "summary": "Pedagogy review returned an invalid result.",
            "issues": [
                {
                    "severity": "blocking",
                    "type": "invalid_review",
                    "message": "Pedagogy reviewer did not return a dictionary.",
                }
            ],
        }

    review.setdefault("pass", False)
    review.setdefault("score", 0)
    review.setdefault("profile", "standard")
    review.setdefault("summary", "")
    review.setdefault("issues", [])

    if not isinstance(review["issues"], list):
        review["issues"] = [
            {
                "severity": "blocking",
                "type": "invalid_issues",
                "message": "Pedagogy review contains an invalid issues field.",
            }
        ]
        review["pass"] = False

    return review


def _blocking_issues(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Return pedagogically blocking issues only."""

    issues = review.get("issues", [])

    return [
        issue
        for issue in issues
        if isinstance(issue, dict)
        and issue.get("severity") == "blocking"
    ]


def _review_passed(review: dict[str, Any]) -> bool:
    """Centralised quality-gate decision."""

    review = _normalise_review(review)

    return bool(
        review.get("pass", False)
        and not _blocking_issues(review)
    )


def _review_signature(review: dict[str, Any]) -> tuple[Any, ...]:
    """Create a stable signature useful for detecting unchanged reviews."""

    issues = review.get("issues", [])

    issue_signature = tuple(
        (
            issue.get("severity"),
            issue.get("type"),
            issue.get("message"),
        )
        for issue in issues
        if isinstance(issue, dict)
    )

    return (
        bool(review.get("pass", False)),
        review.get("score", 0),
        review.get("profile", "standard"),
        review.get("summary", ""),
        issue_signature,
    )


# ---------------------------------------------------------------------------
# Scene-plan helpers
# ---------------------------------------------------------------------------

def _refresh_plan(context: SceneContext) -> None:
    """Rebuild the scene plan from the current canonical script."""

    script = parse_script(context.prompt)

    context.scene_plan = [
        ScenePlanEntry(
            index=section.index,
            stem=section.stem,
            title=section.title,
            anim=section.anim,
            narration_text=section.narration,
        )
        for section in script.sections
    ]


def _script_signature(context: SceneContext) -> tuple[Any, ...]:
    """Return a lightweight signature of the current scene structure."""

    script = parse_script(context.prompt)

    return tuple(
        (
            section.index,
            section.stem,
            section.title,
            section.anim,
            section.narration,
        )
        for section in script.sections
    )


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class PlannerPedagogyPlugin(Plugin):
    """Run the initial pedagogical analysis."""

    name = "planner_pedagogy"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["pedagogy_review"]

    def run(self, context: SceneContext) -> SceneContext:
        _ensure_original_script(context)

        script = parse_script(context.prompt)

        review = _normalise_review(
            pedagogy.review_script(script)
        )

        context.pedagogy_review = review

        _save_review(
            context.project_dir,
            {
                **review,
                "revision_cycle": 0,
                "stage": self.name,
            },
        )

        return context


# ---------------------------------------------------------------------------
# Reviser
# ---------------------------------------------------------------------------

class ReviserScriptPlugin(Plugin):
    """Iteratively repair pedagogical defects until the quality gate passes."""

    name = "reviser_script"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "pedagogy_review"]

    def declare_effects(self) -> list[str]:
        # The reviser mutates the canonical script, scene plan, and review in
        # place. Publish a separate boundary marker rather than claiming those
        # fields as effects; the loader intentionally rejects read/write
        # overlaps and duplicate artifact ownership.
        return ["script_revision"]

    def _max_revisions(self) -> int:
        try:
            value = int(
                self.config.get(
                    "max_revisions",
                    DEFAULT_MAX_REVISIONS,
                )
            )
        except (TypeError, ValueError):
            value = DEFAULT_MAX_REVISIONS

        return max(0, value)

    def run(self, context: SceneContext) -> SceneContext:
        _ensure_original_script(context)

        script = parse_script(context.prompt)
        review = _normalise_review(context.pedagogy_review)

        max_revisions = self._max_revisions()

        history: list[RevisionRecord] = []

        previous_script_signature = _script_signature(context)
        previous_review_signature = _review_signature(review)

        # ---------------------------------------------------------------
        # No revision required
        # ---------------------------------------------------------------

        if _review_passed(review):
            _refresh_plan(context)
            context.pedagogy_review = review
            context.script_revision += 1
            _save_history(context.project_dir, history)
            return context

        # ---------------------------------------------------------------
        # Self-correction loop
        # ---------------------------------------------------------------

        for cycle in range(1, max_revisions + 1):

            before_text = context.prompt.read_text(
                encoding="utf-8"
            )

            before_script_signature = previous_script_signature

            revised_script, revision_meta = pedagogy.revise_script(
                context.project_dir,
                script,
                review,
                label=f"pedagogy revision {cycle}",
            )

            after_text = context.prompt.read_text(
                encoding="utf-8"
            )

            changed = before_text != after_text

            # -----------------------------------------------------------
            # Detect a broken/non-progressing revision
            # -----------------------------------------------------------

            if not changed:
                history.append(
                    RevisionRecord(
                        cycle=cycle,
                        label=f"pedagogy revision {cycle}",
                        changed=False,
                        passed=False,
                        score=review.get("score", 0),
                        issue_count=len(review.get("issues", [])),
                        blocking_issue_count=len(
                            _blocking_issues(review)
                        ),
                    )
                )

                break

            # -----------------------------------------------------------
            # Preserve revision provenance
            # -----------------------------------------------------------

            _save_revision_snapshot(
                context,
                cycle,
            )

            # -----------------------------------------------------------
            # Re-parse canonical script from disk.
            #
            # This is important: the file is the source of truth, not
            # whatever object the reviser happened to return.
            # -----------------------------------------------------------

            script = parse_script(context.prompt)

            current_script_signature = _script_signature(context)

            # If the returned script and canonical file disagree,
            # trust the canonical file and record the discrepancy.
            if current_script_signature == before_script_signature:
                revision_meta = {
                    **(
                        revision_meta
                        if isinstance(revision_meta, dict)
                        else {}
                    ),
                    "warning": (
                        "Revision changed the file but produced no "
                        "observable structural change after parsing."
                    ),
                }

            # -----------------------------------------------------------
            # Re-review
            # -----------------------------------------------------------

            review = _normalise_review(
                pedagogy.review_script(
                    script,
                    label=f"pedagogy recheck {cycle}",
                )
            )

            current_review_signature = _review_signature(review)

            history.append(
                RevisionRecord(
                    cycle=cycle,
                    label=f"pedagogy revision {cycle}",
                    changed=changed,
                    passed=_review_passed(review),
                    score=review.get("score", 0),
                    issue_count=len(review.get("issues", [])),
                    blocking_issue_count=len(
                        _blocking_issues(review)
                    ),
                )
            )

            # -----------------------------------------------------------
            # Persist detailed review
            # -----------------------------------------------------------

            _save_review(
                context.project_dir,
                {
                    **review,
                    "revision_cycle": cycle,
                    "stage": self.name,
                    "revision_meta": (
                        revision_meta
                        if isinstance(revision_meta, dict)
                        else {}
                    ),
                },
            )

            _save_history(
                context.project_dir,
                history,
            )

            previous_script_signature = current_script_signature
            previous_review_signature = current_review_signature

            # -----------------------------------------------------------
            # Success gate
            # -----------------------------------------------------------

            if _review_passed(review):
                break

            # -----------------------------------------------------------
            # Stagnation gate
            #
            # If both the script and review remain unchanged, further
            # LLM calls are unlikely to produce meaningful progress.
            # -----------------------------------------------------------

            if (
                current_script_signature == before_script_signature
                and current_review_signature == previous_review_signature
            ):
                break

        # ---------------------------------------------------------------
        # Rebuild scene plan from canonical script
        # ---------------------------------------------------------------

        _refresh_plan(context)

        context.pedagogy_review = review
        context.script_revision += 1

        _save_history(
            context.project_dir,
            history,
        )

        return context


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class VerifierPedagogyPlugin(Plugin):
    """Convert the pedagogy review into a formal harness gate."""

    name = "verifier_pedagogy"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "pedagogy_review",
            "script_revision",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
            "pedagogy_verified",
        ]

    def run(self, context: SceneContext) -> SceneContext:
        review = _normalise_review(
            context.pedagogy_review
        )

        issues = review.get("issues", [])

        blocking = _blocking_issues(review)

        passed = _review_passed(review)

        status = "pass" if passed else "fail"

        context.check_results[self.name] = [
            {
                "status": status,
                "finding_type": "pedagogy_review",
                "detail": review.get(
                    "summary",
                    "Pedagogy review complete.",
                ),
                "score": review.get("score", 0),
                "profile": review.get(
                    "profile",
                    "standard",
                ),
                "issues": issues,
                "blocking_issues": blocking,
                "issue_count": len(issues),
                "blocking_issue_count": len(blocking),
            }
        ]

        # ---------------------------------------------------------------
        # Formal gate state
        # ---------------------------------------------------------------

        context.pedagogy_verified = passed

        return context

    def _default_gate(self) -> bool:
        """Default behaviour: pedagogy must pass before generation."""

        return True