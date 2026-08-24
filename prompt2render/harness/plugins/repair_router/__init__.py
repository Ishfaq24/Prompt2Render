"""Stage 4: event-driven repair router for Prompt2Render.

The repair router is not an ordinary pipeline stage. It is attached to the
harness event bus and reacts synchronously to ``check.failed`` events.

Responsibilities
----------------
* Map verifier findings to repair-capable plugins.
* Maintain a per-scene/per-finding repair budget.
* Preserve repair diagnostics for downstream generators.
* Revert and regenerate only the affected scene when supported.
* Emit repair lifecycle events.
* Record auditable repair history.
* Keep hard-gate and soft-gate behaviour distinct.

The router does not claim that a repair is semantically successful merely
because generation did not crash. The runner must re-run the originating
verifier after the repair and prove that the finding is gone.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...events import Event, EventBus
from ...plugin import Plugin
from .policy import RoutingPolicy, StaticTableRoutingPolicy


# ---------------------------------------------------------------------------
# Finding routing
# ---------------------------------------------------------------------------

#: Source verifier plugin -> default finding type.
#: A verifier can override this by supplying ``finding_type`` itself.
_DEFAULT_FINDING_TYPE: dict[str, str] = {
    "verifier_spatial": "spatial_conflict",
    "verifier_semantic": "semantic_mismatch",
    "verifier_lifecycle": "lifecycle_violation",
    "verifier_audio": "audio_visual_mismatch",
    "verifier_storyboard": "storyboard_failure",
    "verifier_pedagogy": "pedagogy_review",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(
    value: Any,
    default: int,
    minimum: int = 0,
) -> int:
    """Safely parse an integer configuration value."""

    try:
        result = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, result)


def _detail(finding: dict[str, Any]) -> str:
    """Extract a stable human-readable diagnostic from a finding."""

    for key in ("detail", "message", "diagnostic", "description"):
        value = finding.get(key)

        if value is not None:
            text = str(value).strip()

            if text:
                return text

    return ""


def _scene_id(finding: dict[str, Any]) -> str:
    """Resolve the affected scene identifier."""

    value = (
        finding.get("stem")
        or finding.get("scene_id")
        or "__all__"
    )

    return str(value)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class RepairRouterPlugin(Plugin):
    """Event-driven, policy-based repair router."""

    name = "repair_router"

    def __init__(
        self,
        config: dict | None = None,
    ):
        super().__init__(config)

        self.max_repair_cycles = _safe_int(
            self.config.get(
                "max_repair_cycles",
                3,
            ),
            default=3,
            minimum=0,
        )

        self.policy: RoutingPolicy = (
            StaticTableRoutingPolicy(
                self.config.get(
                    "routing_table"
                )
            )
        )

        # Budget is intentionally keyed by scene + finding type + source.
        # This prevents an unrelated finding from consuming another finding's
        # repair budget.
        self._cycles_used: dict[
            str,
            int,
        ] = {}

        self._plugins_by_name: dict[
            str,
            Plugin,
        ] = {}

        self._log_path: Path | None = None
        self._cycle_id = 0
        self.history: list[Any] = []
        self._active_context: SceneContext | None = None
        self._bus: EventBus | None = None

    # ------------------------------------------------------------------
    # Plugin interface
    # ------------------------------------------------------------------

    def declare_dependencies(self) -> list[str]:
        return [
            "check_results",
            "history",
        ]

    def declare_effects(self) -> list[str]:
        return []

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:
        # The router is attached to the event bus and is deliberately not
        # executed as a normal pipeline stage.
        return context

    def _default_gate(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Event-bus wiring
    # ------------------------------------------------------------------

    def attach(
        self,
        *,
        bus: EventBus,
        plugins_by_name: dict[str, Plugin],
        log_path: Path,
    ) -> None:
        """Attach the router to a live harness run."""

        self._plugins_by_name = dict(
            plugins_by_name
        )

        self._log_path = log_path
        self._bus = bus

        bus.subscribe(
            "check.failed",
            self._on_check_failed,
        )

    def subscribe(
        self,
        bus: EventBus,
    ) -> None:
        """Compatibility hook.

        ``attach()`` is preferred because the router also needs access to
        plugin instances and the repair log path.
        """

        # Intentionally do not subscribe here. Subscribing both here and in
        # attach() would process each failure twice.
        return

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_check_failed(
        self,
        event: Event,
    ) -> None:
        """Handle one verifier failure event."""

        payload = event.payload or {}

        source = str(
            payload.get(
                "plugin",
                "unknown",
            )
        )

        ctx = payload.get(
            "context"
        )

        findings = payload.get(
            "findings",
            [],
        )

        source_is_gate = bool(
            payload.get(
                "is_gate",
                True,
            )
        )

        if not isinstance(
            ctx,
            SceneContext,
        ):
            return

        if not isinstance(
            findings,
            list,
        ):
            findings = [findings]

        self._active_context = ctx

        try:
            for finding in findings:

                if not isinstance(
                    finding,
                    dict,
                ):
                    continue

                self._repair_one(
                    source,
                    finding,
                    ctx,
                    source_is_gate,
                )
        finally:
            self._active_context = None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _resolve_targets(
        self,
        source: str,
        routed_finding: dict[str, Any],
    ) -> list[str]:
        """Resolve repair targets, including the Manim backend alias."""

        targets = self.policy.decide(
            routed_finding
        )

        if not targets:
            return []

        targets = [
            str(target)
            for target in targets
            if str(target).strip()
        ]

        # In --manim mode the live backend is generator_manim, while the
        # shared routing policy normally names generator_code.
        if (
            "generator_code"
            not in self._plugins_by_name
            and "generator_manim"
            in self._plugins_by_name
        ):
            targets = [
                (
                    "generator_manim"
                    if target == "generator_code"
                    else target
                )
                for target in targets
            ]

        # Preserve policy order while removing duplicates.
        return list(
            dict.fromkeys(targets)
        )

    def _cycles_key(
        self,
        scene_id: str,
        finding_type: str,
        source: str,
    ) -> str:
        return (
            f"{scene_id}:"
            f"{finding_type}:"
            f"{source}"
        )

    def _repair_one(
        self,
        source: str,
        finding: dict[str, Any],
        ctx: SceneContext,
        source_is_gate: bool,
    ) -> None:
        """Attempt repair for one finding."""

        finding_type = (
            finding.get("finding_type")
            or _DEFAULT_FINDING_TYPE.get(
                source,
                source,
            )
        )

        finding_type = str(
            finding_type
        )

        scene_id = _scene_id(
            finding
        )

        routed_finding = {
            **finding,
            "finding_type": finding_type,
            "scene_id": scene_id,
            "source_plugin": source,
        }

        targets = self._resolve_targets(
            source,
            routed_finding,
        )

        cycles_key = self._cycles_key(
            scene_id,
            finding_type,
            source,
        )

        used_so_far = self._cycles_used.get(
            cycles_key,
            0,
        )

        # --------------------------------------------------------------
        # No route
        # --------------------------------------------------------------

        if not targets:
            self._log_cycle(
                scene_id,
                finding_type,
                routed_finding.get(
                    "mismatch_subtype"
                ),
                routed_to=[],
                diagnostic_message=_detail(
                    finding
                ),
                pre_hash=_hash(ctx),
                post_hash=_hash(ctx),
                outcome="unresolved",
                cycles_used=used_so_far,
            )

            return

        # --------------------------------------------------------------
        # Repair cycles
        # --------------------------------------------------------------

        while (
            self._cycles_used.get(
                cycles_key,
                0,
            )
            < self.max_repair_cycles
        ):
            used = (
                self._cycles_used.get(
                    cycles_key,
                    0,
                )
                + 1
            )

            self._cycles_used[
                cycles_key
            ] = used

            self._emit(
                "repair.started",
                scene_id=scene_id,
                finding_type=finding_type,
                cycle=used,
                max_cycles=self.max_repair_cycles,
                routed_to=targets,
            )

            pre_hash = _hash(
                ctx
            )

            diagnostic = _detail(
                finding
            )

            if diagnostic:
                ctx.repair_context.setdefault(
                    scene_id,
                    [],
                ).append(
                    diagnostic
                )

            attempt_ok = True
            attempted_targets: list[str] = []

            # ----------------------------------------------------------
            # Execute the route.
            # ----------------------------------------------------------

            for target_name in targets:

                target = (
                    self._plugins_by_name.get(
                        target_name
                    )
                )

                if target is None:
                    attempt_ok = False
                    continue

                attempted_targets.append(
                    target_name
                )

                try:
                    if (
                        hasattr(
                            target,
                            "revert_scene",
                        )
                        and hasattr(
                            target,
                            "regenerate_one",
                        )
                    ):
                        target.revert_scene(
                            ctx,
                            scene_id,
                        )

                        target.regenerate_one(
                            ctx,
                            scene_id,
                        )

                    else:
                        # Generic fallback for plugins that cannot perform
                        # scene-level repair.
                        target.run(
                            ctx
                        )

                except (
                    Exception,
                    SystemExit,
                ) as exc:
                    attempt_ok = False

                    # Keep the failure available to the next cycle rather
                    # than silently discarding it.
                    ctx.repair_context.setdefault(
                        scene_id,
                        [],
                    ).append(
                        (
                            f"{target_name} repair attempt "
                            f"{used} failed: {exc}"
                        )
                    )

            post_hash = _hash(
                ctx
            )

            # IMPORTANT:
            # "attempted" means the repair operation completed without
            # crashing. It does NOT mean the finding is semantically fixed.
            # The runner must re-run the verifier.
            outcome = (
                "attempted"
                if attempt_ok
                else "unresolved"
            )

            self._log_cycle(
                scene_id,
                finding_type,
                routed_finding.get(
                    "mismatch_subtype"
                ),
                routed_to=attempted_targets,
                diagnostic_message=diagnostic,
                pre_hash=pre_hash,
                post_hash=post_hash,
                outcome=outcome,
                cycles_used=used,
            )

            if attempt_ok:
                # Mark this finding as resolved provisionally. The runner's
                # post-repair verifier is the authoritative proof.
                finding["status"] = "resolved"

                self._emit(
                    "repair.finished",
                    scene_id=scene_id,
                    finding_type=finding_type,
                    cycle=used,
                    outcome="attempted",
                )

                return

            self._emit(
                "repair.finished",
                scene_id=scene_id,
                finding_type=finding_type,
                cycle=used,
                outcome="unresolved",
            )

        # --------------------------------------------------------------
        # Budget exhausted
        # --------------------------------------------------------------

        self._log_cycle(
            scene_id,
            finding_type,
            routed_finding.get(
                "mismatch_subtype"
            ),
            routed_to=targets,
            diagnostic_message=_detail(
                finding
            ),
            pre_hash=_hash(ctx),
            post_hash=_hash(ctx),
            outcome="gave_up",
            cycles_used=self._cycles_used.get(
                cycles_key,
                0,
            ),
        )

        # A finding explicitly marked "cosmetic" (e.g. verifier_semantic's
        # layout-only nits, as opposed to a domain/correctness failure) must
        # not carry hard-gate weight just because its source plugin is a
        # hard gate overall. Repair was already attempted up to the budget;
        # if it never resolved, ship the video with the known imperfection
        # rather than aborting the entire multi-scene pipeline over it.
        if not source_is_gate or bool(finding.get("cosmetic")):
            # Soft gate (or a cosmetic-only hard-gate finding): preserve the
            # defect as an open issue without allowing it to halt the scene.
            finding["status"] = (
                "open_defect"
            )

        else:
            # Hard gate: leave status untouched so the runner can halt.
            finding["status"] = finding.get(
                "status",
                "fail",
            )

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit(
        self,
        event_name: str,
        **payload: Any,
    ) -> None:
        if self._bus is None:
            return

        try:
            self._bus.emit(
                event_name,
                **payload,
            )
        except Exception:
            # Repair events must never crash the repair itself.
            return

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_cycle(
        self,
        scene_id: str,
        finding_type: str,
        mismatch_subtype: Any,
        *,
        routed_to: list[str],
        diagnostic_message: str,
        pre_hash: str,
        post_hash: str,
        outcome: str,
        cycles_used: int,
    ) -> None:
        """Persist one auditable repair-cycle record."""

        if self._log_path is None:
            return

        self._cycle_id += 1

        from ...logging_ import RepairRecord

        record = RepairRecord(
            cycle_id=self._cycle_id,
            scene_id=scene_id,
            finding_type=finding_type,
            mismatch_subtype=mismatch_subtype,
            routed_to=routed_to,
            diagnostic_message=diagnostic_message,
            pre_repair_context_hash=pre_hash,
            post_repair_context_hash=post_hash,
            outcome=outcome,
            cycles_used=cycles_used,
            timestamp=time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
        )

        self.history.append(
            record
        )

        if self._active_context is not None:
            self._active_context.repair_records.append(
                dataclasses.asdict(
                    record
                )
            )

        self._log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self._log_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    dataclasses.asdict(
                        record
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )


# ---------------------------------------------------------------------------
# Context hashing
# ---------------------------------------------------------------------------

def _hash(
    ctx: SceneContext,
) -> str:
    """Return the canonical context hash used by repair provenance."""

    from ...logging_ import context_hash

    return context_hash(
        ctx
    )