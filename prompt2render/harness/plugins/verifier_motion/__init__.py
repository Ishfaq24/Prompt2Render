"""Deterministic motion verifier -- Tier 3 Phase 12 ("motion traces").

quality_report.py's own six quality dimensions (semantic/temporal/spatial/
motion/continuity/pedagogical, docs/ARCHITECTURE_AUDIT.md SS16) have had a
"motion" dimension since Phase 10 shipped it, but zero plugins ever mapped
to it -- Phase 10's own docstring flagged this: "motion always reports zero
findings today -- no verifier covers it yet... Phase 12 is presumably where
that gets filled in." This plugin is that fill-in.

It reads the raw per-state frame deltas ``observer_visual`` already recorded
on ``RenderArtifact.motion`` (``visual_observe.observe_motion``) and decides,
per state, whether "too little of the frame changed" is a real defect or a
correct static state:

- A state flagged ``hold`` in ``SemanticAnimationIR`` (Phase 3: "HOLD is a
  per-state flag meaning this state deliberately adds no new elements") is
  legitimately expected to show near-zero motion -- suppressed, never a
  finding.
- Any other state below ``min_motion_delta`` is reported: the plan said
  something should happen here (it has ACTION beats / a non-hold state
  always needs >=1, per Phase 3's own validation), but the rendered pixels
  barely changed. That is exactly the class of defect F1/F2 already showed
  is possible on this path -- an animation authored/planned but not actually
  executed on screen.

Unlike ``verifier_spatial`` (which parses ``observer_visual``'s pre-judged
WARN/FAIL text to stay compatible with the pre-existing SceneKit audit
shape), this verifier owns the pass/warn judgment itself:
``observer_visual``/``visual_observe.observe_motion`` deliberately record
only raw deltas, with no legacy parser to preserve compatibility with. This
keeps "observer observes, verifier decides" uncompromised here.

Deliberately advisory (``_default_gate() -> False``) -- same conservative
posture as ``verifier_spatial``/``observer_visual``: a heuristic pixel-delta
threshold can false-positive (subtle motion, a `Highlight` that only
recolors a few pixels), and this is the first verifier ever to cover the
"motion" dimension at all, so it should not be able to halt a build by
default.
"""

from __future__ import annotations

from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin
from .... import visual_observe


def _hold_lookup(
    context: SceneContext,
) -> dict[str, dict[str, bool]]:
    """``{stem: {state_name: hold}}`` from SemanticAnimationIR, or ``{}``."""

    semantic_ir = context.semantic_ir

    if semantic_ir is None:
        return {}

    return {
        section.stem: {
            state.name: state.hold
            for state in section.states
        }
        for section in semantic_ir.sections
    }


class VerifierMotionPlugin(Plugin):
    """Turns observer_visual's raw motion traces into findings."""

    name = "verifier_motion"

    def declare_dependencies(self) -> list[str]:
        return [
            "render_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        min_motion_delta = float(
            self.config.get(
                "min_motion_delta",
                visual_observe.DEFAULT_MIN_MOTION_DELTA,
            )
        )

        gate = self.is_gate()
        holds = _hold_lookup(context)

        findings: list[dict[str, Any]] = []

        for stem, artifact in context.render_artifacts.items():

            record = getattr(artifact, "motion", None)

            if not isinstance(record, dict):
                findings.append(
                    {
                        "status": "skip",
                        "stem": stem,
                        "finding_type": "motion_trace_unavailable",
                        "category": Category.SPATIAL.value,
                        "detail": (
                            "No motion trace recorded for this rendered "
                            "scene."
                        ),
                    }
                )
                continue

            if record.get("status") != "ok":
                findings.append(
                    {
                        "status": "skip",
                        "stem": stem,
                        "finding_type": "motion_trace_unavailable",
                        "category": Category.SPATIAL.value,
                        "detail": record.get(
                            "detail",
                            "Motion trace unavailable.",
                        ),
                    }
                )
                continue

            stem_holds = holds.get(stem, {})
            triggered = 0

            for trace in record.get("traces") or []:
                state_name = str(trace.get("state", ""))
                delta = trace.get("delta")

                if not isinstance(delta, (int, float)):
                    continue

                if delta >= min_motion_delta:
                    continue

                if stem_holds.get(state_name, False):
                    # Legitimately static -- HOLD means "add nothing new
                    # here", so near-zero motion is the correct outcome.
                    continue

                triggered += 1

                finding = Finding(
                    finding_id=next_finding_id("motion"),
                    scene_id=stem,
                    category=Category.SPATIAL,
                    severity=(
                        Severity.BLOCKING
                        if gate
                        else Severity.WARNING
                    ),
                    message=(
                        f"state '{state_name}': only {delta:.4%} of the "
                        f"frame changed between {trace.get('start')}s and "
                        f"{trace.get('end')}s (expected visible motion)"
                    ),
                    finding_type="motion_absence",
                )

                result = finding.as_check_result()
                result["mismatch_subtype"] = "motion_absence"

                findings.append(result)

            if triggered == 0:
                traces = record.get("traces") or []

                findings.append(
                    {
                        "status": "pass",
                        "stem": stem,
                        "finding_type": "motion_trace",
                        "category": Category.SPATIAL.value,
                        "detail": f"{len(traces)} state(s) traced, motion present",
                    }
                )

        context.check_results[self.name] = findings

        return context

    def _default_gate(self) -> bool:
        """Advisory by default -- see module docstring."""

        return False


__all__ = [
    "VerifierMotionPlugin",
]
