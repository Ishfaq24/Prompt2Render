"""Repair strategy provider for Prompt2Render.

**This module routes and executes repairs. It does not decide whether a
repair succeeded.** That distinction is the whole point of its current
shape.

Previously this class owned the repair lifecycle: it subscribed to
``check.failed``, looped over its own budget, invoked repair targets, and
then declared victory by rewriting the finding's ``status`` to
``"resolved"`` whenever the repair call did not raise. Since
``HarnessRunner._failures()`` counts only ``status == "fail"``, that
rewrite made the finding invisible to the gate -- so a repair that produced
*worse* code still cleared it. Its own docstring conceded the point:
*"'attempted' means the repair operation completed without crashing. It
does NOT mean the finding is semantically fixed."*

Meanwhile the runner ran a second, competing loop (rewind + re-verify) that
communicated with this one only through mutations to ``SceneContext``, with
neither able to see the other's budget.

Now there is exactly one controller --
:class:`prompt2render.harness.repair_controller.RepairController` -- and this
class provides it with two things:

    plan(finding, source)  -> RepairPlan | None   (routing only)
    execute(plan, context) -> RepairExecution     (perform the mutation)

Acceptance, quality comparison, budget, rollback and logging all belong to
the controller. Nothing here inspects or rewrites a finding's status.

The routing policy itself (``policy.py``) is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...context import SceneContext
from ...events import EventBus
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
    "verifier_layout": "layout_violation",
    "verifier_lifecycle": "lifecycle_violation",
    "verifier_audio": "audio_visual_mismatch",
    "verifier_storyboard": "storyboard_failure",
    "verifier_pedagogy": "pedagogy_review",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    """Resolve the affected scene identifier.

    ``"__all__"`` is the deliberate fallback for whole-video findings
    (verifier_audio, verifier_pedagogy). The controller filters those out of
    scene repair -- there is no single scene to regenerate, and every
    ``revert_scene`` implementation raises ``KeyError`` on it.
    """

    value = (
        finding.get("stem")
        or finding.get("scene_id")
        or "__all__"
    )

    return str(value)


def finding_type_of(
    finding: dict[str, Any],
    source: str,
) -> str:
    """The routing key for one finding."""

    return str(
        finding.get("finding_type")
        or _DEFAULT_FINDING_TYPE.get(source, source)
    )


# ---------------------------------------------------------------------------
# Plan / execution records
# ---------------------------------------------------------------------------

def _derive_category(finding: dict[str, Any], source: str) -> str:
    """Diagnosis-driven category from finding or source plugin."""
    raw = str(finding.get("category") or finding.get("Category") or "").strip().upper()
    if raw in {"LAYOUT", "SPATIAL", "SEMANTIC", "STRUCTURAL", "TEMPORAL", "PEDAGOGY", "PEDAGOGICAL", "AUDIO", "TECHNICAL"}:
        # Normalize PEDAGOGICAL -> PEDAGOGY etc but keep canonical
        if raw == "PEDAGOGICAL":
            return "PEDAGOGY"
        return raw
    # Infer from source plugin name
    if "layout" in source.lower():
        return "LAYOUT"
    if "semantic" in source.lower():
        return "SEMANTIC"
    if "spatial" in source.lower():
        return "SPATIAL"
    if "pedagogy" in source.lower():
        return "PEDAGOGY"
    if "temporal" in source.lower() or "lifecycle" in source.lower():
        return "TEMPORAL"
    if "execution" in source.lower() or "render" in source.lower():
        return "STRUCTURAL"
    return "LAYOUT" if "layout" in str(finding.get("finding_type", "")).lower() else "SEMANTIC"


def _derive_subtype(finding: dict[str, Any]) -> str | None:
    for k in ("mismatch_subtype", "layout_subtype", "subtype", "finding_subtype"):
        v = finding.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    ft = str(finding.get("finding_type", "")).lower()
    if "crowd" in ft:
        return "CROWDING"
    if "caption" in ft:
        return "CAPTION_COLLISION"
    if "overlap" in ft:
        return "OVERLAP"
    if "offframe" in ft or "out_of_bounds" in ft:
        return "OUT_OF_BOUNDS"
    if "overflow" in ft:
        return "TEXT_OVERFLOW"
    return None


def _contract_for(category: str, subtype: str | None) -> tuple[list[str], list[str], str]:
    """Target-aware repair contract: what may change vs what must be preserved."""
    cat = str(category or "").upper()
    sub = str(subtype or "").upper()

    if cat == "LAYOUT":
        allowed = ["position", "spacing", "font_size", "line_wrap"]
        protected = ["objects", "values", "relationships", "animation_sequence", "narration"]
        instruction = (
            "This is a layout-only repair. Preserve all semantic content, values, objects, "
            "relationships, animation sequence, and pedagogical intent. Modify only geometry, "
            "spacing, typography, or safe-zone placement necessary to resolve the finding. "
            f"Subtype: {sub}. Allowed: {', '.join(allowed)}. Do NOT change underlying data or logic."
        )
        return allowed, protected, instruction

    if cat == "SPATIAL":
        # SPATIAL is the legacy name for layout; keep repair minimal for backward compat
        allowed = ["position", "spacing"]
        protected = ["objects", "values"]
        instruction = ""  # do not inject layout-only constraint for legacy spatial findings (tests expect only diagnostic)
        return allowed, protected, instruction

    if cat == "SEMANTIC":
        allowed = ["objects", "values", "relationships", "animation_sequence", "labels"]
        protected = ["position", "spacing"]  # layout should stay similar if possible, but semantic may move things
        instruction = (
            "This is a semantic repair. Correct the conceptual content, values, objects, or "
            "relationships to match the narration and domain invariants. Preserve overall layout "
            "where possible. Check every diagram label against the geometry it depicts: "
            "coordinate-plane axes, rotation axes, vector directions, units, and matrix dimensions "
            "must be physically and mathematically consistent. If a 2D projection depicts a 3D "
            "operation, explicitly label the perpendicular/out-of-plane axis rather than assigning "
            "it to an in-plane line. Subtype: {sub}. Allowed: {', '.join(allowed)}."
        )
        return allowed, protected, instruction

    if cat == "STRUCTURAL":
        allowed = ["render", "resolution", "duration", "assets"]
        protected = ["objects", "values", "narration"]
        instruction = "This is a structural repair. Fix rendering or asset issues without altering pedagogical content."
        return allowed, protected, instruction

    if cat in {"PEDAGOGY", "PEDAGOGICAL"}:
        allowed = ["explanation", "progression", "example"]
        protected = ["layout", "values"]
        instruction = "Pedagogical repair: improve clarity and progression while preserving values and layout."
        return allowed, protected, instruction

    if cat == "TEMPORAL":
        allowed = ["cue", "timing", "duration"]
        protected = ["objects", "values"]
        instruction = "Temporal repair: realign cues and animation timing without changing semantic content."
        return allowed, protected, instruction

    # Fallback
    allowed = ["position", "spacing", "font_size"]
    protected = ["objects", "values", "relationships"]
    instruction = f"Repair for {cat}/{sub}: follow allowed changes {allowed}, preserve {protected}."
    return allowed, protected, instruction


@dataclass
class RepairPlan:
    """What the router proposes doing about one finding."""

    stem: str
    finding_type: str
    source_plugin: str
    targets: list[str]
    diagnostic: str = ""
    mismatch_subtype: Any = None
    category: str = "LAYOUT"
    subtype: str | None = None
    allowed_changes: list[str] = field(default_factory=list)
    protected_properties: list[str] = field(default_factory=list)
    repair_instruction: str = ""

    @property
    def routable(self) -> bool:
        return bool(self.targets)


@dataclass
class RepairExecution:
    """What actually happened when a plan was carried out.

    ``ok`` means *the repair operation ran without raising* -- nothing more.
    Whether the result is acceptable is the controller's judgement, made
    from re-verification evidence, not from this flag.
    """

    ok: bool = True
    targets_run: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class RepairRouterPlugin(Plugin):
    """Policy-based repair routing and execution.

    Still a ``Plugin`` subclass so the existing loader path
    (``build_repair_router``) and ``NON_PIPELINE`` exclusion keep working
    unchanged, but it is not a pipeline stage: ``run()`` is a passthrough.
    """

    name = "repair_router"

    def __init__(
        self,
        config: dict | None = None,
    ):
        super().__init__(config)

        self.policy: RoutingPolicy = (
            StaticTableRoutingPolicy(
                self.config.get(
                    "routing_table"
                )
            )
        )

        self._plugins_by_name: dict[str, Plugin] = {}
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
        # Not a pipeline stage -- the controller drives repair explicitly.
        return context

    def _default_gate(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def attach(
        self,
        *,
        bus: EventBus | None = None,
        plugins_by_name: dict[str, Plugin] | None = None,
        log_path: Any = None,
    ) -> None:
        """Register the plugin instances repairs can be routed to.

        No longer subscribes to ``check.failed``: repair is initiated by the
        runner through :class:`RepairController`, not by an event handler
        racing the runner's own control flow. ``bus`` is retained so
        lifecycle events can still be emitted, and ``log_path`` is accepted
        (and ignored) so existing callers keep working -- the controller
        owns the decision log now.
        """

        if plugins_by_name is not None:
            self._plugins_by_name = dict(plugins_by_name)

        if bus is not None:
            self._bus = bus

    def subscribe(
        self,
        bus: EventBus,
    ) -> None:
        """Compatibility hook. Deliberately does not subscribe."""

        return

    @property
    def plugins_by_name(self) -> dict[str, Plugin]:
        return self._plugins_by_name

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def plan(
        self,
        finding: dict[str, Any],
        source: str,
    ) -> RepairPlan:
        """Decide what to do about one finding. Pure -- mutates nothing."""

        finding_type = finding_type_of(finding, source)
        stem = _scene_id(finding)

        routed = {
            **finding,
            "finding_type": finding_type,
            "scene_id": stem,
            "source_plugin": source,
        }

        category = _derive_category(finding, source)
        subtype = _derive_subtype(finding) or str(finding.get("mismatch_subtype") or "").strip().upper() or None
        # Normalize subtype case for contract
        if subtype:
            subtype = subtype.upper()
        allowed, protected, instruction = _contract_for(category, subtype)

        return RepairPlan(
            stem=stem,
            finding_type=finding_type,
            source_plugin=source,
            targets=self._resolve_targets(routed),
            diagnostic=_detail(finding),
            mismatch_subtype=finding.get("mismatch_subtype") or subtype,
            category=category,
            subtype=subtype,
            allowed_changes=allowed,
            protected_properties=protected,
            repair_instruction=instruction,
        )

    def _resolve_targets(
        self,
        routed_finding: dict[str, Any],
    ) -> list[str]:
        """Resolve repair targets, including the Manim backend alias."""

        targets = self.policy.decide(routed_finding)

        if not targets:
            return []

        targets = [
            str(target)
            for target in targets
            if str(target).strip()
        ]

        # The canonical table names generator_code; when Manim is the
        # active backend that role is filled by generator_manim.
        if (
            "generator_code" not in self._plugins_by_name
            and "generator_manim" in self._plugins_by_name
        ):
            targets = [
                "generator_manim" if target == "generator_code" else target
                for target in targets
            ]

        return list(dict.fromkeys(targets))

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        plan: RepairPlan,
        context: SceneContext,
    ) -> RepairExecution:
        """Carry out a plan against the context.

        Records the triggering diagnostic into ``repair_context`` first so
        the generator's prompt can see why it is being asked to try again,
        then invokes each target.

        Scene-scoped repair (``revert_scene`` + ``regenerate_one``) is
        preferred. A target implementing neither degrades to a full
        ``run(ctx)``, which is not scene-scoped and may touch other stems --
        the controller detects that separately via revision comparison.
        """

        execution = RepairExecution()

        if plan.diagnostic:
            history = context.repair_context.setdefault(plan.stem, [])

            # Deduplicate: the same diagnostic re-appended on every attempt
            # used to grow the prompt without adding information, and both
            # generators truncate the feedback to its trailing 6000 chars.
            if plan.diagnostic not in history:
                history.append(plan.diagnostic)

        # Diagnosis-driven constraint: embed the repair contract so the LLM
        # sees what may and may not be changed. This is what enforces
        # layout-only repairs preserving semantic content.
        if getattr(plan, "repair_instruction", None):
            history = context.repair_context.setdefault(plan.stem, [])
            instr = str(plan.repair_instruction).strip()
            if instr and instr not in history:
                history.append(instr)
            # Also append structured contract for explicit logging
            contract = f"REPAIR CONTRACT category={plan.category} subtype={plan.subtype} allowed={plan.allowed_changes} protected={plan.protected_properties}"
            if contract not in history:
                history.append(contract)

        for target_name in plan.targets:
            target = self._plugins_by_name.get(target_name)

            if target is None:
                execution.add_error(
                    f"repair target {target_name!r} is not registered"
                )
                continue

            try:
                if (
                    hasattr(target, "revert_scene")
                    and hasattr(target, "regenerate_one")
                ):
                    target.revert_scene(context, plan.stem)
                    target.regenerate_one(context, plan.stem)
                else:
                    target.run(context)

                execution.targets_run.append(target_name)

            except (Exception, SystemExit) as exc:
                message = (
                    f"{target_name} repair failed: "
                    f"{type(exc).__name__}: {exc}"
                )

                execution.add_error(message)

                context.repair_context.setdefault(
                    plan.stem,
                    [],
                ).append(message)

        return execution

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def emit(
        self,
        event: str,
        **payload: Any,
    ) -> None:
        """Emit a repair lifecycle event, never raising on failure."""

        if self._bus is None:
            return

        try:
            self._bus.emit(event, **payload)
        except Exception:
            return


__all__ = [
    "RepairExecution",
    "RepairPlan",
    "RepairRouterPlugin",
    "finding_type_of",
]
