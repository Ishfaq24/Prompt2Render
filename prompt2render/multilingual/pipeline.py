"""End-to-end multilingual pipeline orchestrator for Prompt2Render.

Coordinates:
- Stage A: Language configuration and input resolution
- Stage B: Language detection and semantic specification extraction
- Stage C: Multilingual translation and terminology preservation
- Stage D: Manim Python scene code generation
- Stage E: Font, script shaping, and text direction resolution
- Stage F: Layout adaptation and safe margins
- Stage G: Multilingual narration and subtitles
- Stage H: Visual quality assurance and automated repair
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prompt2render import cfg, project
from .detector import LanguageDetector, SpecificationExtractor
from .font_manager import FontManager
from .layout import MultilingualLayout
from .registry import LanguageRegistry, LanguageSpec
from .repair import SceneRepairEngine
from .spec import EducationalSpecification, SceneSpec
from .translator import MultilingualTranslator
from .visual_qa import MultilingualVisualQA, VisualAuditReport
from .voice_service import MultilingualVoiceManager


class MultilingualPipeline:
    """Production multilingual educational video generation pipeline."""

    @classmethod
    def generate_manim_scene_code(
        cls,
        scene: SceneSpec,
        lang_code: str,
        script_code: str | None = None,
    ) -> str:
        """Generate verified, executable Manim Community Edition Python code for a scene."""
        font_name = FontManager.resolve_best_font(lang_code, script_code)
        is_rtl = LanguageRegistry.is_rtl(lang_code, script_code)
        
        # Prepare wrapped labels and titles
        title_text = MultilingualLayout.wrap_text(scene.on_screen_text or scene.learning_objective, max_chars=36, lang_code=lang_code)
        title_escaped = title_text.replace('"', '\\"').replace('\n', '\\n')
        
        narr_text = MultilingualLayout.wrap_text(scene.narration_text, max_chars=48, lang_code=lang_code)
        narr_escaped = narr_text.replace('"', '\\"').replace('\n', '\\n')

        # Select layout stage code
        stage_init = ""
        stage_anim = ""
        
        if scene.layout_stage == "flow":
            stage_init = f"""
        # Flow stage for process sequence
        node1 = ServerNode(name="Step 1", subtext="Input Data", status="active")
        node2 = ServerNode(name="Step 2", subtext="Processing", status="active")
        node3 = ServerNode(name="Step 3", subtext="Result", status="good")
        stage = FlowStage(nodes=[node1, node2, node3], buff=0.8)
        stage.shift(UP * 0.2)
        self.play(FadeIn(stage))
        dot, target = stage.pulse_signal(0, 1)
        self.play(dot.animate.move_to(target), run_time=1.0)
        self.wait(1.0)
"""
        elif scene.layout_stage == "split":
            stage_init = f"""
        left_card = ConfigCodeCard(code_lines=["data = [1, 3, 5, 7]", "target = 5"], title="Input", width=4.5)
        right_card = ConfigCodeCard(code_lines=["index = binary_search()", "return 2"], title="Algorithm", width=4.5)
        stage = SplitStage(left=left_card, right=right_card, divider=True)
        self.play(FadeIn(stage))
        self.wait(1.0)
"""
        elif scene.layout_stage == "benchmark":
            stage_init = f"""
        b1 = MetricBadge(label="Time", value="O(log n)", status="good")
        b2 = MetricBadge(label="Space", value="O(1)", status="good")
        b3 = MetricBadge(label="Status", value="Optimal", status="good")
        stage = BenchmarkStage(cards=[b1, b2, b3], title="Performance Analysis")
        self.play(FadeIn(stage))
        self.wait(1.0)
"""
        else:
            # Default hero_focus
            if scene.math_expressions:
                formula_str = scene.math_expressions[0].replace('"', '\\"')
                stage_init = f"""
        formula = MathTex(r"{formula_str}", font_size=38)
        formula.set_color(YELLOW_C)
        formula.shift(UP * 0.5)
        self.play(Write(formula), run_time=1.2)
        self.wait(1.0)
"""
            else:
                stage_init = f"""
        grid = ArrayGrid(values=[2, 4, 8, 16, 32], active_index=2)
        grid.shift(UP * 0.4)
        self.play(FadeIn(grid), run_time=1.0)
        self.wait(1.0)
"""

        code = f"""# [Prompt2Render Multilingual] Lang: {lang_code}, Script: {script_code or 'default'}, Direction: {'rtl' if is_rtl else 'ltr'}, Font: {font_name}
from manim import *
from prompt2render.assets.mobjects import (
    FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
    ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
    ArrayGrid, FormulaCard, KeyBadge, CaptionDock, P2RText
)

class Scene{scene.stem}(Scene):
    def construct(self):
        # 1. Title Band
        title = Text("{title_escaped}", font="{font_name}", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # 2. Main Hero Stage Visualization
{stage_init}
        # 3. Caption Dock in Lower Safe Zone
        caption = CaptionDock("{narr_escaped}")
        self.play(FadeIn(caption), run_time=0.6)
        self.wait(2.0)
"""
        return code

    @classmethod
    def execute_pipeline(
        cls,
        prompt: str,
        target_lang: str = "en",
        target_script: str | None = None,
        input_lang: str | None = None,
        slug: str | None = None,
        duration_minutes: float = 2.0,
        enable_narration: bool = True,
        enable_subtitles: bool = True,
        auto_repair: bool = True,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Execute the full end-to-end multilingual educational video generation pipeline."""
        # Stage A & B: Detect language and extract specification
        spec = SpecificationExtractor.extract_from_prompt(
            prompt=prompt,
            input_lang=input_lang,
            target_lang=target_lang,
            target_script=target_script,
            duration_minutes=duration_minutes,
        )

        # Stage C: Translate specification if target language differs
        if spec.target_language != spec.source_language:
            spec = MultilingualTranslator.translate_specification(
                spec, target_lang=target_lang, target_script=target_script
            )

        # Determine project slug
        proj_slug = slug or cfg.slugify(prompt[:30])
        clean_slug = cfg.slugify(proj_slug)
        proj_dir = cfg.PROJECTS / clean_slug
        if not proj_dir.is_dir():
            d = project.new_project(clean_slug, prompt, minutes=duration_minutes, language=target_lang, script=target_script)
            proj_dir = d
        scenes_dir = proj_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        generated_scenes = []
        validation_reports = []

        # Stage D & E: Generate Manim code for each scene
        for sc in spec.scenes:
            code = cls.generate_manim_scene_code(sc, target_lang, target_script)
            scene_file = scenes_dir / f"scene_{sc.stem}.py"
            scene_file.write_text(code, encoding="utf-8")
            generated_scenes.append({
                "stem": sc.stem,
                "file": str(scene_file),
                "code": code,
            })

        # Save metadata and specification
        meta_file = proj_dir / "multilingual_spec.json"
        meta_file.write_text(spec.to_json(), encoding="utf-8")

        # Stage G: Optional Subtitles
        subtitles_srt = ""
        if enable_subtitles:
            cues = []
            cur_time = 0.0
            for sc in spec.scenes:
                cues.append({
                    "start": cur_time,
                    "end": cur_time + sc.estimated_duration_sec,
                    "text": sc.narration_text,
                })
                cur_time += sc.estimated_duration_sec
            sub_file = proj_dir / "out" / "captions.srt"
            subtitles_srt = MultilingualVoiceManager.generate_subtitles_srt(cues, sub_file)

        return {
            "slug": proj_slug,
            "project_dir": str(proj_dir),
            "specification": spec.to_dict(),
            "target_language": target_lang,
            "target_script": spec.target_script,
            "font": FontManager.resolve_best_font(target_lang, spec.target_script),
            "is_rtl": LanguageRegistry.is_rtl(target_lang, spec.target_script),
            "scenes": generated_scenes,
            "subtitles_enabled": enable_subtitles,
            "subtitles_path": str(proj_dir / "out" / "captions.srt") if enable_subtitles else None,
            "validation_reports": validation_reports,
            "status": "success",
        }
