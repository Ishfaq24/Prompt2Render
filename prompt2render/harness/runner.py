"""Pipeline runner for the Prompt2Render harness.

The runner executes an already-resolved plugin DAG over one SceneContext,
and it is the single authority over the repair lifecycle.

Plugin execution has two failure classes:

1. Hard execution failure: ``plugin.run()`` raises. Always fatal for that
   invocation, regardless of the plugin's gate setting.

2. Soft verification failure: ``plugin.run()`` returns normally but writes
   ``status == "fail"`` entries to ``context.check_results[plugin.name]``.
   The runner hands those to :class:`RepairController`, which owns the
   complete detect -> snapshot -> repair -> re-verify -> compare -> decide
   cycle and returns an auditable decision.

What this replaced
------------------

There used to be two competing loops here:

* an inner repair/re-verify loop inside ``_run_one`` that emitted
  ``check.failed``, let the router rewrite a finding's status to
  ``"resolved"``, and re-ran the plugin up to three times; and
* an outer rewind loop in ``run()`` that inferred a set of affected stems
  from four heuristics (new ``repair_context`` keys, vanished
  ``render_artifacts``, empty manifests, scene-plan text fingerprints) and
  jumped the plugin index backwards.

They coordinated only through mutations to ``SceneContext``. The inner
loop's success path cleared ``repair_context`` *before returning*, which
destroyed the outer loop's primary trigger -- the other three heuristics
existed to compensate, and a repair that changed neither a render artifact
nor scene-plan text was invisible to all four. Their three budgets
(router cycles, re-verify attempts, rewind counts) had no shared
accounting.

Both are gone. Repair is now explicit, revision-driven, and owned in one
place, and staleness is a comparison against ``scene_versions`` rather than
a heuristic (see :mod:`prompt2render.harness.lineage`).
"""

from __future__ import annotations

import time
from typing import Any

from . import lineage
from .context import HistoryEntry, SceneContext, snapshot
from .events import EventBus
from .logging_ import (
    StructuredLogger,
    write_self_correction_report,
)
from .plugin import Plugin
from .repair_controller import RepairController
from .scene_quality import classify


class GateFailure(RuntimeError):
    """Raised when a gated plugin still has blocking findings."""

    def __init__(
        self,
        plugin_name: str,
        findings: list[dict[str, Any]],
    ) -> None:
        self.plugin_name = plugin_name
        self.findings = findings

        super().__init__(
            f"{plugin_name}: hard gate failed — "
            f"{findings}"
        )


class FinalizationFailure(GateFailure):
    """Raised when scene gates passed but no valid programme was produced.

    This is the reachability invariant: a run whose scene-level gates all
    pass must actually produce ``out/final.mp4``. Terminating "successfully"
    with no video, or with a video built from superseded scene revisions, is
    a failure the harness must state plainly rather than hide.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason

        super().__init__(
            "finalization",
            [
                {
                    "status": "fail",
                    "finding_type": "final_video_unreachable",
                    "category": "TECHNICAL",
                    "severity": "BLOCKING",
                    "detail": reason,
                }
            ],
        )


#: Stages that produce or validate the finished programme. Used to decide
#: whether the reachability invariant applies to a given pipeline.
FINALIZATION_STAGES = (
    "renderer_finish",
    "renderer_manim_finish",
)

#: Minimum plausible size for a real encoded video, in bytes. Matches the
#: threshold encode.py/finish.py already use for their own output checks.
MIN_FINAL_BYTES = 2048


class HarnessRunner:
    """Execute a resolved plugin pipeline, owning the repair lifecycle."""

    def __init__(
        self,
        plugins: list[Plugin],
        logger: StructuredLogger,
        bus: EventBus | None = None,
        *,
        repair_controller: RepairController | None = None,
        enforce_final_video: bool = True,
    ) -> None:
        self.plugins = list(plugins)
        self.logger = logger
        self.bus = bus or EventBus()
        self.repair_controller = repair_controller

        #: When False, the reachability invariant is not enforced -- used by
        #: partial pipelines (the ablation runner, focused tests) that
        #: deliberately contain no finish stage.
        self.enforce_final_video = bool(enforce_final_video)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        ctx: SceneContext,
        halt_on_gate_failure: bool = True,
    ) -> SceneContext:
        """Run every resolved plugin in order, repairing scenes as needed.

        Two explicit phases:

        1. **Scene phase** -- run each stage. A stage with blocking
           scene-scoped findings is handed to the repair controller, which
           either accepts a candidate (advancing the scene's revision) or
           restores the accepted state. The stage is then re-evaluated once
           against the post-repair evidence.

        2. **Finalization** -- after every stage has run, verify the
           reachability invariant: if the scene gates passed, a valid
           ``out/final.mp4`` built from the current revisions must exist.
        """

        for index, plugin in enumerate(self.plugins):
            ctx = self._run_one(
                plugin,
                ctx,
                halt_on_gate_failure=halt_on_gate_failure,
                plugin_index=index,
            )

        self._check_final_video_reachable(ctx, halt_on_gate_failure)

        return ctx

    # ------------------------------------------------------------------
    # Single stage
    # ------------------------------------------------------------------

    def _run_one(
        self,
        plugin: Plugin,
        ctx: SceneContext,
        *,
        halt_on_gate_failure: bool,
        plugin_index: int,
    ) -> SceneContext:
        """Execute one stage, repair any scene defects, decide its gate."""

        snap = snapshot(ctx)

        self.bus.emit(
            "stage.started",
            plugin=plugin.name,
        )

        started = time.monotonic()
        diagnostics = ""

        ctx = self._execute(plugin, ctx, snap, started)

        self._normalize(ctx, plugin)
        self._stamp_revisions(ctx, plugin)

        fails = self._failures(ctx, plugin)

        # --------------------------------------------------------------
        # Repair -- delegated entirely to the controller
        # --------------------------------------------------------------

        if fails:
            ctx, repaired = self._repair(ctx, plugin, fails)

            if repaired:
                # Re-evaluate against post-repair evidence. The controller
                # already re-ran every scene verifier, so the stage is not
                # re-executed here -- doing so would duplicate its work and
                # let a stage overwrite the controller's findings.
                fails = self._failures(ctx, plugin)

        # --------------------------------------------------------------
        # Gate
        # --------------------------------------------------------------

        ok = not bool(fails)

        if fails:
            diagnostics = "; ".join(
                str(
                    finding.get(
                        "detail",
                        finding.get("message", ""),
                    )
                )
                for finding in fails
            )

            if plugin.is_gate() and halt_on_gate_failure:
                self.logger.log_invocation(
                    plugin=plugin.name,
                    input_ctx=snap,
                    output_ctx=ctx,
                    ok=False,
                    diagnostics=diagnostics,
                    duration_s=time.monotonic() - started,
                )

                write_self_correction_report(
                    ctx,
                    final_pass=False,
                    repair_controller=self.repair_controller,
                )

                raise GateFailure(
                    plugin.name,
                    fails,
                )

        ctx.history.append(
            _history_entry(
                plugin,
                ok=ok,
            )
        )

        self.logger.log_invocation(
            plugin=plugin.name,
            input_ctx=snap,
            output_ctx=ctx,
            ok=ok,
            diagnostics=diagnostics,
            duration_s=time.monotonic() - started,
        )

        return ctx

    def _execute(
        self,
        plugin: Plugin,
        ctx: SceneContext,
        snap: SceneContext,
        started: float,
    ) -> SceneContext:
        """Forward execution. A raise is always fatal for this invocation."""

        try:
            result = plugin.run(ctx)

            if result is not None:
                if not isinstance(result, SceneContext):
                    raise TypeError(
                        f"{plugin.name}.run() returned "
                        f"{type(result).__name__}; "
                        "expected SceneContext."
                    )

                ctx = result

            return ctx

        except (Exception, SystemExit) as exc:
            # SystemExit is deliberately included: several prompt2render
            # modules use it for expected fatal configuration conditions.
            diagnostics = f"{type(exc).__name__}: {exc}"

            ctx.check_results[plugin.name] = [
                {
                    "status": "fail",
                    "finding_type": "stage_exception",
                    "category": "TECHNICAL",
                    "severity": "BLOCKING",
                    "detail": diagnostics,
                }
            ]

            self.bus.emit(
                "stage.failed",
                plugin=plugin.name,
                error=diagnostics,
                context=ctx,
            )

            self.logger.log_invocation(
                plugin=plugin.name,
                input_ctx=snap,
                output_ctx=ctx,
                ok=False,
                diagnostics=diagnostics,
                duration_s=time.monotonic() - started,
            )

            write_self_correction_report(
                ctx,
                final_pass=False,
                repair_controller=self.repair_controller,
            )

            raise

    # ------------------------------------------------------------------
    # Repair
    # ------------------------------------------------------------------

    def _repair(
        self,
        ctx: SceneContext,
        plugin: Plugin,
        fails: list[dict[str, Any]],
    ) -> tuple[SceneContext, bool]:
        """Hand blocking scene findings to the controller, one scene at a time.

        Returns ``(context, whether any repair cycle ran)``.
        """

        if self.repair_controller is None:
            return ctx, False

        # Announce the failure for observers (progress UI, experiment
        # tooling). Nothing subscribed to this drives control flow any more.
        self.bus.emit(
            "check.failed",
            plugin=plugin.name,
            findings=fails,
            context=ctx,
            is_gate=plugin.is_gate(),
        )

        by_stem: dict[str, list[dict[str, Any]]] = {}

        for finding in fails:
            if not isinstance(finding, dict):
                continue

            stem = str(
                finding.get("stem") or finding.get("scene_id") or ""
            )

            if not lineage.is_scene_stem(stem):
                # Whole-video findings have no single scene to regenerate.
                continue

            by_stem.setdefault(stem, []).append(finding)

        repaired = False

        for stem, scene_findings in sorted(by_stem.items()):
            record = self.repair_controller.repair_scene(
                ctx,
                stem,
                scene_findings,
                plugin.name,
            )

            repaired = True

            if record.accepted:
                # The scene genuinely changed. Everything derived from it,
                # up to and including out/final.mp4, is now stale by
                # revision comparison rather than by heuristic.
                lineage.invalidate_scene(ctx, stem)

        return ctx, repaired

    # ------------------------------------------------------------------
    # Reachability invariant
    # ------------------------------------------------------------------

    def _check_final_video_reachable(
        self,
        ctx: SceneContext,
        halt_on_gate_failure: bool,
    ) -> None:
        """If scene gates passed, a current final.mp4 must exist.

        Deliberately enforced here rather than in ``qc.py`` so the
        standalone ``prompt2render check`` command keeps its existing
        behaviour of reporting a missing final video as SKIP -- checking
        layout/alignment on a partially-built project is a legitimate use.
        """

        if not (self.enforce_final_video and halt_on_gate_failure):
            return

        names = {plugin.name for plugin in self.plugins}

        if not (names & set(FINALIZATION_STAGES)):
            # No finish stage in this pipeline -- nothing was promised.
            return

        reason = self._finalization_problem(ctx)

        if reason is None:
            return

        write_self_correction_report(
            ctx,
            final_pass=False,
            repair_controller=self.repair_controller,
        )

        raise FinalizationFailure(reason)

    @staticmethod
    def _finalization_problem(ctx: SceneContext) -> str | None:
        """Why the programme is not shippable, or ``None`` if it is."""

        program = ctx.program

        if program is None:
            return (
                "every scene gate passed but no finish stage recorded a "
                "programme artifact -- out/final.mp4 was never produced"
            )

        if program.final_mp4 is None:
            return (
                "the finish stage ran but produced no out/final.mp4"
            )

        final = program.final_mp4

        if not final.exists():
            return f"out/final.mp4 is missing at {final}"

        try:
            size = final.stat().st_size
        except OSError as exc:
            return f"out/final.mp4 could not be inspected: {exc}"

        if size <= MIN_FINAL_BYTES:
            return (
                f"out/final.mp4 is {size} bytes, which is too small to be a "
                "valid encode"
            )

        if program.is_stale(ctx.scene_versions):
            expected = dict(ctx.scene_versions)
            built_from = dict(program.source_revisions)

            drifted = sorted(
                stem
                for stem in set(expected) | set(built_from)
                if expected.get(stem) != built_from.get(stem)
            )

            return (
                "out/final.mp4 was built from superseded scene revisions "
                f"(scenes {drifted} changed after it was produced); it "
                "cannot be treated as current"
            )

        return None

    # ------------------------------------------------------------------
    # Result bookkeeping
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(
        ctx: SceneContext,
        plugin: Plugin,
    ) -> None:
        """A stage that wrote nothing is recorded as a clean pass."""

        if plugin.name not in ctx.check_results:
            ctx.check_results[plugin.name] = [
                {
                    "status": "pass",
                    "finding_type": "stage_success",
                    "category": "TECHNICAL",
                    "severity": "INFO",
                    "detail": "stage completed successfully",
                }
            ]

    @staticmethod
    def _stamp_revisions(
        ctx: SceneContext,
        plugin: Plugin,
    ) -> None:
        """Tag this stage's scene-scoped findings with the scene revision.

        Done centrally so none of the eleven verifiers has to remember --
        the same reasoning that moved ``finding_type`` onto ``Finding``
        itself rather than asking each verifier to hand-add it.
        """

        results = ctx.check_results.get(plugin.name)

        if not isinstance(results, list):
            return

        for finding in results:
            if not isinstance(finding, dict):
                continue

            stem = finding.get("stem") or finding.get("scene_id")

            if lineage.is_scene_stem(stem):
                finding.setdefault(
                    "scene_revision",
                    lineage.current_revision(ctx, str(stem)),
                )

    @staticmethod
    def _failures(
        ctx: SceneContext,
        plugin: Plugin,
    ) -> list[dict[str, Any]]:
        """Return this plugin's blocking findings.

        Uses ``scene_quality.classify`` so the gate, the repair controller
        and the quality report all agree on what counts as blocking --
        including for the many verifiers that write plain dicts with no
        ``severity`` key.
        """

        results = ctx.check_results.get(plugin.name, [])

        if not isinstance(results, list):
            return [
                {
                    "status": "fail",
                    "finding_type": "invalid_check_result",
                    "category": "TECHNICAL",
                    "severity": "BLOCKING",
                    "detail": (
                        f"{plugin.name} produced non-list check_results."
                    ),
                }
            ]

        return [
            finding
            for finding in results
            if isinstance(finding, dict)
            and classify(finding) == "blocking"
        ]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def _history_entry(
    plugin: Plugin,
    ok: bool,
    *,
    suffix: str | None = None,
) -> HistoryEntry:
    name = plugin.name

    if suffix:
        name = f"{name}:{suffix}"

    return HistoryEntry(
        plugin=name,
        at=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        effects=list(
            plugin.declare_effects()
        ),
        ok=bool(ok),
    )


__all__ = [
    "FINALIZATION_STAGES",
    "FinalizationFailure",
    "GateFailure",
    "HarnessRunner",
]
