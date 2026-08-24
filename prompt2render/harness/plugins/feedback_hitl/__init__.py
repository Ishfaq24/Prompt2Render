"""Real Human-In-The-Loop (HITL) interface for prompt2render.
Checks if the user has provided manual annotations or rejections for specific 
scenes in a `hitl_feedback.json` file. If a scene is manually rejected, 
this plugin emits a finding to force a repair cycle.
"""
from __future__ import annotations

import json

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
        hitl_file = context.project_dir / "hitl_feedback.json" if context.project_dir else None

        if hitl_file and hitl_file.exists():
            try:
                raw = hitl_file.read_text(encoding="utf-8")
                feedback_data = json.loads(raw) if raw.strip() else {}
                if not isinstance(feedback_data, dict):
                    feedback_data = {}
                # Never auto-mutate hitl_feedback.json based on in-memory
                # render_artifacts staleness.  The previous heuristic
                # ``stem in repair_context and stem in render_artifacts`` was
                # true for *stale* clips (old MP4 still present in the map) and
                # would delete the user rejection before a fresh clip had been
                # rendered and re-verified, causing the exact stale-assembly
                # bug reported for sections 01/07.  Clearing is now delegated
                # to the runner's ``_clear_verified_repair_context`` (which
                # tracks passing verifiers) and to explicit user action; the
                # plugin only emits findings.
                for stem, feedback in list(feedback_data.items()):
                    if not isinstance(feedback, dict):
                        continue
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

            except Exception:
                # Malformed JSON must not crash the harness; surface as a
                # skip so the pipeline can still report other verdicts.
                pass

        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        # Defaults to False so an automated run doesn't block waiting for a human,
        # but if the human DID leave a rejection file, the finding triggers repair.
        return False
