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
from .convergence import CandidateSignature, ConvergenceTracker, StopReason
from .journal import EventJournal
from .lifecycle import InvalidTransition, SceneState
from .lifecycle import transition as lifecycle_transition
from .plugin import Plugin
from .revision_history import RevisionEntry, record_revision
from .scene_quality import (
    SceneQuality,
    Verdict,
    classify,
    compare,
    diff_findings,
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

    #: Convergence tracker (P0-4): the immediately preceding cycle for this
    #: scene left the exact same blocking finding-type signature in place.
    NO_PROGRESS = "no_progress"

    #: Convergence tracker: this cycle's finding-type signature reproduces
    #: one already seen at least one cycle earlier (A -> B -> A).
    REPAIR_OSCILLATION = "repair_oscillation"


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

    #: resolved/introduced/unchanged blocking finding types (P0-3) -- what
    #: actually changed between the accepted baseline and this candidate,
    #: not merely whether the net verdict was better/worse/equal.
    finding_diff: dict[str, list[str]] = field(default_factory=dict)

    #: The repair goal/invariants this cycle operated under (P1-1) --
    #: {category, subtype, allowed_changes, protected_properties,
    #: repair_instruction}, read from the router's already-existing
    #: ``RepairPlan`` (``repair_router/__init__.py``'s ``_contract_for``).
    #: That mechanism already implements the target architecture's "repair
    #: goal + invariants + category-constrained allowed_changes" -- this
    #: field just makes it visible in the decision log instead of only
    #: living inside the prompt text sent to the LLM.
    repair_contract: dict[str, Any] = field(default_factory=dict)

    decision: str = Decision.VERIFIER_FAILED.value
    rejection_reason: str = ""
    repairs_used_for_scene: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""

    #: P1-4/Phase 18: true when this cycle ran under a dry-run request --
    #: ``decision`` still reflects what WOULD have happened (including
    #: ``"accepted"``), but the candidate was always discarded and no
    #: lifecycle/revision-history side effect was applied. See
    #: ``RepairController.repair_scene``'s ``dry_run`` parameter.
    dry_run: bool = False

    @property
    def accepted(self) -> bool:
        # A dry run never actually commits, regardless of what decision it
        # would have reached -- callers (runner._repair's
        # lineage.invalidate_scene trigger, in particular) must never treat
        # a dry-run preview as a real acceptance.
        return self.decision == Decision.ACCEPTED.value and not self.dry_run

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
        journal: EventJournal | None = None,
        convergence: ConvergenceTracker | None = None,
    ) -> None:
        self.router = router
        self.plugins_by_name = dict(plugins_by_name or {})
        self.logger = logger
        self.log_path = Path(log_path) if log_path else None

        #: Durable event journal (P0-1). Optional so every existing caller
        #: (tests, tools/harness_run.py before it is updated) keeps working.
        self.journal = journal

        #: Cross-cycle no-progress/oscillation detector (P0-4). One tracker
        #: per controller instance, matching how ``repairs_per_scene``
        #: already accumulates across cycles for the life of one harness
        #: run.
        self.convergence = convergence or ConvergenceTracker()

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
        *,
        dry_run: bool = False,
    ) -> RepairDecisionRecord:
        """Run one complete, regression-safe repair cycle for one scene.

        ``dry_run`` (Phase 18): generate, render and verify a candidate,
        and judge it exactly as normal -- but never promote it and never
        apply any lifecycle/revision-history side effect, regardless of
        the verdict. ``record.decision`` still reports what WOULD have
        happened; ``record.accepted`` is always ``False`` for a dry run.
        Does not consume repair budget -- a preview must not cost a scene
        one of its limited real attempts.
        """

        self._cycle_id += 1

        trigger = findings[0] if findings else {}
        plan = self.router.plan(trigger, source_plugin)

        record = RepairDecisionRecord(
            cycle_id=self._cycle_id,
            dry_run=dry_run,
            stem=str(stem),
            trigger_finding_type=plan.finding_type,
            source_plugin=source_plugin,
            routed_to=list(plan.targets),
            previous_revision=lineage.current_revision(context, stem),
            repair_contract=self._extract_repair_contract(plan),
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
                context=context,
            )

        if not plan.routable:
            return self._finish(
                record,
                Decision.NOT_ROUTABLE,
                f"no repair route for finding_type {plan.finding_type!r}",
                context=context,
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
                context=context,
            )

        # A rejected candidate still consumes budget -- otherwise a scene
        # could be retried indefinitely by producing different bad results.
        # A dry run does not: it is a preview, not a real attempt.
        if not dry_run:
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

        self._safe_transition(
            context, stem, SceneState.REPAIRING,
            reason=f"repair:{plan.finding_type}",
        )

        self.router.emit(
            "repair.started",
            scene_id=stem,
            finding_type=plan.finding_type,
            cycle=record.cycle_id,
            routed_to=plan.targets,
        )
        self._journal(
            context, "scene.repair.started", stem, record.candidate_revision,
            payload={
                "finding_type": plan.finding_type,
                "routed_to": list(plan.targets),
                "repair_contract": record.repair_contract,
            },
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
                    context=context,
                    restored_revision=scope.base_revision,
                )

            self._journal(
                context, "scene.repair.candidate", stem, scope.revision,
                payload={"code_path": str(scope.code_path)},
            )
            self._safe_transition(context, stem, SceneState.RENDERING)

            self._render_candidate(context, stem, record)
            self._journal(context, "scene.repair.rendered", stem, scope.revision)
            self._safe_transition(context, stem, SceneState.RENDERED)

            self._verify_candidate(context, stem, record)
            self._journal(context, "scene.repair.verified", stem, scope.revision)
            self._safe_transition(context, stem, SceneState.VERIFYING)

            candidate_quality = SceneQuality.collect(context, stem)
            record.candidate_quality = candidate_quality.to_dict()
            record.finding_diff = diff_findings(
                accepted_quality, candidate_quality,
            ).to_dict()

            verdict = self._judge(
                plan,
                accepted_quality,
                candidate_quality,
                context,
                stem,
                record,
            )

            # Convergence check (P0-4): consulted after the candidate has
            # been fully verified, so the stop reason is recorded with
            # complete evidence, and only on the path that would otherwise
            # reject -- an accepted candidate is, by the acceptance rule
            # itself, genuine progress and does not need second-guessing.
            stop_reason = self.convergence.record(
                stem,
                CandidateSignature.of(
                    self._read_candidate_source(scope),
                    candidate_quality.blocking_types.keys(),
                ),
            )

            if verdict is not None:
                decision, reason = verdict

                if stop_reason is StopReason.NO_PROGRESS:
                    decision, reason = (
                        Decision.NO_PROGRESS,
                        f"no progress: identical blocking finding-type "
                        f"signature as the immediately preceding repair "
                        f"cycle ({reason})",
                    )
                elif stop_reason is StopReason.REPAIR_OSCILLATION:
                    decision, reason = (
                        Decision.REPAIR_OSCILLATION,
                        f"oscillation: this blocking finding-type "
                        f"signature already occurred earlier in this "
                        f"scene's repair history ({reason})",
                    )

                self._restore(context, scope, accepted_results)

                return self._finish(
                    record,
                    decision,
                    reason,
                    context=context,
                    restored_revision=scope.base_revision,
                )

            if record.dry_run:
                # Would accept -- but a dry run never commits. Restore the
                # accepted scene exactly as any other non-commit path does,
                # and report the WOULD-BE decision (ACCEPTED) so a caller
                # can see the preview's verdict; record.accepted correctly
                # reads False regardless, since it checks dry_run too.
                self._restore(context, scope, accepted_results)

                return self._finish(
                    record,
                    Decision.ACCEPTED,
                    "[dry-run] would accept -- no changes committed",
                    context=context,
                    restored_revision=scope.base_revision,
                )

            self.convergence.reset(stem)

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
                context=context,
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
                context=context,
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
        context: SceneContext | None = None,
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

        # context is optional so this stays callable from anywhere _finish
        # was already called from without one -- every real call site does
        # pass it, this is only a safety net for future/test callers.
        if context is not None:
            self._journal_repair_outcome(context, record, decision)

            # A dry run (Phase 18) is a preview: it must leave zero trace
            # in the scene's lifecycle state or its persisted revision
            # history, regardless of what decision it would have reached.
            # The journal event above still records it -- observability
            # without commitment is exactly the point of a dry run.
            if not record.dry_run:
                self._transition_after_repair(context, record.stem, decision)
                self._record_revision_history(context, record, decision)

        return record

    # ------------------------------------------------------------------
    # Durable journal + lifecycle -- both fail-safe, never derail a cycle
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_repair_contract(plan: Any) -> dict[str, Any]:
        """Read the router's repair goal/invariants off a ``RepairPlan``.

        Defensive against simplified test doubles (``test_layout_semantic
        .py``'s ``_Plan``, and this module's own test fixtures) which only
        implement ``finding_type``/``targets``/``routable`` -- an absent
        attribute yields an empty/default value rather than an
        ``AttributeError`` breaking a repair cycle over pure observability.
        """

        return {
            "category": getattr(plan, "category", "") or "",
            "subtype": getattr(plan, "subtype", None),
            "allowed_changes": list(getattr(plan, "allowed_changes", None) or []),
            "protected_properties": list(
                getattr(plan, "protected_properties", None) or []
            ),
            "repair_instruction": getattr(plan, "repair_instruction", "") or "",
        }

    @staticmethod
    def _project_name(context: SceneContext) -> str:
        project_dir = getattr(context, "project_dir", None)

        if project_dir is None:
            return ""

        return getattr(project_dir, "name", str(project_dir))

    def _journal(
        self,
        context: SceneContext,
        event_type: str,
        stem: str,
        revision: int,
        *,
        status: str = "ok",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.journal is None:
            return

        self.journal.append(
            event_type=event_type,
            project=self._project_name(context),
            scene_id=stem,
            revision=revision,
            status=status,
            payload=payload or {},
        )

    def _journal_repair_outcome(
        self,
        context: SceneContext,
        record: RepairDecisionRecord,
        decision: Decision,
    ) -> None:
        if record.dry_run:
            # A dry run never commits, so it is never a genuine
            # scene.accepted -- always report it as a rollback (the
            # candidate WAS opened and rendered, then always discarded)
            # regardless of what decision it would have reached. The
            # would-be decision is still in the payload.
            event_type, status = "scene.rollback", "ok"
        elif decision is Decision.ACCEPTED:
            event_type, status = "scene.accepted", "ok"
        elif record.restored_revision is not None:
            # A candidate was opened and then discarded -- a genuine
            # rollback, not merely "never got to try".
            event_type, status = "scene.rollback", "fail"
        else:
            # NOT_ROUTABLE / REPAIR_BUDGET_EXHAUSTED -- no candidate was
            # ever opened for this cycle.
            event_type, status = "scene.rejected", "fail"

        self._journal(
            context,
            event_type,
            record.stem,
            record.candidate_revision,
            status=status,
            payload={
                "decision": decision.value,
                "reason": record.rejection_reason,
                "finding_diff": record.finding_diff,
                "dry_run": record.dry_run,
            },
        )

    def _safe_transition(
        self,
        context: SceneContext,
        stem: str,
        to_state: SceneState,
        *,
        reason: str = "",
    ) -> None:
        """Attempt a lifecycle transition; never let a mismatch break a cycle.

        Lifecycle tracking is observational (matching the fail-safe posture
        already established by ``journal``/``quality_report``) -- an
        ``InvalidTransition`` here means the state machine's model of this
        scene's history and the repair controller's own bookkeeping have
        drifted, which is worth recording, not worth crashing a real build
        over.
        """

        try:
            lifecycle_transition(context, stem, to_state, journal=self.journal, reason=reason)
        except InvalidTransition as exc:
            self._journal(
                context, "harness.selfcheck", stem,
                context.scene_versions.get(str(stem), 0),
                status="skip",
                payload={"note": f"lifecycle transition skipped: {exc}"},
            )

    def _transition_after_repair(
        self,
        context: SceneContext,
        stem: str,
        decision: Decision,
    ) -> None:
        if decision is Decision.ACCEPTED:
            self._safe_transition(context, stem, SceneState.ACCEPTED, reason="repair accepted")
            self.convergence.reset(stem)
            return

        if decision in (Decision.NOT_ROUTABLE, Decision.REPAIR_BUDGET_EXHAUSTED):
            # Nothing was attempted -- no candidate was ever opened, so the
            # scene's state is exactly what it already was.
            return

        # Every other decision discarded a candidate. Try REJECTED first
        # (valid from VERIFYING, the common case where a candidate was
        # fully evaluated) then ROLLED_BACK (valid from REJECTED, and also
        # directly from REPAIRING for an early-exit failure that never
        # reached VERIFYING) -- _safe_transition silently skips whichever
        # hop does not apply to the actual current state rather than
        # requiring the caller to know which path this cycle took.
        self._safe_transition(context, stem, SceneState.REJECTED, reason=decision.value)
        self._safe_transition(context, stem, SceneState.ROLLED_BACK, reason=decision.value)

    def _record_revision_history(
        self,
        context: SceneContext,
        record: RepairDecisionRecord,
        decision: Decision,
    ) -> None:
        """Persist this cycle's outcome to ``revisions.json`` (P1-2).

        Only real, individually-repairable scenes are tracked -- whole-
        video findings (``lineage.GLOBAL_STEM``) have no per-scene
        revision to record against. Every decision is recorded, not just
        acceptances: a rejected attempt's reasoning is otherwise lost the
        moment ``workspace.discard`` removes its sidecar files.
        """

        if not lineage.is_scene_stem(record.stem):
            return

        entry = RevisionEntry(
            revision=record.candidate_revision,
            parent_revision=record.previous_revision,
            timestamp=record.timestamp,
            reason=f"repair:{record.trigger_finding_type}",
            decision=decision.value,
            repair_contract=record.repair_contract,
            finding_diff=record.finding_diff,
            quality=record.candidate_quality,
        )

        record_revision(
            getattr(context, "project_dir", None),
            record.stem,
            entry,
            accepted=(decision is Decision.ACCEPTED),
        )

    @staticmethod
    def _read_candidate_source(scope: Any) -> str:
        """Best-effort read of a candidate's source text, for hashing.

        Never raises -- a candidate that failed before writing any source
        (e.g. the repair target crashed) still needs a signature so the
        convergence tracker has something deterministic to compare.
        """

        try:
            path = getattr(scope, "code_path", None)

            if path is not None and Path(path).exists():
                return Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

        return ""

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
