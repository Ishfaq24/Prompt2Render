"""Deterministic pre-render verifier for generated Scenekit modules.

This verifier is intentionally independent of an LLM. It parses the generated
module, validates the documented Scenekit input contracts, records every literal
k.* call to a JSON trace, and emits blocking findings for deterministic defects.
It does not claim to prove arbitrary subject-matter truth; that requires a
structured topic profile or an optional semantic reviewer.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...context import SceneContext
from ...plugin import Plugin
from ...finding import Category, Finding, Severity, next_finding_id
from ....scenes import trace_scene_source, validate_scene_source


class VerifierExecutionPlugin(Plugin):
    name = "verifier_execution"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def _trace_path(self, artifact_path: Path) -> Path:
        return artifact_path.with_suffix(".trace.json")

    def run(self, context: SceneContext) -> SceneContext:
        findings: list[dict] = []
        for entry in context.scene_plan:
            artifact = context.code_artifacts.get(entry.stem)
            if not artifact or not artifact.path or not artifact.path.exists():
                continue

            source = artifact.path.read_text(encoding="utf-8")
            narration = context.narration.get(entry.stem)
            max_cue = len(narration.sentences) - 1 if narration and narration.sentences else None
            errors = validate_scene_source(source, max_cue=max_cue)
            try:
                trace = trace_scene_source(source)
                trace["stem"] = entry.stem
                trace["source"] = str(artifact.path)
                trace["valid"] = not errors
                trace_path = self._trace_path(artifact.path)
                trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True), encoding="utf-8")
            except Exception as exc:
                errors.append(f"could not write deterministic scene trace: {exc}")

            for message in errors:
                finding = Finding(
                    finding_id=next_finding_id("exec"),
                    scene_id=entry.stem,
                    category=Category.SEMANTIC,
                    severity=Severity.BLOCKING if self.is_gate() else Severity.WARNING,
                    message=f"PRE-FLIGHT EXECUTION CHECK: {message}",
                ).as_check_result()
                finding["finding_type"] = "execution_failure"
                findings.append(finding)

        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        return True
