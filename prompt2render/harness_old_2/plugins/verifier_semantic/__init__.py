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
        
        try:
            if hasattr(llm, "keys"):
                keys = llm.keys()
            else:
                # Fallback for older llm.py that doesn't have keys()
                key = os.environ.get("GEMINI_API_KEY", "")
                keys = [key] if key else []
        except SystemExit:
            keys = []
            
        if not keys:
            cfg.warn("No GEMINI_API_KEY found, skipping semantic verification.")
            context.check_results[self.name] = []
            return context
            
        # Fallbacks for older llm.py
        if hasattr(llm, "model_chain"):
            models = llm.model_chain("P2R_SCENE_MODEL", "gemini-3.7-flash")
            model = models[0]
        else:
            model = os.environ.get("P2R_SCENE_MODEL", "gemini-3.7-flash")
            
        if hasattr(llm, "client"):
            client = llm.client(keys[0])
        else:
            try:
                from openai import OpenAI
            except ImportError:
                import sys
                sys.exit("[prompt2render] openai not installed — pip install -r requirements.txt")
            client = OpenAI(
                api_key=keys[0], 
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/", 
                timeout=300.0, 
                max_retries=2
            )

        for entry in context.scene_plan:
            artifact = context.code_artifacts.get(entry.stem)
            if not artifact or not artifact.path or not artifact.path.exists():
                continue

            code = artifact.path.read_text(encoding="utf-8")
            
            prompt = (
                f"You are a strict educational video reviewer and computer science expert. "
                f"Your job is to verify if the generated Python drawing code violates any pedagogical invariants or domain logic.\n\n"
                f"INTENT (Brief): {entry.anim}\n"
                f"NARRATION (What the speaker says): {entry.narration_text}\n\n"
                f"CODE (What is actually drawn):\n```python\n{code}\n```\n\n"
                f"You MUST evaluate the code for fatal domain logic errors based on the topic. Use your general knowledge of computer science and mathematics.\n"
                f"1. **Data Consistency**: Does the code use the exact numbers/data mentioned in the brief? If it invents new numbers or drops elements, reject it.\n"
                f"2. **Domain Invariants**: Are the visual states mathematically/logically sound for the topic? (e.g., in Tower of Hanoi, a larger disk cannot sit on a smaller disk; in a sorting algorithm, an array claimed to be sorted must actually be sorted).\n"
                f"3. **Intentional Rule Demonstration**: If the narration explicitly explains an ILLEGAL move or anti-pattern, the code MUST physically draw that illegal state (e.g., `[1, 2]` in Hanoi) AND clearly mark it as illegal (e.g., with a red 'X' or 'ILLEGAL' badge). If it just draws a legal state and slaps an 'ILLEGAL' label on it, reject it.\n"
                f"4. **Pedagogical Mismatch**: Does the visual state contradict the spoken explanation? (e.g., Narration says 'move to peg C' but code moves it to peg B).\n\n"
                f"Output ONLY a JSON object: {{\"status\": \"pass\" | \"fail\", \"reason\": \"Detailed explanation if failed. Include the exact code snippet that is wrong and explain how to fix it.\"}}"
            )
            
            try:
                if hasattr(llm, "complete"):
                    content = llm.complete(prompt, max_tokens=1000)
                else:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    content = resp.choices[0].message.content if resp.choices else "{}"
                    
                import json
                # Handle cases where llm.complete() returns markdown json blocks
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                    
                result = json.loads(content.strip())
                
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
        # Default to True so that pedagogical failures (like illegal Hanoi moves)
        # hard-block the pipeline if the repair router cannot fix them.
        return True
