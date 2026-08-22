"""Real snippet retriever for prompt2render.
Instead of full RAG with embeddings, this uses a simple keyword-based 
retrieval over a local snippet library to inject helpful scenekit patterns 
into the prompt based on the section's brief.
"""
from __future__ import annotations

import re
from pathlib import Path

from ...context import SceneContext
from ...plugin import Plugin


class RetrieverManimRagPlugin(Plugin):
    name = "retriever_manim_rag"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["scene_plan"]

    def run(self, context: SceneContext) -> SceneContext:
        # Simple dictionary of keyword -> scenekit pattern
        snippets = {
            "array": "Remember: k.array([1, 2, 3]) draws a contiguous row of boxes.",
            "tree": "Remember: k.node('A', (x, y)) and k.arrow(node_a, node_b) can build trees.",
            "pointer": "Remember: k.label('i', (x, y)) can be used as a pointer under an array index.",
            "code": "Remember: k.code('def foo():\\n  pass') draws a syntax-highlighted block.",
            "compare": "Remember: You can draw two elements side-by-side by adjusting their x-coordinates."
        }
        
        for entry in context.scene_plan:
            text_to_search = (entry.anim + " " + entry.narration_text).lower()
            found_snippets = []
            
            for keyword, snippet in snippets.items():
                if re.search(r'\b' + keyword + r'\b', text_to_search):
                    found_snippets.append(snippet)
                    
            if found_snippets:
                injection = "\n\nRetrieved Scenekit Tips:\n" + "\n".join(found_snippets)
                entry.anim += injection
                
        return context

    def _default_gate(self) -> bool:
        return False
