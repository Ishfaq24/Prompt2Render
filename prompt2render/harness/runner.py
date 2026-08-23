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
"""

from __future__ import annotations

import time
from typing import Any

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
        """Run all resolved plugins in order."""

        for plugin in self.plugins:
            ctx = self._run_one(
                plugin,
                ctx,
                halt_on_gate_failure=halt_on_gate_failure,
            )

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
    ) -> SceneContext:
        """Execute, optionally repair, and re-verify one plugin."""

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

        # If the verifier's successful result contains no scene information,
        # do not guess that every repair is now safe to clear.
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