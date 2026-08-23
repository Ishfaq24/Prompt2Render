"""Real LLM planner for prompt2render.
Instead of relying solely on the human-authored `> ANIM:` brief, this plugin
uses an LLM to expand the brief into a detailed state-by-state storyboard 
before handing it off to the Coder. This separates planning from coding, 
reducing hallucinations and cognitive overload.
"""
from __future__ import annotations

import os

from ...context import SceneContext
from ...plugin import Plugin
from .... import llm
from .... import cfg


class PlannerLlmPlugin(Plugin):
    name = "planner_llm"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["scene_plan"]

    def run(self, context: SceneContext) -> SceneContext:
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
            cfg.warn("No GEMINI_API_KEY found, skipping LLM planning.")
            for entry in context.scene_plan:
                entry.planned = True
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
            if entry.planned:
                continue
                
            prompt = (
                f"You are an expert educational video storyboarder.\n"
                f"Expand this brief into a detailed, step-by-step visual plan.\n\n"
                f"Title: {entry.title}\n"
                f"Original Brief: {entry.anim}\n"
                f"Narration: {entry.narration_text}\n\n"
                f"Output ONLY the expanded brief as plain text, focusing on exactly what elements "
                f"are on screen, their values, and how they change state by state to match the narration. "
                f"Keep it concise but specific (e.g. 'State 1: Array [2, 6, 1]. State 2: Highlight index 1')."
            )
            
            try:
                if hasattr(llm, "complete"):
                    # Use the shared completion helper that handles key/model fallback automatically
                    expanded_anim = llm.complete(prompt, max_tokens=1500).strip()
                else:
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    expanded_anim = resp.choices[0].message.content.strip() if resp.choices else ""
                    
                if expanded_anim:
                    # Append the expanded plan to the original brief so the Coder gets both
                    entry.anim = f"{entry.anim}\n\nExpanded Plan:\n{expanded_anim}"
            except Exception as e:
                cfg.warn(f"LLM planning failed for {entry.stem}: {e}")
                
            entry.planned = True
            
        return context

    def _default_gate(self) -> bool:
        return False
