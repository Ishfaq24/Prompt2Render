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
        return ["render_artifacts", "check_results"]

    def declare_effects(self) -> list[str]:
        return ["hitl_annotations", "check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        findings = []
        hitl_file = context.project_dir / "hitl_feedback.json" if context.project_dir else None
        
        if hitl_file and hitl_file.exists():
            try:
                feedback_data = json.loads(hitl_file.read_text(encoding="utf-8"))
                for stem, feedback in feedback_data.items():
                    if feedback.get("status") == "reject":
                        reason = feedback.get("reason", "Manually rejected by human reviewer.")
                        f = Finding(
                            finding_id=next_finding_id("hitl"),
                            scene_id=stem,
                            category=Category.SEMANTIC,
                            severity=Severity.BLOCKING if self.is_gate() else Severity.WARNING,
                            message=f"Human Reviewer Feedback: {reason}"
                        )
                        findings.append(f.as_check_result())
                        
                        # Store annotation
                        context.hitl_annotations.append({
                            "stem": stem,
                            "reason": reason
                        })
            except Exception:
                pass
                
        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        # Defaults to False so an automated run doesn't block waiting for a human,
        # but if the human DID leave a rejection file, the finding triggers repair.
        return False
