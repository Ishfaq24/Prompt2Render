"""Language detector and educational specification extractor.

Detects input language, preserves technical entities and math equations,
and builds language-independent educational specifications.
"""

from __future__ import annotations

import re
from typing import Any

from .registry import LanguageRegistry
from .spec import EducationalSpecification, SceneSpec, VisualElementSpec


class LanguageDetector:
    """Detects input natural language using Unicode character frequency heuristics."""

    @classmethod
    def detect(cls, text: str) -> str:
        """Detect the language code ('en', 'hi', 'ur', 'ar', 'ks') from input text."""
        if not text:
            return "en"

        arabic_cnt = 0
        devanagari_cnt = 0
        kashmiri_specific_cnt = 0
        latin_cnt = 0

        for ch in text:
            code = ord(ch)
            # Devanagari block
            if 0x0900 <= code <= 0x097F:
                devanagari_cnt += 1
            # Arabic & Arabic Supplement blocks
            elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
                arabic_cnt += 1
                # Kashmiri specific Arabic letters (e.g. 0x0672, 0x06C4, etc.)
                if code in (0x0620, 0x0657, 0x065A, 0x065B, 0x0672, 0x06C4):
                    kashmiri_specific_cnt += 1
            # Latin
            elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
                latin_cnt += 1

        total = arabic_cnt + devanagari_cnt + latin_cnt
        if total == 0:
            return "en"

        if devanagari_cnt > (total * 0.25):
            return "hi"

        if arabic_cnt > (total * 0.25):
            if kashmiri_specific_cnt > 0:
                return "ks"
            # Distinguish Urdu vs Arabic by common Urdu characters (ٹ, ڈ, ڑ, ے, ہ, چ, پ)
            urdu_specific = set("ٹڈڑپےچھ")
            if any(c in urdu_specific for c in text):
                return "ur"
            return "ar"

        return "en"


class SpecificationExtractor:
    """Builds language-independent EducationalSpecification from user prompt or script."""

    @classmethod
    def extract_from_prompt(
        cls,
        prompt: str,
        input_lang: str | None = None,
        target_lang: str = "en",
        target_script: str | None = None,
        duration_minutes: float = 2.0,
        educational_level: str = "undergraduate computer science",
    ) -> EducationalSpecification:
        """Construct educational specification from a user prompt."""
        detected_lang = input_lang or LanguageDetector.detect(prompt)
        lang_spec = LanguageRegistry.get_language(target_lang)
        resolved_script = target_script or lang_spec.default_script
        direction = lang_spec.get_script(resolved_script).direction

        # Extract mathematical formulas (e.g. $...$ or standard operators)
        formulas = re.findall(r"\$([^\$]+)\$", prompt)

        # Build modular scenes tailored to the prompt
        scenes = [
            SceneSpec(
                scene_index=1,
                stem="01",
                learning_objective=f"Introduction to {prompt}",
                narration_text=f"Welcome. Today we explore {prompt}.",
                on_screen_text=prompt,
                visual_elements=[
                    VisualElementSpec(
                        element_id="hero_title",
                        element_type="title",
                        properties={"text": prompt},
                    )
                ],
                math_expressions=formulas,
                estimated_duration_sec=round(duration_minutes * 60 * 0.35, 1),
                layout_stage="hero_focus",
                direction=direction,
            ),
            SceneSpec(
                scene_index=2,
                stem="02",
                learning_objective="Core mechanics and step-by-step operation",
                narration_text=f"Let us examine how {prompt} operates step by step.",
                on_screen_text="Core Mechanics",
                visual_elements=[
                    VisualElementSpec(
                        element_id="main_stage",
                        element_type="flow_stage",
                        properties={"title": "Execution Flow"},
                    )
                ],
                math_expressions=formulas,
                estimated_duration_sec=round(duration_minutes * 60 * 0.40, 1),
                layout_stage="flow",
                direction=direction,
            ),
            SceneSpec(
                scene_index=3,
                stem="03",
                learning_objective="Summary, complexity, and takeaways",
                narration_text=f"To recap the fundamental properties of {prompt}.",
                on_screen_text="Summary & Takeaways",
                visual_elements=[
                    VisualElementSpec(
                        element_id="summary_card",
                        element_type="benchmark",
                        properties={"title": "Summary"},
                    )
                ],
                math_expressions=[],
                estimated_duration_sec=round(duration_minutes * 60 * 0.25, 1),
                layout_stage="benchmark",
                direction=direction,
            ),
        ]

        return EducationalSpecification(
            topic=prompt,
            learning_objectives=[f"Master concepts of {prompt}"],
            prerequisites=["Basic mathematics and programming concepts"],
            source_language=detected_lang,
            target_language=target_lang,
            target_script=resolved_script,
            educational_level=educational_level,
            scenes=scenes,
            mathematical_formulas=formulas,
            technical_terms=[],
        )
