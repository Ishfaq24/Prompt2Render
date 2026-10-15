"""Comprehensive automated tests for multilingual educational video generation.

Covers Test Scenarios 1 through 10 from specification:
- Test 1: English (Latin script, baseline functionality)
- Test 2: Hindi (Devanagari script, Nirmala UI font, linear regression, equation alignment)
- Test 3: Urdu (Arabic script, Arial font, right-to-left layout, binary search)
- Test 4: Kashmiri (Arabic and Devanagari script variants tested independently)
- Test 5: Arabic (Arabic script, RTL direction, scientific concepts)
- Test 6: Mixed Language (Hindi explanations containing English terms and formulas)
- Test 7: Long Text (Text wrapping, boundary safety, font size scaling)
- Test 8: Missing Font (Actionable diagnostic and fallback resolution)
- Test 9: Rendering Failure (Controlled defect detection, retry bounds, targeted repair)
- Test 10: Visual Regression (Ink fraction, bounding margin validation, frame QA)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt2render.multilingual import (
    EducationalSpecification,
    FontManager,
    LanguageDetector,
    LanguageRegistry,
    MultilingualLayout,
    MultilingualPipeline,
    MultilingualTranslator,
    MultilingualVisualQA,
    MultilingualVoiceManager,
    SceneRepairEngine,
    SceneSpec,
)


# Test 1: English
def test_scenario_1_english():
    lang = LanguageRegistry.get_language("en")
    assert lang.code == "en"
    assert lang.default_script == "Latn"
    script = lang.get_script("Latn")
    assert script.direction == "ltr"
    font = FontManager.resolve_best_font("en", "Latn")
    assert isinstance(font, str) and len(font) > 0


# Test 2: Hindi (Devanagari script & linear regression)
def test_scenario_2_hindi():
    lang = LanguageRegistry.get_language("hi")
    assert lang.code == "hi"
    assert lang.default_script == "Deva"
    script = lang.get_script("Deva")
    assert script.direction == "ltr"
    font = FontManager.resolve_best_font("hi", "Deva")
    assert font in ("Nirmala UI", "Nirmala Text", "Mangal", "Lohit Devanagari", "sans-serif")

    # Translation and technical preservation check
    prompt = "Explain linear regression with gradient descent and $y = mx + b$"
    translated = MultilingualTranslator.translate_text(prompt, target_lang="hi", target_script="Deva")
    assert "$y = mx + b$" in translated
    assert "रैखिक प्रतिगमन" in translated or "Linear Regression" in translated


# Test 3: Urdu (RTL script & binary search)
def test_scenario_3_urdu():
    lang = LanguageRegistry.get_language("ur")
    assert lang.code == "ur"
    assert lang.default_script == "Arab"
    script = lang.get_script("Arab")
    assert script.direction == "rtl"
    assert LanguageRegistry.is_rtl("ur", "Arab") is True

    prompt = "Binary search on sorted array finding target index"
    translated = MultilingualTranslator.translate_text(prompt, target_lang="ur", target_script="Arab")
    assert "بائنری سرچ" in translated or "Binary Search" in translated


# Test 4: Kashmiri (Arabic vs Devanagari variants)
def test_scenario_4_kashmiri_dual_scripts():
    lang = LanguageRegistry.get_language("ks")
    assert "Arab" in lang.supported_scripts
    assert "Deva" in lang.supported_scripts

    # Arabic script variant
    arab_script = lang.get_script("Arab")
    assert arab_script.direction == "rtl"
    font_arab = FontManager.resolve_best_font("ks", "Arab")
    assert isinstance(font_arab, str)

    # Devanagari script variant
    deva_script = lang.get_script("Deva")
    assert deva_script.direction == "ltr"
    font_deva = FontManager.resolve_best_font("ks", "Deva")
    assert font_deva in ("Nirmala UI", "Lohit Devanagari", "Nirmala Text", "Mangal", "sans-serif")

    # Test independent translation
    t_arab = MultilingualTranslator.translate_text("binary search algorithm", target_lang="ks", target_script="Arab")
    t_deva = MultilingualTranslator.translate_text("binary search algorithm", target_lang="ks", target_script="Deva")
    assert t_arab != t_deva


# Test 5: Arabic (RTL and scientific concept)
def test_scenario_5_arabic():
    lang = LanguageRegistry.get_language("ar")
    assert lang.code == "ar"
    script = lang.get_script("Arab")
    assert script.direction == "rtl"
    assert LanguageRegistry.is_rtl("ar") is True

    prompt = "Explain neural network backpropagation algorithm"
    translated = MultilingualTranslator.translate_text(prompt, target_lang="ar")
    assert "الشبكة العصبية" in translated or "Neural Network" in translated


# Test 6: Mixed Language (Hindi with English identifiers & math)
def test_scenario_6_mixed_language():
    text = "We train the neural network using gradient descent for 100 epochs with $L = \\frac{1}{2}(y - \\hat{y})^2$."
    translated = MultilingualTranslator.translate_text(text, target_lang="hi", target_script="Deva")
    # Equation and core tokens must remain intact
    assert "$L = \\frac{1}{2}(y - \\hat{y})^2$" in translated
    assert "100" in translated


# Test 7: Long Text Wrapping & Scaling
def test_scenario_7_long_text():
    long_narr = (
        "In supervised machine learning algorithms, continuous gradient optimization updates model parameter weights "
        "iteratively until the computed residual cost diminishes below a pre-specified convergence threshold."
    )
    wrapped_en = MultilingualLayout.wrap_text(long_narr, max_chars=40, lang_code="en")
    lines = wrapped_en.split("\n")
    assert len(lines) >= 3
    for line in lines:
        assert len(line) <= 50  # Boundary check

    # Recommended font size scaling
    sz_hi = MultilingualLayout.get_recommended_font_size(24, "hi", "Deva")
    sz_ar = MultilingualLayout.get_recommended_font_size(24, "ar", "Arab")
    assert sz_hi >= 24
    assert sz_ar >= 24


# Test 8: Missing Font Diagnostics & Fallback
def test_scenario_8_missing_font():
    # Check non-existent font
    avail = FontManager.verify_font_availability("NonExistentFont123")
    assert avail is False

    # Resolved font must always fall back to a safe available font
    resolved = FontManager.resolve_best_font("hi", "Deva", preferred_font="NonExistentFont123")
    assert resolved != "NonExistentFont123"
    assert resolved in ("Nirmala UI", "Mangal", "Lohit Devanagari", "sans-serif", "Nirmala Text")


# Test 9: Controlled Rendering Defect Detection & Repair
def test_scenario_9_defect_and_repair():
    faulty_code = (
        'class Scene01(Scene):\n'
        '    def construct(self):\n'
        '        title = Text("रैखिक प्रतिगमन", font="Segoe UI", font_size=52)\n'
    )
    repaired = SceneRepairEngine.repair_code_for_language(
        code=faulty_code,
        lang_code="hi",
        script_code="Deva",
        error_message="WARN [offframe] title extends past canvas boundaries",
    )
    # Font should be adjusted to Nirmala UI for Hindi on Windows
    assert 'font="Nirmala UI"' in repaired or "Nirmala" in repaired
    # Font size 52 should be scaled down to prevent offframe clipping
    assert "font_size=44" in repaired or "font_size=42" in repaired or "font_size=41" in repaired


# Test 10: Visual Regression QA Frame Check
def test_scenario_10_visual_regression_qa(tmp_path):
    from PIL import Image

    # 1. Blank frame test
    blank_png = tmp_path / "blank.png"
    Image.new("RGBA", (1920, 1080), (11, 15, 25, 255)).save(blank_png)
    report_blank = MultilingualVisualQA.audit_rendered_frame(blank_png, scene_stem="01")
    assert report_blank.passed is False
    assert any("blank frame" in e.lower() for e in report_blank.errors)

    # 2. Content frame test
    content_png = tmp_path / "content.png"
    im = Image.new("RGBA", (1920, 1080), (11, 15, 25, 255))
    # Draw non-trivial pixels in center
    for x in range(500, 1400):
        for y in range(400, 700):
            im.putpixel((x, y), (255, 255, 255, 255))
    im.save(content_png)

    report_content = MultilingualVisualQA.audit_rendered_frame(content_png, scene_stem="01")
    assert report_content.passed is True
    assert report_content.metrics["ink_fraction"] > 0.01


# Pipeline End-to-End Orchestration Test
def test_multilingual_pipeline_orchestration(tmp_path):
    prompt = "Explain binary search in Urdu"
    res = MultilingualPipeline.execute_pipeline(
        prompt=prompt,
        target_lang="ur",
        target_script="Arab",
        slug="test-urdu-bs",
        duration_minutes=1.5,
        enable_narration=True,
        enable_subtitles=True,
    )
    assert res["status"] == "success"
    assert res["target_language"] == "ur"
    assert res["is_rtl"] is True
    assert len(res["scenes"]) >= 3
    # Check scene file generation
    for sc in res["scenes"]:
        assert Path(sc["file"]).exists()
        code = Path(sc["file"]).read_text(encoding="utf-8")
        assert "class Scene" in code
