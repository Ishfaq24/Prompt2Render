"""Context-aware multilingual translation and educational terminology preservation.

Ensures that mathematical formulas, code identifiers, variables, and scientific terms
remain unaltered while translating instructional narration and on-screen text.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .registry import LanguageRegistry
from .spec import EducationalSpecification, SceneSpec


# Standard technical terms and glossaries to preserve or transliterate cleanly
STANDARD_PRESERVED_TERMS = {
    "linear regression",
    "gradient descent",
    "binary search",
    "neural network",
    "backpropagation",
    "loss function",
    "learning rate",
    "weights",
    "biases",
    "o(n)",
    "o(1)",
    "o(log n)",
    "o(n log n)",
    "cpu",
    "gpu",
    "ram",
    "api",
    "json",
    "python",
}

# Educational terminology dictionaries for verified domain-accurate translations
DOMAIN_GLOSSARY: dict[str, dict[str, str]] = {
    "hi": {
        "linear regression": "रैखिक प्रतिगमन (Linear Regression)",
        "binary search": "बाइनरी सर्च (Binary Search)",
        "gradient descent": "ग्रेडिएंट डिसेंट (Gradient Descent)",
        "neural network": "न्यूरल नेटवर्क (Neural Network)",
        "backpropagation": "बैकप्रोपेगेशन (Backpropagation)",
        "loss function": "हानि फलन (Loss Function)",
        "learning rate": "लर्निंग रेट (Learning Rate)",
        "time complexity": "समय जटिलता (Time Complexity)",
        "space complexity": "स्थान जटिलता (Space Complexity)",
        "algorithm": "एल्गोरिदम (Algorithm)",
        "step": "चरण",
        "input": "इनपुट",
        "output": "आउटपुट",
        "data structure": "डेटा संरचना (Data Structure)",
    },
    "ur": {
        "linear regression": "لکیری رجعت (Linear Regression)",
        "binary search": "بائنری سرچ (Binary Search)",
        "gradient descent": "گریڈینٹ ڈیسینٹ (Gradient Descent)",
        "neural network": "عصبی نیٹ ورک (Neural Network)",
        "backpropagation": "بیک پروپیگیشن (Backpropagation)",
        "loss function": "نقصان کا تفاعل (Loss Function)",
        "learning rate": "سیکھنے کی شرح (Learning Rate)",
        "time complexity": "وقت کی پیچیدگی (Time Complexity)",
        "space complexity": "جگہ کی پیچیدگی (Space Complexity)",
        "algorithm": "الگورتھم (Algorithm)",
        "step": "مرحلہ",
        "input": "ان پٹ",
        "output": "آؤٹ پٹ",
        "data structure": "ڈیٹا ڈھانچہ (Data Structure)",
    },
    "ar": {
        "linear regression": "الانحدار الخطي (Linear Regression)",
        "binary search": "البحث الثنائي (Binary Search)",
        "gradient descent": "الانحدار التدريجي (Gradient Descent)",
        "neural network": "الشبكة العصبية (Neural Network)",
        "backpropagation": "الانتشار الخلفي (Backpropagation)",
        "loss function": "دالة الخسارة (Loss Function)",
        "learning rate": "معدل التعلم (Learning Rate)",
        "time complexity": "التعقيد الزمني (Time Complexity)",
        "space complexity": "التعقيد المكاني (Space Complexity)",
        "algorithm": "خوارزمية (Algorithm)",
        "step": "خطوة",
        "input": "مدخلات",
        "output": "مخرجات",
        "data structure": "هيكل البيانات (Data Structure)",
    },
    "ks": {
        "linear regression": "لکیری ریگریشن (Linear Regression)",
        "binary search": "بائنری سرچ (Binary Search)",
        "gradient descent": "گریڈینٹ ڈیسینٹ (Gradient Descent)",
        "neural network": "نیورل نیٹ ورک (Neural Network)",
        "backpropagation": "بیک پروپیگیشن (Backpropagation)",
        "algorithm": "الگورتھم (Algorithm)",
        "step": "قدم / مرحلہ",
        "data structure": "ڈیٹا ڈھانچہ",
    },
}


class MultilingualTranslator:
    """Translates educational specifications with terminology preservation and LLM fallback."""

    @classmethod
    def preserve_tokens(cls, text: str) -> tuple[str, dict[str, str]]:
        """Mask mathematical formulas, code blocks, and immutable tokens before translation."""
        placeholders: dict[str, str] = {}
        counter = 0

        # Mask LaTeX expressions: $...$ or $$...$$
        def math_repl(m):
            nonlocal counter
            key = f"__MATH_{counter}__"
            counter += 1
            placeholders[key] = m.group(0)
            return key

        masked = re.sub(r"\$\$[^\$]+\$\$|\$[^\$]+\$", math_repl, text)

        # Mask inline code: `...`
        def code_repl(m):
            nonlocal counter
            key = f"__CODE_{counter}__"
            counter += 1
            placeholders[key] = m.group(0)
            return key

        masked = re.sub(r"`[^`]+`", code_repl, masked)
        return masked, placeholders

    @classmethod
    def restore_tokens(cls, text: str, placeholders: dict[str, str]) -> str:
        """Restore masked mathematical and code tokens to their original form."""
        restored = text
        for key, val in placeholders.items():
            restored = restored.replace(key, val)
        return restored

    @classmethod
    def translate_text(
        cls,
        text: str,
        target_lang: str,
        target_script: str | None = None,
        source_lang: str = "en",
    ) -> str:
        """Translate text while preserving technical terminology and math symbols."""
        if not text or target_lang == source_lang:
            return text

        masked, placeholders = cls.preserve_tokens(text)

        # 1. Apply domain glossary substitutions
        glossary = DOMAIN_GLOSSARY.get(target_lang, {})
        translated = masked

        # If LLM is configured and text is non-trivial, translate through LLM with structured prompt
        try:
            from prompt2render import llm
            # Safely check if keys exist without causing SystemExit
            has_key = bool(
                os.environ.get("P2R_LLM_API_KEY", "").strip()
                or os.environ.get("OPENAI_API_KEY", "").strip()
                or os.environ.get("GEMINI_API_KEY", "").strip()
            )
            if has_key:
                keys = llm.keys()
                if keys:
                    prompt = (
                        f"You are an expert multilingual educational translator for mathematics and computer science.\n"
                        f"Translate the following instructional text from {source_lang} to {target_lang} (script: {target_script or 'default'}).\n"
                        f"CRITICAL REQUIREMENTS:\n"
                        f"- Keep ALL placeholders like __MATH_0__, __CODE_0__ EXACTLY unchanged.\n"
                        f"- Preserve technical terms, algorithm names, variable names, and code syntax.\n"
                        f"- Write natural, pedagogically clear explanations for students.\n"
                        f"- Do not add explanations or meta commentary; output ONLY the translated text.\n\n"
                        f"Text to translate:\n{masked}"
                    )
                    res = llm.complete(prompt, temperature=0.1, max_tokens=1000)
                    if res and res.strip():
                        translated = res.strip()
        except BaseException:
            # Safe offline deterministic substitution using glossary
            pass

        # Apply domain glossary replacements if available
        for en_term, target_term in glossary.items():
            pattern = re.compile(re.escape(en_term), re.IGNORECASE)
            translated = pattern.sub(target_term, translated)

        # Kashmiri Devanagari transliteration handling if target_script is Deva
        if target_lang == "ks" and target_script == "Deva":
            # Replace Arabic script Kashmiri glossary entries with Devanagari equivalents
            deva_map = {
                "بائنری سرچ": "बाइनरी सर्च",
                "الگورتھم": "एल्गोरिदम",
                "لکیری ریگریشن": "रैखिक रिग्रेशन",
                "ڈیٹا ڈھانچہ": "डेटा ढांचा",
            }
            for ar_t, dev_t in deva_map.items():
                translated = translated.replace(ar_t, dev_t)

        return cls.restore_tokens(translated, placeholders)

    @classmethod
    def translate_specification(
        cls,
        spec: EducationalSpecification,
        target_lang: str,
        target_script: str | None = None,
    ) -> EducationalSpecification:
        """Translate an entire educational specification to the target language."""
        if spec.target_language == target_lang and spec.target_script == target_script:
            return spec

        lang_spec = LanguageRegistry.get_language(target_lang)
        resolved_script = target_script or lang_spec.default_script
        direction = lang_spec.get_script(resolved_script).direction

        translated_scenes: list[SceneSpec] = []
        for scene in spec.scenes:
            tr_obj = cls.translate_text(scene.learning_objective, target_lang, resolved_script, spec.source_language)
            tr_narr = cls.translate_text(scene.narration_text, target_lang, resolved_script, spec.source_language)
            tr_screen = cls.translate_text(scene.on_screen_text, target_lang, resolved_script, spec.source_language)

            translated_scenes.append(
                SceneSpec(
                    scene_index=scene.scene_index,
                    stem=scene.stem,
                    learning_objective=tr_obj,
                    narration_text=tr_narr,
                    on_screen_text=tr_screen,
                    visual_elements=scene.visual_elements,
                    math_expressions=scene.math_expressions,
                    code_snippets=scene.code_snippets,
                    estimated_duration_sec=scene.estimated_duration_sec,
                    layout_stage=scene.layout_stage,
                    direction=direction,
                )
            )

        tr_topic = cls.translate_text(spec.topic, target_lang, resolved_script, spec.source_language)
        tr_objs = [cls.translate_text(o, target_lang, resolved_script, spec.source_language) for o in spec.learning_objectives]

        return EducationalSpecification(
            topic=tr_topic,
            learning_objectives=tr_objs,
            prerequisites=spec.prerequisites,
            source_language=spec.source_language,
            target_language=target_lang,
            target_script=resolved_script,
            educational_level=spec.educational_level,
            scenes=translated_scenes,
            mathematical_formulas=spec.mathematical_formulas,
            technical_terms=spec.technical_terms,
        )
