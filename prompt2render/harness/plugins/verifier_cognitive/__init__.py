"""Cognitive Signaling & Mayer-Sweller Attention Verifier.

Evaluates pedagogical signaling quality and cognitive load metrics:
1. Signaling Coverage: Fraction of key spoken technical concepts that receive
   visual focus/signaling (Indicate, Circumscribe, Flash, etc.).
2. Redundancy Guard: Enforces that on-screen text does not duplicate full spoken narration
   (Sweller's redundancy effect / phonological loop overload).
3. Split-Attention Guard: Detects technical terms spoken without visual referents or signaling.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin
from ....cognitive_signaling import (
    calculate_cognitive_load_metrics,
    extract_key_concepts,
    resolve_visual_referents,
)


class VerifierCognitivePlugin(Plugin):
    """Verifies Mayer-Sweller cognitive signaling and attention guidance."""

    name = "verifier_cognitive"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "code_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(self, context: SceneContext) -> SceneContext:
        findings: list[dict[str, Any]] = []

        for entry in context.scene_plan:
            stem = entry.stem
            spoken_text = entry.narration_text or ""
            if not spoken_text and stem in context.narration:
                sentences = context.narration[stem].sentences
                spoken_text = " ".join(s.get("text", "") for s in sentences)

            # Retrieve code content
            code_art = context.code_artifacts.get(stem)
            code_text = ""
            if code_art and code_art.path and Path(code_art.path).is_file():
                try:
                    code_text = Path(code_art.path).read_text(encoding="utf-8")
                except Exception:
                    code_text = ""

            # Extract on-screen texts from code
            on_screen_texts = re.findall(
                r"(?:Text|Tex|MathTex)\s*\(\s*[rf]*[\"']([^\"']+)[\"']",
                code_text,
            )

            # Extract visual element definitions from code
            visual_elements = re.findall(
                r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:Text|MathTex|Tex|Square|Circle|Rectangle|Dot|VGroup|Polygon|Line|Arrow|SVGMobject|ImageMobject)",
                code_text,
            )

            # Extract signaling calls in code
            signaling_calls = re.findall(
                r"\b(?:Indicate|Circumscribe|Flash|Wiggle|FocusOn)\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)",
                code_text,
            )

            # Extract essential technical concepts
            concepts = extract_key_concepts(spoken_text)
            referent_map = resolve_visual_referents(concepts, visual_elements)

            # Calculate cognitive load metrics
            narration_words = spoken_text.split()
            cues = [{"target": m} for m in signaling_calls]
            metrics = calculate_cognitive_load_metrics(
                narration_words=narration_words,
                on_screen_texts=on_screen_texts,
                signaling_cues=cues,
                total_duration_s=max(5.0, len(narration_words) / 2.5),
            )

            # 1. Redundancy Overload Guard
            if metrics["redundancy_index"] > 0.40 and len(on_screen_texts) > 2:
                findings.append(
                    Finding(
                        finding_id=next_finding_id("cog"),
                        scene_id=stem,
                        category=Category.PEDAGOGY,
                        severity=Severity.WARNING,
                        message=(
                            f"Redundancy overload detected (ratio {metrics['redundancy_index']:.2f} > 0.40). "
                            "On-screen text risks overloading the phonological loop by duplicating spoken narration."
                        ),
                        finding_type="redundancy_overload",
                    ).as_check_result()
                )

            # 2. Split-Attention / Signaling Coverage Guard
            signaled_referents = set(signaling_calls)
            mapped_referents = set(referent_map.values())
            covered = mapped_referents & signaled_referents

            coverage = len(covered) / max(1, len(mapped_referents)) if mapped_referents else 1.0

            if concepts and mapped_referents and coverage < 0.25:
                findings.append(
                    Finding(
                        finding_id=next_finding_id("cog"),
                        scene_id=stem,
                        category=Category.PEDAGOGY,
                        severity=Severity.INFO,
                        message=(
                            f"Signaling coverage is low ({coverage:.0%}). Consider adding Indicate() or "
                            "Circumscribe() for key technical concepts to direct learner attention."
                        ),
                        finding_type="split_attention",
                    ).as_check_result()
                )

            # 3. Informational pass if clean
            if not any(f.get("scene_id") == stem for f in findings):
                findings.append(
                    Finding(
                        finding_id=next_finding_id("cog"),
                        scene_id=stem,
                        category=Category.PEDAGOGY,
                        severity=Severity.INFO,
                        message=(
                            f"Cognitive load verified (redundancy ratio: {metrics['redundancy_index']:.2f}, "
                            f"signaling density: {metrics['signaling_density']:.1f}/10s)."
                        ),
                        finding_type="cognitive_signaling_pass",
                    ).as_check_result()
                )

        context.check_results[self.name] = findings
        return context

    def _default_gate(self) -> bool:
        """Cognitive verifier is advisory by default."""
        return False
