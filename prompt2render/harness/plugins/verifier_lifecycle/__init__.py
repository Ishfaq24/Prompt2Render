"""Real lifecycle checker for prompt2render.
Verifies object continuity across scenes by checking if elements that 
appear in consecutive scenes are drawn with consistent properties (e.g. array length).
"""
from __future__ import annotations

import re

from ...context import SceneContext
from ...plugin import Plugin
from ...finding import Finding, Category, Severity, next_finding_id


class VerifierLifecyclePlugin(Plugin):
    name = "verifier_lifecycle"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts", "scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        findings = []
        
        # Simple heuristic: if an array is defined in scene N, 
        # it should ideally have the same length in scene N+1 unless explicitly changed.
        # This prevents the LLM from hallucinating [2, 6, 1] in scene 1 and [2, 6, 1, 8, 4] in scene 2
        # without explanation.
        
        last_arrays = []
        
        for entry in context.scene_plan:
            artifact = context.code_artifacts.get(entry.stem)
            if not artifact or not artifact.path or not artifact.path.exists():
                continue

            code = artifact.path.read_text(encoding="utf-8")
            
            # Find array definitions like k.array([2, 6, 1, 8, 4])
            current_arrays = []
            for match in re.finditer(r"k\.array\(\s*\[(.*?)\]", code):
                items = [x.strip() for x in match.group(1).split(",") if x.strip()]
                current_arrays.append(items)
                
            if last_arrays and current_arrays:
                # If both scenes have arrays, check if the first array matches in length
                # (assuming it's the same primary array being manipulated)
                if len(last_arrays[0]) != len(current_arrays[0]):
                    # Check if the narration implies an array size change (e.g., "split", "merge", "add", "remove")
                    if not any(word in entry.narration_text.lower() for word in ["split", "merge", "add", "remove", "append", "pop", "insert"]):
                        f = Finding(
                            finding_id=next_finding_id("life"),
                            scene_id=entry.stem,
                            category=Category.SEMANTIC,
                            severity=Severity.WARNING,
                            message=f"Lifecycle mismatch: Array length changed from {len(last_arrays[0])} to {len(current_arrays[0])} without explicit narration justification."
                        )
                        findings.append(f.as_check_result())
                        
            if current_arrays:
                last_arrays = current_arrays

        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        return False
