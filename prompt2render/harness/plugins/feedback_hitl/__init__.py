"""Real Human-In-The-Loop (HITL) interface for prompt2render.
Checks if the user has provided manual annotations or rejections for specific
scenes in a `hitl_feedback.json` file. If a scene is manually rejected,
this plugin emits a finding to force a repair cycle.

Tier 4: parsing itself now delegates to ``harness.hitl.read_feedback`` --
SS14 documented this plugin and ``renderer_manim.hitl_status_sets`` as two
independent parsers of the same file; both are now thin wrappers over one
shared reader.
"""
from __future__ import annotations

from ... import hitl
from ...context import SceneContext
from ...plugin import Plugin
from ...finding import Finding, Category, Severity, next_finding_id


class FeedbackHitlPlugin(Plugin):
    name = "feedback_hitl"

    def declare_dependencies(self) -> list[str]:
        return ["render_artifacts"]

    def declare_effects(self) -> list[str]:
        # Findings are recorded in the aggregate check_results map, but that
        # mutable map is not an owned DAG artifact. The owned output here is
        # the human annotation collection.
        return ["hitl_annotations"]

    def run(self, context: SceneContext) -> SceneContext:
        findings: list[dict] = []

        # Never auto-mutate hitl_feedback.json based on in-memory
        # render_artifacts staleness. The previous heuristic
        # ``stem in repair_context and stem in render_artifacts`` was true
        # for *stale* clips (old MP4 still present in the map) and would
        # delete the user rejection before a fresh clip had been rendered
        # and re-verified, causing the exact stale-assembly bug reported for
        # sections 01/07. Clearing is now delegated to the runner's
        # ``_clear_verified_repair_context`` (which tracks passing
        # verifiers) and to explicit user action; the plugin only emits
        # findings.
        for stem, feedback in hitl.read_feedback(context.project_dir).items():
            if feedback.get("status") != "reject":
                continue

            reason = feedback.get("reason", "Manually rejected by human reviewer.")

            result = Finding(
                finding_id=next_finding_id("hitl"),
                scene_id=str(stem),
                category=Category.SEMANTIC,
                severity=Severity.BLOCKING,
                message=f"Human Reviewer Feedback: {reason}",
            ).as_check_result()
            result["finding_type"] = "feedback_hitl"
            findings.append(result)
            context.hitl_annotations.append({"stem": str(stem), "reason": str(reason)})

        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        # Defaults to False so an automated run doesn't block waiting for a human,
        # but if the human DID leave a rejection file, the finding triggers repair.
        return False
