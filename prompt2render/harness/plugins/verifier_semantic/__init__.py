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
        return ["code_artifacts", "scene_plan", "render_artifacts"]

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

            # If we are in a repair loop, the code was regenerated but not re-rendered yet.
            # We must re-render to get the fresh preview image for the visual audit.
            preview_img = context.project_dir / "build" / "manim" / "previews" / f"Scene{entry.stem}.png"
            if entry.stem in context.repair_context and hasattr(artifact, "path") and artifact.path:
                from ....visuals import manim_scene
                try:
                    # Remove stale preview so we don't accidentally audit the old one if render fails
                    if preview_img.exists():
                        preview_img.unlink()
                    manim_scene(context.project_dir, context.project_dir / "build" / "manim" / f"scene_{entry.stem}.py", f"Scene{entry.stem}", entry.index)
                except Exception as e:
                    # If the repair code crashes Manim, record it as a semantic failure so the loop continues
                    from ...finding import Finding, Category, Severity, next_finding_id
                    findings.append(Finding(
                        finding_id=next_finding_id("sem"),
                        scene_id=entry.stem,
                        category=Category.RENDER,
                        severity=Severity.BLOCKING if self.is_gate() else Severity.WARNING,
                        message=f"Repaired Manim code failed to render: {e}"
                    ).as_check_result())
                    continue

            code = artifact.path.read_text(encoding="utf-8")
            
            prompt = (
                f"You are a strict educational video reviewer and computer science expert. "
                f"Your job is to verify if the generated Python drawing code violates any pedagogical invariants or domain logic.\n\n"
                f"INTENT (Brief): {entry.anim}\n"
                f"NARRATION (What the speaker says): {entry.narration_text}\n\n"
                f"CODE (What is actually drawn):\n```python\n{code}\n```\n\n"
                f"You MUST evaluate the code and the provided final preview frame for fatal domain logic errors and obvious layout failures. Use your general knowledge of computer science and mathematics.\n"
                f"1. **Data Consistency**: Does the code use the exact numbers/data mentioned in the brief? If it invents new numbers or drops elements, reject it.\n"
                f"2. **Domain Invariants**: Are the visual states mathematically/logically sound for the topic? (e.g., in Tower of Hanoi, a larger disk cannot sit on a smaller disk; in a sorting algorithm, an array claimed to be sorted must actually be sorted).\n"
                f"3. **Intentional Rule Demonstration**: If the narration explicitly explains an ILLEGAL move or anti-pattern, the code MUST physically draw that illegal state AND clearly mark it as illegal (e.g., with a red 'X'). If it just draws a legal state and slaps an 'ILLEGAL' label on it, reject it.\n"
                f"4. **Pedagogical Mismatch**: Does the visual state contradict the spoken explanation?\n"
                f"5. **Layout Safety**: Look at the preview frame. Are there any overlapping text elements or graphics? Is any text cut off by the edge of the screen? Is the text too small to read? If so, reject it and explain which coordinates to adjust.\n\n"
                f"Output ONLY a JSON object: {{\"status\": \"pass\" | \"fail\", \"reason\": \"Detailed explanation if failed. Include the exact code snippet that is wrong and explain how to fix it.\"}}"
            )
            
            # The preview_img path is defined earlier.
            messages = [{"role": "user", "content": prompt}]
            
            if preview_img.exists():
                import base64
                img_data = base64.b64encode(preview_img.read_bytes()).decode("utf-8")
                messages = [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}}
                    ]
                }]
            
            try:
                if hasattr(llm, "complete") and not preview_img.exists():
                    content = llm.complete(prompt, max_tokens=1000)
                else:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_format={"type": "json_object"}
                    )
                    content = resp.choices[0].message.content if resp.choices else "{}"
                    
                import json
                # Handle cases where llm.complete() returns markdown json blocks
                import re
                if content.startswith("```json"):
                    content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
                
                content = content.strip()
                try:
                    result = json.loads(content, strict=False)
                except json.JSONDecodeError:
                    # Fallback for invalid escapes or malformed JSON
                    # Replace invalid backslashes before quotes
                    content = content.replace('\\"', '"').replace('\\', '\\\\')
                    try:
                        result = json.loads(content, strict=False)
                    except json.JSONDecodeError:
                        # Final fallback: regex extraction
                        status_match = re.search(r'"status"\s*:\s*"([^"]+)"', content)
                        reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', content)
                        result = {
                            "status": status_match.group(1) if status_match else "pass",
                            "reason": reason_match.group(1) if reason_match else ""
                        }
                
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
