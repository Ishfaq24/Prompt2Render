"""Pipeline runner for the Prompt2Render harness.

The runner executes an already-resolved plugin DAG over one SceneContext.

Plugin execution has two failure classes:

1. Hard execution failure:
   ``plugin.run()`` raises. This is always fatal for that invocation,
   regardless of the plugin's gate setting.

2. Soft verification failure:
   ``plugin.run()`` returns normally but writes one or more ``status == "fail"``
   entries to ``context.check_results[plugin.name]``. These are emitted as
   ``check.failed`` events. The EventBus/repair_router may synchronously repair
   the affected scene and mark the finding resolved. The runner then
   re-verifies the original verifier rather than trusting the repair router.

The runner owns orchestration and gate policy. Repair policy remains in
``repair_router`` and ``RoutingPolicy``.

Tier 3 Phase 14 ("verifier-driven repair with regression detection") adds
one more trigger source to the rewind loop below: ``regression.
scene_fingerprints``/``changed_stems`` (see ``regression.py`` for the
structural gap this closes and an honest note on why it is a forward-looking
safety net today rather than a fix for a currently-live bug). Purely
additive: it only ever widens ``trigger``, never narrows it, so it cannot
change any existing gate/rewind decision by itself -- it can only cause
*more* re-verification to happen in a case that would otherwise silently
skip it.
"""

from __future__ import annotations

import time
from typing import Any

from . import regression
from .context import HistoryEntry, SceneContext, snapshot
from .events import EventBus
from .logging_ import (
    StructuredLogger,
    write_self_correction_report,
)
from .plugin import Plugin


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


class HarnessRunner:
    """Execute a resolved plugin pipeline."""

    DEFAULT_MAX_REVERIFY_ATTEMPTS = 3

    def __init__(
        self,
        plugins: list[Plugin],
        logger: StructuredLogger,
        bus: EventBus | None = None,
        *,
        max_reverify_attempts: int = DEFAULT_MAX_REVERIFY_ATTEMPTS,
    ) -> None:
        self.plugins = list(
            plugins
        )
        self.logger = logger
        self.bus = bus or EventBus()

        self.max_reverify_attempts = max(
            0,
            int(
                max_reverify_attempts
            ),
        )

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        ctx: SceneContext,
        halt_on_gate_failure: bool = True,
    ) -> SceneContext:
        """Run all resolved plugins in order.

        If a repair cycle mutates earlier artifacts (e.g. generator_code /
        generator_manim), the pipeline MUST rewind to the earliest producer of
        ``code_artifacts`` and re-execute the full chain:

            generator -> verifier_execution -> renderer -> verifier_temporal
            -> verifier_semantic -> feedback_hitl (and any other gates)

        The previous heuristic scanned only consumers of ``code_artifacts`` /
        ``render_artifacts``.  ``generator_manim`` declares dependencies on
        ``scene_plan``/``narration`` and therefore was never found, so a HITL
        regeneration of sections 01/07 would mark the finding "resolved" but
        never re-render or re-verify before assembly.  This implementation
        searches for *producers* of ``code_artifacts`` (including the canonical
        names ``generator_manim``/``generator_code``) and falls back to the
        earliest ``scene_plan`` producer, guaranteeing stale assembly is
        impossible.
        """

        i = 0
        # Prevent infinite rewind loops but allow HITL to trigger the same
        # stems again when hitl_feedback.json still lists them as reject
        # (user explicitly said same file should cause regeneration again).
        # Each distinct (plugin_index, frozenset) may rewind up to 3 times.
        seen_rewinds: dict[tuple[int, frozenset[str]], int] = {}
        MAX_SAME_REWINDS = 3
        total_rewinds = 0
        MAX_TOTAL_REWINDS = 10

        while i < len(self.plugins):
            plugin = self.plugins[i]

            before_repair_stems = set(ctx.repair_context.keys())
            before_render_keys = set(ctx.render_artifacts.keys())
            before_fingerprints = regression.scene_fingerprints(ctx)

            ctx = self._run_one(
                plugin,
                ctx,
                halt_on_gate_failure=halt_on_gate_failure,
                plugin_index=i,
            )

            after_repair_stems = set(ctx.repair_context.keys())
            new_repairs = after_repair_stems - before_repair_stems
            # A revert_scene() pops the stale render artifact when a repair
            # is routed to a code generator. IMPORTANT: this must NOT be
            # gated on ``s in after_repair_stems`` (repair_context
            # membership). The success path of ``_run_one`` — via
            # ``_clear_verified_repair_context`` — pops a stem's
            # repair_context entry as soon as the *current* plugin
            # re-verifies clean, which happens before we get back here. For
            # a repair surfaced by a verifier that runs *after*
            # renderer_manim (verifier_semantic/_lifecycle/_spatial/_temporal,
            # feedback_hitl) and whose own re-check then passes, that pop
            # erased the only signal this loop used to have, so the rewind
            # back to renderer_manim never fired and a freshly regenerated
            # scene kept its stale, pre-fix render. Comparing render_artifacts
            # key sets directly is immune to that: it only fires when a
            # render that existed before this stage genuinely no longer does.
            stale_renders = before_render_keys - set(ctx.render_artifacts.keys())
            # Also trigger if a pending stem has no manifest (render not yet redone)
            missing_renders = {
                s for s in after_repair_stems
                if s not in ctx.render_artifacts
                or not getattr(ctx.render_artifacts.get(s, None), "manifest", None)
            }
            trigger = new_repairs | stale_renders | missing_renders

            # Tier 3 Phase 14: a repair routed to a plugin without
            # regenerate_one/revert_scene degrades to a full target.run(ctx)
            # (SS15 implicit contract #2), which can silently rewrite an
            # unrelated stem's authored content without touching
            # repair_context/render_artifacts at all -- the three triggers
            # above would never see it. Detect that directly and widen
            # trigger; this can only add stems, never remove any of the
            # above.
            after_fingerprints = regression.scene_fingerprints(ctx)
            silently_changed = regression.changed_stems(
                before_fingerprints, after_fingerprints
            )
            regression_detected = silently_changed - trigger

            if regression_detected:
                self.logger.info(
                    f"Regression detected at {plugin.name}: repair "
                    f"silently changed {sorted(regression_detected)} "
                    "without registering them via repair_context/"
                    "render_artifacts -- widening rewind scope to "
                    "re-verify them too."
                )

            trigger = trigger | regression_detected

            if trigger:
                # Rewind to the earliest *consumer* of code/render artifacts
                # that has already executed.  The repair_router has already
                # produced fresh code via revert+regenerate, so we need to
                # re-run the downstream chain:
                #   verifier_execution -> renderer_manim -> verifier_temporal
                #   -> verifier_semantic -> feedback_hitl
                # Rewinding to the generator would duplicate the LLM call.
                rewind_idx = self._rewind_target_index(i)

                if rewind_idx < i:
                    key = (rewind_idx, frozenset(sorted(trigger)))
                    cnt = seen_rewinds.get(key, 0)
                    if cnt >= MAX_SAME_REWINDS or total_rewinds >= MAX_TOTAL_REWINDS:
                        self.logger.info(
                            f"Rewind loop detected for {sorted(trigger)} at {self.plugins[rewind_idx].name} "
                            f"(cnt={cnt}, total={total_rewinds}); not rewinding again — surfacing gate failure."
                        )
                    else:
                        seen_rewinds[key] = cnt + 1
                        total_rewinds += 1
                        # Invalidate downstream check_results for the affected
                        # stems so verifiers cannot pass on stale cached
                        # findings.  Only the stale stems are cleared; other
                        # stems keep their passing evidence.
                        for pname in [q.name for q in self.plugins[rewind_idx:]]:
                            if pname in ctx.check_results:
                                remaining = [
                                    r for r in ctx.check_results[pname]
                                    if not isinstance(r, dict) or str(r.get("stem") or r.get("scene_id") or "") not in trigger
                                ]
                                # If the only findings were for the stale stems,
                                # remove the entry entirely so the verifier re-runs.
                                if len(remaining) != len(ctx.check_results[pname]):
                                    if remaining:
                                        ctx.check_results[pname] = remaining
                                    else:
                                        ctx.check_results.pop(pname, None)
                        self.logger.info(
                            f"Rewinding pipeline from {plugin.name} to {self.plugins[rewind_idx].name} "
                            f"to re-process repaired scenes: {sorted(trigger)} (rewind #{total_rewinds})"
                        )
                        i = rewind_idx
                        continue

            i += 1

        return ctx

    # ------------------------------------------------------------------
    # Rewind targeting
    # ------------------------------------------------------------------

    def _rewind_target_index(self, plugin_index: int) -> int:
        """Return the earliest index before ``plugin_index`` worth replaying.

        A rewind target is a plugin that either consumes ``code_artifacts``/
        ``render_artifacts`` or produces ``code_artifacts`` (the canonical
        generator stages). When none exists before ``plugin_index`` — e.g. a
        repair to an upstream planning/verification stage like
        ``verifier_storyboard``, which sits before any code generator even
        appears in the pipeline — this returns ``plugin_index`` unchanged,
        signalling "no rewind is possible here".
        """

        rewind_idx = plugin_index

        for j, p in enumerate(self.plugins[:plugin_index]):
            deps = p.declare_dependencies() or []
            if "code_artifacts" in deps or "render_artifacts" in deps:
                rewind_idx = min(rewind_idx, j)

        # Fallback: if no consumer was found (e.g. stripped Manim config),
        # rewind to the earliest code producer.
        if rewind_idx == plugin_index:
            for j, p in enumerate(self.plugins[:plugin_index]):
                eff = p.declare_effects() or []
                if "code_artifacts" in eff or p.name in ("generator_manim", "generator_code"):
                    rewind_idx = min(rewind_idx, j)

        return rewind_idx

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
        """Execute, optionally repair, and re-verify one plugin."""

        # Stems already present in repair_context before this plugin does
        # anything. Used as a fallback in _clear_verified_repair_context
        # when a successful result carries no stem info at all: any stem
        # that appeared in repair_context ONLY during this invocation was
        # necessarily added by this same plugin's own failure (see below),
        # so a since-confirmed clean re-verification can safely clear it —
        # without guessing about unrelated stems that were already pending.
        repair_keys_before_run = set(
            ctx.repair_context.keys()
        )

        snap = snapshot(
            ctx
        )

        self.bus.emit(
            "stage.started",
            plugin=plugin.name,
        )

        started = time.monotonic()
        ok = True
        diagnostics = ""

        # --------------------------------------------------------------
        # Forward execution
        # --------------------------------------------------------------

        try:
            result = plugin.run(
                ctx
            )

            if result is not None:
                if not isinstance(
                    result,
                    SceneContext,
                ):
                    raise TypeError(
                        f"{plugin.name}.run() returned "
                        f"{type(result).__name__}; "
                        "expected SceneContext."
                    )

                ctx = result

        except (
            Exception,
            SystemExit,
        ) as exc:
            # SystemExit is deliberately included because existing
            # prompt2render modules use it for expected fatal configuration
            # conditions.
            ok = False

            diagnostics = (
                f"{type(exc).__name__}: {exc}"
            )

            ctx.check_results[
                plugin.name
            ] = [
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
                duration_s=(
                    time.monotonic()
                    - started
                ),
            )

            write_self_correction_report(
                ctx,
                final_pass=False,
            )

            raise

        # --------------------------------------------------------------
        # Normalize missing check results
        # --------------------------------------------------------------

        if plugin.name not in ctx.check_results:
            ctx.check_results[
                plugin.name
            ] = [
                {
                    "status": "pass",
                    "finding_type": "stage_success",
                    "category": "TECHNICAL",
                    "severity": "INFO",
                    "detail": "stage completed successfully",
                }
            ]

        fails = self._failures(
            ctx,
            plugin,
        )

        # --------------------------------------------------------------
        # Repair/re-verification loop
        # --------------------------------------------------------------

        reverify_attempts = 0

        while fails:
            before_repairs = len(
                ctx.repair_records
            )

            # EventBus is synchronous, so a repair_router subscribed to
            # check.failed gets a chance to repair before emit() returns.
            self.bus.emit(
                "check.failed",
                plugin=plugin.name,
                findings=fails,
                context=ctx,
                is_gate=plugin.is_gate(),
            )

            after_repairs = len(
                ctx.repair_records
            )

            resolved = any(
                isinstance(
                    finding,
                    dict,
                )
                and finding.get(
                    "status"
                )
                == "resolved"
                for finding in fails
            )

            repair_happened = (
                after_repairs
                > before_repairs
            )

            # A router may choose to mutate the finding to "resolved", but
            # the authoritative test is still the verifier rerun. If a
            # router repaired the scene without mutating the finding, the
            # repair-record delta still allows one re-verification attempt.
            if not (
                resolved
                or repair_happened
            ):
                break

            new_records = ctx.repair_records[before_repairs:]

            # The router has already exhausted its own repair budget for
            # this finding (outcome "gave_up"). The finding's status is left
            # untouched in that case (still "fail" for a hard gate), so
            # reverifying here would just re-observe the identical failure
            # and burn through max_reverify_attempts producing more useless
            # "gave_up" cycles before the gate check below finally fires.
            if any(r.get("outcome") == "gave_up" for r in new_records):
                break

            # If the repair was routed to an earlier stage (like generator_code),
            # we must break out of this plugin's internal re-verification loop
            # and let the outer pipeline loop rewind. We can detect this by checking
            # if the router added new scenes to repair_context.
            #
            # This is only safe when the outer loop actually HAS a rewind
            # target to replay back to. A repair routed to a stage upstream
            # of any code/render-artifact producer (e.g. verifier_storyboard
            # repairing via planner_llm, long before generator_code even
            # appears in the pipeline) has no such target — _rewind_target_index
            # would return plugin_index unchanged and the outer loop's `if
            # rewind_idx < i` never fires. Breaking here anyway would let a
            # router's optimistic "resolved" mutation stand as this plugin's
            # final verdict without ever re-running plugin.run() to confirm
            # it, so context fields the plugin itself sets (like
            # storyboard_verified) stay stale even though check_results
            # claims success. Falling through to the reverify-in-place path
            # below is the only way to get an authoritative result in that
            # case.
            if (
                any(r.get("routed_to") for r in new_records)
                and self._rewind_target_index(plugin_index) < plugin_index
            ):
                break

            if (
                reverify_attempts
                >= self.max_reverify_attempts
            ):
                diagnostics = (
                    f"maximum re-verification attempts "
                    f"({self.max_reverify_attempts}) "
                    f"exhausted"
                )
                break

            reverify_attempts += 1

            # Never trust the router's "resolved" claim. Clear this verifier's
            # previous result and execute it again against the repaired
            # artifacts.
            ctx.check_results[
                plugin.name
            ] = []

            reverify_started = time.monotonic()

            try:
                result = plugin.run(
                    ctx
                )

                if result is not None:
                    if not isinstance(
                        result,
                        SceneContext,
                    ):
                        raise TypeError(
                            f"{plugin.name}.run() returned "
                            f"{type(result).__name__}; "
                            "expected SceneContext."
                        )

                    ctx = result

            except (
                Exception,
                SystemExit,
            ) as exc:
                diagnostics = (
                    f"Re-verification crashed: "
                    f"{type(exc).__name__}: {exc}"
                )

                ctx.check_results[
                    plugin.name
                ] = [
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
                    re_verification=True,
                )

                fails = self._failures(
                    ctx,
                    plugin,
                )
                break

            fails = self._failures(
                ctx,
                plugin,
            )

            # Record re-verification in history separately from the original
            # invocation. This makes the evidence layer honest about how many
            # executions actually occurred.
            ctx.history.append(
                _history_entry(
                    plugin,
                    ok=not bool(fails),
                    suffix=(
                        f"reverify_{reverify_attempts}"
                    ),
                )
            )

            # Defensive diagnostic if a repair consumed a cycle but produced
            # exactly the same failing result.
            if (
                fails
                and not repair_happened
                and not resolved
            ):
                break

            # Avoid an unused local while retaining the measurement for future
            # instrumentation.
            _ = reverify_started

        # --------------------------------------------------------------
        # Final gate decision
        # --------------------------------------------------------------

        # Re-evaluate fails because if we broke out of the loop early to rewind,
        # the original fails list might contain findings that were provisionally marked 'resolved'
        fails = self._failures(ctx, plugin)
        
        if fails:
            ok = False

            diagnostics = diagnostics or "; ".join(
                str(
                    finding.get(
                        "detail",
                        finding.get(
                            "message",
                            "",
                        ),
                    )
                )
                for finding in fails
            )

            if (
                plugin.is_gate()
                and halt_on_gate_failure
            ):
                self.logger.log_invocation(
                    plugin=plugin.name,
                    input_ctx=snap,
                    output_ctx=ctx,
                    ok=False,
                    diagnostics=diagnostics,
                    duration_s=(
                        time.monotonic()
                        - started
                    ),
                )

                write_self_correction_report(
                    ctx,
                    final_pass=False,
                )

                raise GateFailure(
                    plugin.name,
                    fails,
                )

        else:
            # Do not clear all repair context. Other scenes may still have
            # unresolved repair state belonging to another verifier.
            self._clear_verified_repair_context(
                ctx,
                plugin,
                repair_keys_before_run,
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
            duration_s=(
                time.monotonic()
                - started
            ),
        )

        return ctx

    # ------------------------------------------------------------------
    # Finding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _failures(
        ctx: SceneContext,
        plugin: Plugin,
    ) -> list[dict[str, Any]]:
        """Return normalized fail findings for one plugin."""

        results = ctx.check_results.get(
            plugin.name,
            [],
        )

        if not isinstance(
            results,
            list,
        ):
            return [
                {
                    "status": "fail",
                    "finding_type": "invalid_check_result",
                    "category": "TECHNICAL",
                    "severity": "BLOCKING",
                    "detail": (
                        f"{plugin.name} produced non-list "
                        "check_results."
                    ),
                }
            ]

        return [
            finding
            for finding in results
            if isinstance(
                finding,
                dict,
            )
            and str(
                finding.get(
                    "status",
                    ""
                )
            ).lower()
            == "fail"
        ]

    @staticmethod
    def _clear_verified_repair_context(
        ctx: SceneContext,
        plugin: Plugin,
        repair_keys_before_run: set[str],
    ) -> None:
        """Clear repair context only for scenes actually verified successfully.

        A verifier may emit a clean result for only part of the pipeline, so
        clearing every scene's repair context is unsafe.
        """

        affected: set[str] = set()

        for result in ctx.check_results.get(
            plugin.name,
            [],
        ):
            if not isinstance(
                result,
                dict,
            ):
                continue

            stem = (
                result.get("stem")
                or result.get("scene_id")
            )

            if stem:
                affected.add(
                    str(stem)
                )

        if not affected:
            # The verifier's successful result carries no scene information
            # at all (a global/aggregate pass, e.g. verifier_storyboard's
            # all-clean case) — do not guess that every OTHER pending repair
            # is now safe to clear. But any stem that appeared in
            # repair_context only DURING this plugin's own run necessarily
            # came from this same plugin's own earlier failure in this
            # invocation (see repair_keys_before_run in _run_one), so a
            # since-confirmed clean re-verification can safely clear those
            # specific entries without touching unrelated pending repairs.
            affected = set(ctx.repair_context.keys()) - repair_keys_before_run

        if not affected:
            return

        for stem in affected:
            ctx.repair_context.pop(
                stem,
                None,
            )


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
        name = (
            f"{name}:{suffix}"
        )

    return HistoryEntry(
        plugin=name,
        at=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        effects=list(
            plugin.declare_effects()
        ),
        ok=bool(
            ok
        ),
    )


__all__ = [
    "GateFailure",
    "HarnessRunner",
]