"""The authoritative repair controller.

There is exactly one owner of the repair lifecycle, and this is it. The
runner invokes it; it never self-triggers. Before this existed the harness
ran two competing loops -- an inner repair/re-verify loop inside
``HarnessRunner._run_one`` and an outer heuristic rewind inside
``HarnessRunner.run`` -- which coordinated only through mutations to
``SceneContext``, held three uncoordinated budgets, and could each miss
repairs the other had already consumed budget for.

The acceptance rule
-------------------

A repair candidate is accepted **iff all three hold**:

1. It introduces no new blocking finding type for the scene, and its total
   blocking count is no higher than the accepted scene's.
2. The finding that triggered the repair is gone.
3. The deterministic quality comparison says the candidate is BETTER or
   EQUAL (see :mod:`prompt2render.harness.scene_quality`).

Otherwise the candidate is discarded, the accepted scene is restored
verbatim, and the decision is recorded with the reason.

Rule 1 is what stops a repair trading one defect for another -- fixing a
layout collision by breaking animation continuity leaves the blocking
*count* unchanged while making the scene worse. Rule 3 is what stops a net
downgrade even when no rule-1 violation occurred. Together they encode the
actual goal, which is not "make every verifier green at any cost" but
"remove the detected defect while preserving or improving what was already
accepted".

Crucially, the whole scene is re-verified -- every scene-scoped verifier in
the pipeline, not merely the one that complained. "The verifier that
failed now passes" is not evidence that nothing else broke, and accepting
on that basis is precisely how an LLM repair silently downgrades a scene.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import lineage, workspace
from .context import SceneContext
from .plugin import Plugin
from .scene_quality import (
    SceneQuality,
    Verdict,
    classify,
    compare,
    new_blocking_types,
)

#: Verifiers that report per scene and are therefore re-run after a repair.
#: Order matters: observation feeds the verifiers that read its output.
SCENE_OBSERVERS = ("observer_visual",)

SCENE_VERIFIERS = (
    "verifier_execution",
    "verifier_semantic",
    "verifier_spatial",
    "verifier_layout",
    "verifier_motion",
    "verifier_lifecycle",
    "verifier_temporal",
)

#: Whole-video verifiers are deliberately excluded: they emit findings with
#: no stem, so there is no single scene to regenerate for them.
WHOLE_VIDEO_VERIFIERS = (
    "verifier_audio",
    "verifier_pedagogy",
)

#: Plugins that turn an accepted scene source into a render.
SCENE_RENDERERS = ("renderer_stills", "renderer_manim")

DEFAULT_MAX_REPAIRS_PER_SCENE = 3
DEFAULT_MAX_TOTAL_REPAIRS = 12


class Decision(str, Enum):
    """Outcome of one complete repair cycle."""

    ACCEPTED = "accepted"
    REGRESSION_REJECTED = "regression_rejected"
    VERIFIER_FAILED = "verifier_failed"
    TARGET_DEFECT_UNRESOLVED = "target_defect_unresolved"
    REPAIR_BUDGET_EXHAUSTED = "repair_budget_exhausted"
    NOT_ROUTABLE = "not_routable"
    REPAIR_ERRORED = "repair_errored"


@dataclass
class RepairDecisionRecord:
    """A complete, auditable account of one repair cycle.

    This is the research artifact: every field needed to reconstruct why a
    candidate was kept or thrown away, without re-running anything.
    """

    cycle_id: int
    stem: str
    trigger_finding_type: str
    source_plugin: str
    routed_to: list[str] = field(default_factory=list)
    previous_revision: int = 0
    candidate_revision: int = 0
    restored_revision: int | None = None
    triggering_findings: list[dict[str, Any]] = field(default_factory=list)
    verifier_results: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict
    )
    previous_quality: dict[str, Any] = field(default_factory=dict)
    candidate_quality: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] = field(default_factory=dict)
    decision: str = Decision.VERIFIER_FAILED.value
    rejection_reason: str = ""
    repairs_used_for_scene: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""

    @property
    def accepted(self) -> bool:
        return self.decision == Decision.ACCEPTED.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _blocking_findings(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        finding
        for finding in results or []
        if isinstance(finding, dict) and classify(finding) == "blocking"
    ]


class RepairController:
    """Owns detect -> snapshot -> repair -> re-verify -> compare -> decide."""

    def __init__(
        self,
        *,
        router: Any,
        plugins_by_name: dict[str, Plugin],
        logger: Any = None,
        log_path: Path | None = None,
        max_repairs_per_scene: int = DEFAULT_MAX_REPAIRS_PER_SCENE,
        max_total_repairs: int = DEFAULT_MAX_TOTAL_REPAIRS,
    ) -> None:
        self.router = router
        self.plugins_by_name = dict(plugins_by_name or {})
        self.logger = logger
        self.log_path = Path(log_path) if log_path else None

        self.max_repairs_per_scene = max(0, int(max_repairs_per_scene))
        self.max_total_repairs = max(0, int(max_total_repairs))

        #: ``{stem: attempts}`` -- a rejected regression counts as an
        #: attempt, so a scene cannot be retried forever by producing
        #: successively different bad candidates.
        self.repairs_per_scene: dict[str, int] = {}
        self.total_repairs = 0

        self.decisions: list[RepairDecisionRecord] = []
        self._cycle_id = 0

    # ------------------------------------------------------------------
    # Budget
    # ------------------------------------------------------------------

    def budget_remaining(self, stem: str) -> bool:
        """Whether another repair may be attempted for this scene."""

        if self.total_repairs >= self.max_total_repairs:
            return False

        return (
            self.repairs_per_scene.get(str(stem), 0)
            < self.max_repairs_per_scene
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def repair_scene(
        self,
        context: SceneContext,
        stem: str,
        findings: list[dict[str, Any]],
        source_plugin: str,
    ) -> RepairDecisionRecord:
        """Run one complete, regression-safe repair cycle for one scene."""

        self._cycle_id += 1

        trigger = findings[0] if findings else {}
        plan = self.router.plan(trigger, source_plugin)

        record = RepairDecisionRecord(
            cycle_id=self._cycle_id,
            stem=str(stem),
            trigger_finding_type=plan.finding_type,
            source_plugin=source_plugin,
            routed_to=list(plan.targets),
            previous_revision=lineage.current_revision(context, stem),
            triggering_findings=[
                copy.deepcopy(f) for f in findings if isinstance(f, dict)
            ],
            repairs_used_for_scene=self.repairs_per_scene.get(str(stem), 0),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        if not lineage.is_scene_stem(stem):
            return self._finish(
                record,
                Decision.NOT_ROUTABLE,
                "whole-video finding has no single scene to repair",
            )

        if not plan.routable:
            return self._finish(
                record,
                Decision.NOT_ROUTABLE,
                f"no repair route for finding_type {plan.finding_type!r}",
            )

        if not self.budget_remaining(stem):
            return self._finish(
                record,
                Decision.REPAIR_BUDGET_EXHAUSTED,
                (
                    f"scene {stem} has used "
                    f"{self.repairs_per_scene.get(str(stem), 0)}/"
                    f"{self.max_repairs_per_scene} repairs "
                    f"(total {self.total_repairs}/{self.max_total_repairs}); "
                    "preserving the last accepted state"
                ),
            )

        # A rejected candidate still consumes budget -- otherwise a scene
        # could be retried indefinitely by producing different bad results.
        self.repairs_per_scene[str(stem)] = (
            self.repairs_per_scene.get(str(stem), 0) + 1
        )
        self.total_repairs += 1
        record.repairs_used_for_scene = self.repairs_per_scene[str(stem)]

        return self._run_cycle(context, stem, plan, record)

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------

    def _run_cycle(
        self,
        context: SceneContext,
        stem: str,
        plan: Any,
        record: RepairDecisionRecord,
    ) -> RepairDecisionRecord:

        accepted_quality = SceneQuality.collect(context, stem)
        record.previous_quality = accepted_quality.to_dict()

        # Preserve the accepted scene's findings so a rejection can restore
        # the full evidential state, not just the files.
        accepted_results = self._snapshot_scene_results(context, stem)

        canonical_code = self._canonical_code_path(context, stem)

        scope = workspace.open_candidate(
            context,
            stem,
            canonical_code=canonical_code,
            trigger_finding_type=plan.finding_type,
        )
        record.candidate_revision = scope.revision

        self.router.emit(
            "repair.started",
            scene_id=stem,
            finding_type=plan.finding_type,
            cycle=record.cycle_id,
            routed_to=plan.targets,
        )

        try:
            execution = self.router.execute(plan, context)
            record.routed_to = list(execution.targets_run)
            record.errors.extend(execution.errors)

            if not execution.ok:
                self._restore(context, scope, accepted_results)

                return self._finish(
                    record,
                    Decision.REPAIR_ERRORED,
                    "; ".join(execution.errors)
                    or "repair execution failed",
                    restored_revision=scope.base_revision,
                )

            self._render_candidate(context, stem, record)
            self._verify_candidate(context, stem, record)

            candidate_quality = SceneQuality.collect(context, stem)
            record.candidate_quality = candidate_quality.to_dict()

            verdict = self._judge(
                plan,
                accepted_quality,
                candidate_quality,
                context,
                stem,
                record,
            )

            if verdict is not None:
                self._restore(context, scope, accepted_results)

                return self._finish(
                    record,
                    verdict[0],
                    verdict[1],
                    restored_revision=scope.base_revision,
                )

            revision = workspace.promote(
                context,
                scope,
                canonical_code=canonical_code,
                canonical_render_dir=self._canonical_render_dir(context, stem),
            )
            record.candidate_revision = revision

            # The scene genuinely changed: everything downstream of it,
            # including out/final.mp4, is stale by revision comparison.
            context.repair_context.pop(str(stem), None)

            return self._finish(
                record,
                Decision.ACCEPTED,
                "",
            )

        except (Exception, SystemExit) as exc:
            # A crash mid-cycle must never leave the accepted scene lost or
            # a candidate half-promoted.
            record.errors.append(f"{type(exc).__name__}: {exc}")

            if context.candidate is not None:
                self._restore(context, scope, accepted_results)

            return self._finish(
                record,
                Decision.REPAIR_ERRORED,
                f"repair cycle raised: {type(exc).__name__}: {exc}",
                restored_revision=scope.base_revision,
            )

    # ------------------------------------------------------------------
    # Judgement -- the acceptance rule
    # ------------------------------------------------------------------

    def _judge(
        self,
        plan: Any,
        accepted: SceneQuality,
        candidate: SceneQuality,
        context: SceneContext,
        stem: str,
        record: RepairDecisionRecord,
    ) -> tuple[Decision, str] | None:
        """Return ``None`` to accept, or ``(decision, reason)`` to reject."""

        # Rule 1a -- no newly-introduced blocking finding types.
        introduced = new_blocking_types(accepted, candidate)

        if introduced:
            summary = ", ".join(
                f"{name} x{count}" for name, count in sorted(introduced.items())
            )

            return (
                Decision.REGRESSION_REJECTED,
                f"repair introduced new blocking finding(s): {summary}",
            )

        # Rule 1b -- blocking count must not increase.
        if candidate.blocking > accepted.blocking:
            return (
                Decision.REGRESSION_REJECTED,
                f"blocking findings rose {accepted.blocking} -> "
                f"{candidate.blocking}",
            )

        # Rule 2 -- the defect that triggered this repair must be gone.
        if plan.finding_type in candidate.blocking_types:
            return (
                Decision.TARGET_DEFECT_UNRESOLVED,
                f"the triggering defect {plan.finding_type!r} is still "
                "present after repair",
            )

        # Rule 3 -- the candidate must not be a net downgrade.
        comparison = compare(accepted, candidate)
        record.comparison = comparison.to_dict()

        if comparison.verdict in (Verdict.WORSE,):
            return (
                Decision.REGRESSION_REJECTED,
                f"quality regressed: {comparison.reason}",
            )

        if comparison.verdict is Verdict.INSUFFICIENT_EVIDENCE:
            return (
                Decision.VERIFIER_FAILED,
                f"cannot establish the candidate is at least as good: "
                f"{comparison.reason}",
            )

        return None

    # ------------------------------------------------------------------
    # Candidate production and verification
    # ------------------------------------------------------------------

    def _render_candidate(
        self,
        context: SceneContext,
        stem: str,
        record: RepairDecisionRecord,
    ) -> None:
        """Render the candidate using whichever renderer is active."""

        for name in SCENE_RENDERERS:
            renderer = self.plugins_by_name.get(name)

            if renderer is None:
                continue

            try:
                if hasattr(renderer, "regenerate_one"):
                    renderer.regenerate_one(context, stem)
                else:
                    renderer.run(context)
            except (Exception, SystemExit) as exc:
                record.errors.append(
                    f"{name} candidate render failed: "
                    f"{type(exc).__name__}: {exc}"
                )

            return

    def _verify_candidate(
        self,
        context: SceneContext,
        stem: str,
        record: RepairDecisionRecord,
    ) -> None:
        """Re-run EVERY scene-scoped verifier against the candidate.

        Not just the one that failed. Accepting on the strength of the
        original complaint alone is exactly how a repair that fixes layout
        by breaking continuity gets through.
        """

        self._clear_scene_results(context, stem)

        for name in SCENE_OBSERVERS + SCENE_VERIFIERS:
            plugin = self.plugins_by_name.get(name)

            if plugin is None or not plugin.enabled():
                continue

            try:
                result = plugin.run(context)

                if isinstance(result, SceneContext):
                    context = result

            except (Exception, SystemExit) as exc:
                record.errors.append(
                    f"{name} re-verification failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue

            produced = context.check_results.get(name)

            if isinstance(produced, list):
                scene_scoped = [
                    finding
                    for finding in produced
                    if isinstance(finding, dict)
                    and str(
                        finding.get("stem") or finding.get("scene_id") or ""
                    ) == str(stem)
                ]

                if scene_scoped:
                    record.verifier_results[name] = [
                        copy.deepcopy(f) for f in scene_scoped
                    ]

    # ------------------------------------------------------------------
    # Scene-scoped check-result bookkeeping
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_scene_results(
        context: SceneContext,
        stem: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Deep-copy every finding recorded against one scene."""

        target = str(stem)
        snapshot: dict[str, list[dict[str, Any]]] = {}

        for plugin_name, results in context.check_results.items():
            if not isinstance(results, list):
                continue

            mine = [
                copy.deepcopy(finding)
                for finding in results
                if isinstance(finding, dict)
                and str(
                    finding.get("stem") or finding.get("scene_id") or ""
                ) == target
            ]

            if mine:
                snapshot[plugin_name] = mine

        return snapshot

    @staticmethod
    def _clear_scene_results(
        context: SceneContext,
        stem: str,
    ) -> None:
        """Drop one scene's findings, leaving every other scene's intact."""

        target = str(stem)

        for plugin_name in list(context.check_results):
            results = context.check_results.get(plugin_name)

            if not isinstance(results, list):
                continue

            kept = [
                finding
                for finding in results
                if not (
                    isinstance(finding, dict)
                    and str(
                        finding.get("stem") or finding.get("scene_id") or ""
                    ) == target
                )
            ]

            if len(kept) != len(results):
                context.check_results[plugin_name] = kept

    def _restore(
        self,
        context: SceneContext,
        scope: Any,
        accepted_results: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Put the accepted scene back, files and evidence alike."""

        stem = scope.stem

        workspace.discard(context, scope)

        self._clear_scene_results(context, stem)

        for plugin_name, results in accepted_results.items():
            context.check_results.setdefault(plugin_name, []).extend(
                copy.deepcopy(results)
            )

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def _canonical_code_path(
        self,
        context: SceneContext,
        stem: str,
    ) -> Path:
        """Where this scene's accepted source lives."""

        if "generator_manim" in self.plugins_by_name:
            return (
                Path(context.project_dir)
                / "build"
                / "manim"
                / f"scene_{stem}.py"
            )

        from ..stills import scene_path

        return scene_path(context.project_dir, stem)

    def _canonical_render_dir(
        self,
        context: SceneContext,
        stem: str,
    ) -> Path | None:
        """Where this scene's accepted render lives, if it has a directory."""

        if "renderer_stills" in self.plugins_by_name:
            from ..stills import stills_dir

            return stills_dir(context.project_dir, stem)

        # The Manim renderer writes a single clip into sections/, which
        # promote() handles through the candidate's own render dir contents.
        return None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _finish(
        self,
        record: RepairDecisionRecord,
        decision: Decision,
        reason: str,
        *,
        restored_revision: int | None = None,
    ) -> RepairDecisionRecord:
        record.decision = decision.value
        record.rejection_reason = reason
        record.restored_revision = restored_revision

        self.decisions.append(record)
        self._write(record)

        self.router.emit(
            "repair.finished",
            scene_id=record.stem,
            finding_type=record.trigger_finding_type,
            cycle=record.cycle_id,
            outcome=record.decision,
        )

        if self.logger is not None:
            try:
                self.logger.info(
                    f"repair {record.stem} rev{record.previous_revision}"
                    f"->{record.candidate_revision}: {record.decision}"
                    + (f" -- {reason}" if reason else "")
                )
            except Exception:
                pass

        return record

    def _write(
        self,
        record: RepairDecisionRecord,
    ) -> None:
        """Append one decision to the repair log. Never raises."""

        if self.log_path is None:
            return

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(record.to_dict(), ensure_ascii=False) + "\n"
                )
        except Exception:
            return

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, int]:
        """Counts per decision, for the self-correction report."""

        counts: dict[str, int] = {}

        for record in self.decisions:
            counts[record.decision] = counts.get(record.decision, 0) + 1

        return counts


__all__ = [
    "DEFAULT_MAX_REPAIRS_PER_SCENE",
    "DEFAULT_MAX_TOTAL_REPAIRS",
    "Decision",
    "RepairController",
    "RepairDecisionRecord",
    "SCENE_RENDERERS",
    "SCENE_VERIFIERS",
    "WHOLE_VIDEO_VERIFIERS",
]
