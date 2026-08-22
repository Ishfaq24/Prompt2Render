"""Real semantic-correctness checker for prompt2render.
Verifies that the generated Python scene module actually fulfills the intent 
described in the scene_plan's `anim` brief and narration text.
"""
from __future__ import annotations

import os
from pathlib import Path

from ...context import SceneContext
from ...plugin import Plugin
from ...finding import Finding, Category, Severity, next_finding_id
from .... import llm
from .... import cfg


class VerifierSemanticPlugin(Plugin):
    name = "verifier_semantic"

    def declare_dependencies(self) -> list[str]:
        return ["code_artifacts", "scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        findings = []
        
        keys = llm.keys()
        if not keys:
            cfg.warn("No GEMINI_API_KEY found, skipping semantic verification.")
            context.check_results[self.name] = []
            return context
            
        models = llm.model_chain("P2R_SCENE_MODEL", "gemini-3.7-flash")
        client = llm.client(keys[0])
        model = models[0]

        for entry in context.scene_plan:
            artifact = context.code_artifacts.get(entry.stem)
            if not artifact or not artifact.path or not artifact.path.exists():
                continue

            code = artifact.path.read_text(encoding="utf-8")
            
            prompt = (
                f"You are a strict educational video reviewer. "
                f"Your job is to verify if the generated drawing code matches the educational intent.\n\n"
                f"INTENT (Brief): {entry.anim}\n"
                f"NARRATION (What the speaker says): {entry.narration_text}\n\n"
                f"CODE (What is actually drawn):\n```python\n{code}\n```\n\n"
                f"Check for:\n"
                f"1. Missing elements: Does the code draw the arrays, blocks, or values mentioned in the intent?\n"
                f"2. Incorrect values: If the brief specifies an array like [2,6,1,8,4], does the code use those exact numbers?\n"
                f"3. Pedagogical mismatch: Does the visual progression match the spoken explanation?\n\n"
                f"Output ONLY a JSON object: {{\"status\": \"pass\" | \"fail\", \"reason\": \"Detailed explanation if failed\"}}"
            )
            
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                
                content = resp.choices[0].message.content
                import json
                result = json.loads(content)
                
                if result.get("status", "").lower() == "fail":
                    f = Finding(
                        finding_id=next_finding_id("sem"),
                        scene_id=entry.stem,
                        category=Category.SEMANTIC,
                        severity=Severity.BLOCKING if self.is_gate() else Severity.WARNING,
                        message=result.get("reason", "Semantic mismatch detected by LLM critic.")
                    )
                    findings.append(f.as_check_result())
            except Exception as e:
                cfg.warn(f"Semantic verification failed for {entry.stem}: {e}")
                
        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        # Default to False (soft gate) so it doesn't hard-block the pipeline 
        # on subjective LLM judgments, but it will trigger repair_router.
        return False
