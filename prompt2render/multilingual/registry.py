"""Multilingual language and script registry for Prompt2Render.

Provides registry definitions, script configuration, font mappings, text direction,
and validation for all supported educational video generation languages.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScriptSpec:
    code: str
    name: str
    direction: str  # "ltr" or "rtl"
    default_font_windows: str
    default_font_linux: str
    fallback_fonts: list[str] = field(default_factory=list)
    char_ranges: list[tuple[int, int]] = field(default_factory=list)

    def get_font(self) -> str:
        """Return the appropriate primary font for the host OS."""
        if sys.platform.startswith("win"):
            return self.default_font_windows
        return self.default_font_linux


@dataclass(frozen=True)
class LanguageSpec:
    code: str
    name: str
    native_name: str
    default_script: str
    supported_scripts: dict[str, ScriptSpec]
    tts_lang_code: str
    default_voice: str | None = None
    sample_text: str = ""

    def get_script(self, script_code: str | None = None) -> ScriptSpec:
        """Resolve script spec, defaulting to default_script if omitted."""
        if not script_code:
            return self.supported_scripts[self.default_script]
        if script_code not in self.supported_scripts:
            valid = list(self.supported_scripts.keys())
            raise ValueError(
                f"Unsupported script '{script_code}' for language '{self.code}'. "
                f"Valid scripts: {valid}"
            )
        return self.supported_scripts[script_code]


# Registry definitions
_LANGUAGES: dict[str, LanguageSpec] = {
    "en": LanguageSpec(
        code="en",
        name="English",
        native_name="English",
        default_script="Latn",
        supported_scripts={
            "Latn": ScriptSpec(
                code="Latn",
                name="Latin",
                direction="ltr",
                default_font_windows="Segoe UI",
                default_font_linux="DejaVu Sans",
                fallback_fonts=["Arial", "Helvetica", "sans-serif"],
                char_ranges=[(0x0020, 0x007E), (0x00A0, 0x00FF)],
            )
        },
        tts_lang_code="en-us",
        default_voice="af_heart",
        sample_text="Gradient Descent Optimization and Neural Networks",
    ),
    "hi": LanguageSpec(
        code="hi",
        name="Hindi",
        native_name="हिन्दी",
        default_script="Deva",
        supported_scripts={
            "Deva": ScriptSpec(
                code="Deva",
                name="Devanagari",
                direction="ltr",
                default_font_windows="Nirmala UI",
                default_font_linux="Lohit Devanagari",
                fallback_fonts=["Nirmala Text", "Mangal", "Arial Unicode MS", "Noto Sans Devanagari", "sans-serif"],
                char_ranges=[(0x0900, 0x097F)],
            )
        },
        tts_lang_code="hi-in",
        default_voice=None,
        sample_text="रैखिक प्रतिगमन और न्यूरल नेटवर्क की कार्यप्रणाली",
    ),
    "ur": LanguageSpec(
        code="ur",
        name="Urdu",
        native_name="اردو",
        default_script="Arab",
        supported_scripts={
            "Arab": ScriptSpec(
                code="Arab",
                name="Urdu Nastaliq / Arabic",
                direction="rtl",
                default_font_windows="Arial",
                default_font_linux="Noto Nastaliq Urdu",
                fallback_fonts=["Segoe UI", "Tahoma", "Urdu Typesetting", "Noto Sans Arabic", "sans-serif"],
                char_ranges=[(0x0600, 0x06FF), (0x0750, 0x077F)],
            )
        },
        tts_lang_code="ur-pk",
        default_voice=None,
        sample_text="بائنری سرچ الگورتھم اور ڈیٹا ڈھانچے",
    ),
    "ar": LanguageSpec(
        code="ar",
        name="Arabic",
        native_name="العربية",
        default_script="Arab",
        supported_scripts={
            "Arab": ScriptSpec(
                code="Arab",
                name="Arabic",
                direction="rtl",
                default_font_windows="Arial",
                default_font_linux="DejaVu Sans",
                fallback_fonts=["Segoe UI", "Tahoma", "Amiri", "Noto Sans Arabic", "sans-serif"],
                char_ranges=[(0x0600, 0x06FF)],
            )
        },
        tts_lang_code="ar-xa",
        default_voice=None,
        sample_text="الانحدار الخطي وشبكات الأعصاب الاصطناعية",
    ),
    "ks": LanguageSpec(
        code="ks",
        name="Kashmiri",
        native_name="کٲشُر / कॉशुर",
        default_script="Arab",
        supported_scripts={
            "Arab": ScriptSpec(
                code="Arab",
                name="Perso-Arabic (Nastaliq)",
                direction="rtl",
                default_font_windows="Arial",
                default_font_linux="Noto Nastaliq Urdu",
                fallback_fonts=["Segoe UI", "Tahoma", "Noto Sans Arabic", "sans-serif"],
                char_ranges=[(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)],
            ),
            "Deva": ScriptSpec(
                code="Deva",
                name="Devanagari (Kashmiri variant)",
                direction="ltr",
                default_font_windows="Nirmala UI",
                default_font_linux="Lohit Devanagari",
                fallback_fonts=["Nirmala Text", "Mangal", "Noto Sans Devanagari", "sans-serif"],
                char_ranges=[(0x0900, 0x097F), (0x1CD0, 0x1CFF)],
            ),
        },
        tts_lang_code="ks-in",
        default_voice=None,
        sample_text="کٲشُر زَبانہِ مَنٛز الگورتھم / कॉशुर ज़बानि मंज़ एल्गोरिदम",
    ),
}


class LanguageRegistry:
    """Central registry and query interface for all supported languages."""

    @classmethod
    def list_languages(cls) -> list[dict[str, Any]]:
        """Return serialized list of all supported languages and their scripts."""
        out = []
        for code, lang in _LANGUAGES.items():
            scripts = [
                {
                    "code": s.code,
                    "name": s.name,
                    "direction": s.direction,
                    "font": s.get_font(),
                }
                for s in lang.supported_scripts.values()
            ]
            out.append({
                "code": lang.code,
                "name": lang.name,
                "native_name": lang.native_name,
                "default_script": lang.default_script,
                "scripts": scripts,
                "sample_text": lang.sample_text,
            })
        return out

    @classmethod
    def get_language(cls, lang_code: str) -> LanguageSpec:
        """Lookup language spec by code or alias."""
        clean = (lang_code or "").strip().lower()
        # Aliases
        if clean in ("en", "eng", "english"):
            clean = "en"
        elif clean in ("hi", "hin", "hindi"):
            clean = "hi"
        elif clean in ("ur", "urd", "urdu"):
            clean = "ur"
        elif clean in ("ar", "ara", "arabic"):
            clean = "ar"
        elif clean in ("ks", "kas", "kashmiri"):
            clean = "ks"

        if clean not in _LANGUAGES:
            valid = list(_LANGUAGES.keys())
            raise ValueError(f"Unsupported language code '{lang_code}'. Supported languages: {valid}")
        return _LANGUAGES[clean]

    @classmethod
    def resolve_font(cls, lang_code: str, script_code: str | None = None) -> str:
        """Resolve the primary font for language and script combination."""
        lang = cls.get_language(lang_code)
        script = lang.get_script(script_code)
        return script.get_font()

    @classmethod
    def is_rtl(cls, lang_code: str, script_code: str | None = None) -> bool:
        """Check if language/script is right-to-left."""
        lang = cls.get_language(lang_code)
        script = lang.get_script(script_code)
        return script.direction == "rtl"
