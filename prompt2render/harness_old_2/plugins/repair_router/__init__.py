"""Stage 4: the real repair_router, generalizing scenes.py generate()'s existing inline retry
loop (single-purpose: spatial_conflict -> generator_code, max_retries=3) into the general
event-driven mechanism the migration brief specifies.

Not an ordinary pipeline stage — see loader.build_repair_router(), which excludes it from the
resolve_order pipeline. It's attached directly to the harness's event bus and reacts to
`check.failed` events emitted by HarnessRunner._run_one(), synchronously, before the runner
decides whether a hard gate should halt the run — so a successful repair can turn a would-be
GateFailure into a pass within the same plugin invocation.

Known limitation, stated rather than hidden: for `spatial_conflict` (the one finding type with
real, working detection today — verifier_spatial), this will rarely actually trigger in practice.
scenes.py generate()'s own internal accept/reject loop already resolves layout conflicts before a
section is ever recorded as "accepted" — so by the time verifier_spatial runs, code_artifacts are
already past that gate. This router is real and load-bearing for when verifier_semantic /
verifier_lifecycle grow real detection logic (both currently stubs, per Stage 3), and it's fully
exercised by tests/harness/test_repair_router.py with dummy plugins — but it is not something a
`hash-tables` harness run today will visibly exercise.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ...context import SceneContext
from ...events import Event, EventBus
from ...plugin import Plugin
from .policy import RoutingPolicy, StaticTableRoutingPolicy

#: source verifier plugin name -> the finding_type its failures are routed under. A verifier can
#: override this by putting an explicit "finding_type" key on its own finding dicts.
_DEFAULT_FINDING_TYPE = {
    "verifier_spatial": "spatial_conflict",
    "verifier_semantic": "semantic_mismatch",
    "verifier_lifecycle": "lifecycle_violation",
    "verifier_audio": "audio_visual_mismatch",
}


class RepairRouterPlugin(Plugin):
    name = "repair_router"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.max_repair_cycles = int(self.config.get("max_repair_cycles", 3))
        self.policy: RoutingPolicy = StaticTableRoutingPolicy(self.config.get("routing_table"))
        self._cycles_used: dict[str, int] = {}
        self._plugins_by_name: dict[str, Plugin] = {}
        self._log_path: Path | None = None
        self._cycle_id = 0

    def declare_dependencies(self) -> list[str]:
        return ["check_results", "history"]

    def declare_effects(self) -> list[str]:
        return []

    def run(self, context: SceneContext) -> SceneContext:
        return context   # never called as an ordinary stage — see module docstring

    def _default_gate(self) -> bool:
        return False

    # ------------------------------------------------------------------------------- wiring --

    def attach(self, *, bus: EventBus, plugins_by_name: dict[str, Plugin],
              log_path: Path) -> None:
        """Wire this router into a live run. Needs the actual plugin instances (to revert/re-run
        the ones a routing decision targets) — the event payload alone isn't enough."""
        self._plugins_by_name = plugins_by_name
        self._log_path = log_path
        bus.subscribe("check.failed", self._on_check_failed)

    def subscribe(self, bus: EventBus) -> None:
        # Superseded by attach(), which also needs plugin instances + a log path that a bare
        # EventBus reference can't supply. Kept only so callers matching the Stage 3 stub
        # interface don't break; does nothing on its own.
        return

    # --------------------------------------------------------------------------- the cycle --

    def _on_check_failed(self, event: Event) -> None:
        source = event.payload["plugin"]
        ctx: SceneContext = event.payload["context"]
        findings = event.payload["findings"]
        source_is_gate = event.payload.get("is_gate", True)

        for finding in findings:
            self._repair_one(source, finding, ctx, source_is_gate)

    def _repair_one(self, source: str, finding: dict, ctx: SceneContext,
                    source_is_gate: bool) -> None:
        """The runner emits check.failed exactly once per failing plugin invocation — so the
        per-scene retry budget (max_repair_cycles) is a loop *within* this one handler call, not
        something a caller re-triggers.
        """
        finding_type = finding.get("finding_type") or _DEFAULT_FINDING_TYPE.get(source, source)
        scene_id = finding.get("stem") or finding.get("scene_id") or "__all__"
        routed_finding = {**finding, "finding_type": finding_type, "scene_id": scene_id,
                          "source_plugin": source}
        targets = self.policy.decide(routed_finding)
        cycles_key = f"{scene_id}:{source}"

        if not targets:
            self._log_cycle(scene_id, finding_type, routed_finding.get("mismatch_subtype"),
                            routed_to=[], diagnostic_message=finding.get("detail", ""),
                            pre_hash=_hash(ctx), post_hash=_hash(ctx), outcome="unresolved",
                            cycles_used=self._cycles_used.get(cycles_key, 0))
            return

        resolved = False
        while self._cycles_used.get(cycles_key, 0) < self.max_repair_cycles:
            used = self._cycles_used.get(cycles_key, 0) + 1
            self._cycles_used[cycles_key] = used
            pre_hash = _hash(ctx)

            ctx.repair_context.setdefault(scene_id, []).append(finding.get("detail", ""))
            attempt_ok = True
            for target_name in targets:
                target = self._plugins_by_name.get(target_name)
                if target is None:
                    attempt_ok = False
                    continue
                try:
                    if hasattr(target, "revert_scene") and hasattr(target, "regenerate_one"):
                        target.revert_scene(ctx, scene_id)
                        target.regenerate_one(ctx, scene_id)
                    else:
                        target.run(ctx)   # generic fallback — no per-scene granularity available
                except (Exception, SystemExit):
                    attempt_ok = False

            post_hash = _hash(ctx)
            outcome = "resolved" if attempt_ok else "unresolved"
            self._log_cycle(scene_id, finding_type, routed_finding.get("mismatch_subtype"),
                            routed_to=targets, diagnostic_message=finding.get("detail", ""),
                            pre_hash=pre_hash, post_hash=post_hash, outcome=outcome,
                            cycles_used=used)
            if attempt_ok:
                resolved = True
                break

        if resolved:
            # Mark this finding resolved in place — it's the same dict object the runner's
            # `fails` list references, so the runner's post-emit re-check sees it.
            finding["status"] = "resolved"
        else:
            self._log_cycle(scene_id, finding_type, routed_finding.get("mismatch_subtype"),
                            routed_to=targets, diagnostic_message=finding.get("detail", ""),
                            pre_hash=_hash(ctx), post_hash=_hash(ctx), outcome="gave_up",
                            cycles_used=self._cycles_used.get(cycles_key, 0))
            if not source_is_gate:
                # Budget exhausted, soft gate: demote to an open, non-blocking defect rather
                # than leaving `status: fail` (which would otherwise halt the scene on the
                # runner's post-emit re-check regardless of is_gate()).
                finding["status"] = "open_defect"
            # Hard gate: leave `status: fail` in place so the runner halts the scene.

    # -------------------------------------------------------------------------------- log --

    def _log_cycle(self, scene_id, finding_type, mismatch_subtype, *, routed_to,
                  diagnostic_message, pre_hash, post_hash, outcome, cycles_used) -> None:
        if self._log_path is None:
            return
        self._cycle_id += 1
        record = {
            "cycle_id": self._cycle_id,
            "scene_id": scene_id,
            "finding_type": finding_type,
            "mismatch_subtype": mismatch_subtype,
            "routed_to": routed_to,
            "diagnostic_message": diagnostic_message,
            "pre_repair_context_hash": pre_hash,
            "post_repair_context_hash": post_hash,
            "outcome": outcome,
            "cycles_used": cycles_used,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def _hash(ctx: SceneContext) -> str:
    from ...logging_ import context_hash
    return context_hash(ctx)
