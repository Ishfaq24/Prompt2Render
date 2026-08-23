"""Orchestrates a resolved plugin order over one SceneContext.

Contract for a plugin's `run()`: raising means a hard crash (always fatal, regardless of
is_gate()). A soft failure — a verifier that found something wrong — is reported by appending
entries to `context.check_results[plugin.name]`, each a dict with at least a `status` key
(`"pass" | "warn" | "fail" | "skip"`). The runner treats any `"fail"` entry there as a
`check.failed` event; whether that halts the run depends on the plugin's `is_gate()`.
"""
from __future__ import annotations

import time

from .context import SceneContext, snapshot
from .events import EventBus
from .logging_ import StructuredLogger
from .plugin import Plugin


class GateFailure(RuntimeError):
    def __init__(self, plugin_name: str, findings: list[dict]):
        self.plugin_name = plugin_name
        self.findings = findings
        super().__init__(f"{plugin_name}: hard gate failed — {findings}")


class HarnessRunner:
    def __init__(self, plugins: list[Plugin], logger: StructuredLogger,
                 bus: EventBus | None = None):
        self.plugins = plugins
        self.logger = logger
        self.bus = bus or EventBus()

    def run(self, ctx: SceneContext, halt_on_gate_failure: bool = True) -> SceneContext:
        for plugin in self.plugins:
            ctx = self._run_one(plugin, ctx, halt_on_gate_failure=halt_on_gate_failure)
        return ctx

    def _run_one(self, plugin: Plugin, ctx: SceneContext, *,
                 halt_on_gate_failure: bool) -> SceneContext:
        snap = snapshot(ctx)
        self.bus.emit("stage.started", plugin=plugin.name)
        t0 = time.monotonic()
        ok = True
        diagnostics = ""
        try:
            ctx = plugin.run(ctx)
        except (Exception, SystemExit) as e:                      # noqa: BLE001
            # prompt2render's own modules (align.py, voice.py, scenes.py, stills.py, ...) use
            # `sys.exit(...)` — a SystemExit, not an Exception — as their idiom for an expected
            # fatal condition ("no build/master.wav — run `prompt2render voice` first"). A plugin wrapping
            # those calls needs this caught here too, or it would silently bypass logging and
            # blow straight through the harness process.
            ok = False
            diagnostics = f"{type(e).__name__}: {e}"
            self.bus.emit("stage.failed", plugin=plugin.name, error=diagnostics)
            self.logger.log_invocation(
                plugin=plugin.name, input_ctx=snap, output_ctx=snap,
                ok=False, diagnostics=diagnostics, duration_s=time.monotonic() - t0)
            raise

        fails = [f for f in ctx.check_results.get(plugin.name, [])
                 if f.get("status") == "fail"]
        if fails:
            # The bus is synchronous: if repair_router is subscribed, its handler runs — and may
            # mutate `ctx` in place — before emit() returns. So re-read check_results afterward
            # rather than trusting the `fails` snapshot taken before the emit.
            self.bus.emit("check.failed", plugin=plugin.name, findings=fails, context=ctx,
                          is_gate=plugin.is_gate())
            fails = [f for f in ctx.check_results.get(plugin.name, [])
                    if f.get("status") == "fail"]
        if fails:
            ok = False
            diagnostics = "; ".join(f.get("detail", "") for f in fails)
            if plugin.is_gate() and halt_on_gate_failure:
                self.logger.log_invocation(
                    plugin=plugin.name, input_ctx=snap, output_ctx=ctx,
                    ok=False, diagnostics=diagnostics, duration_s=time.monotonic() - t0)
                raise GateFailure(plugin.name, fails)

        ctx.history.append(_history_entry(plugin, ok))
        self.logger.log_invocation(
            plugin=plugin.name, input_ctx=snap, output_ctx=ctx,
            ok=ok, diagnostics=diagnostics, duration_s=time.monotonic() - t0)
        return ctx


def _history_entry(plugin: Plugin, ok: bool):
    from .context import HistoryEntry
    return HistoryEntry(
        plugin=plugin.name,
        at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        effects=plugin.declare_effects(),
        ok=ok,
    )
