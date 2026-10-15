from manim import *
import numpy as np

class Scene08(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("8. The Complete Symphony: From Concept to Execution", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 5.7s] Engineering feat: Full Pipeline Stage Setup
        summary_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.5, height=0.65, color="#10B981", fill_opacity=0.2),
            Text("The 6 Core Compilation Stages", font_size=15, color="#10B981")
        ).shift(UP * 2.2)
        self.play(FadeIn(summary_badge, shift=DOWN*0.2), run_time=1.2)
        self.wait(3.5)

        # [6.0s -> 18.9s] The 6 sequential stages lighting up in order
        def make_stage(num, label, sub, col):
            b = RoundedRectangle(corner_radius=0.12, width=1.75, height=1.3, stroke_color=col, stroke_width=1.8, fill_color="#0F172A", fill_opacity=0.9)
            t_num = Text(num, font_size=11, color=col).shift(UP * 0.38)
            t_lbl = Text(label, font_size=13, color=WHITE).shift(UP * 0.05)
            t_sub = Text(sub, font_size=10, color="#94A3B8").shift(DOWN * 0.32)
            return VGroup(b, t_num, t_lbl, t_sub)

        stages_data = [
            ("01", "Source", "Raw Text", "#388BFD"),
            ("02", "Lexer", "Tokens", "#F59E0B"),
            ("03", "Parser", "AST Tree", "#A855F7"),
            ("04", "Semantic", "Type Check", "#10B981"),
            ("05", "Optimizer", "IR Passes", "#00F0FF"),
            ("06", "Codegen", "Assembly", "#EC4899")
        ]

        stage_mobs = VGroup(*(make_stage(n, l, s, c) for n, l, s, c in stages_data)).arrange(RIGHT, buff=0.25).shift(UP * 0.4)
        stage_mobs.scale_to_fit_width(12.4)

        arrows = VGroup()
        for i in range(len(stage_mobs) - 1):
            arrows.add(Arrow(stage_mobs[i].get_right(), stage_mobs[i+1].get_left(), buff=0.06, stroke_width=2, color="#64748B", max_tip_length_to_length_ratio=0.3))

        for i, sm in enumerate(stage_mobs):
            if i == 0:
                self.play(FadeIn(sm, shift=UP*0.2), run_time=1.0)
            else:
                self.play(GrowArrow(arrows[i-1]), FadeIn(sm, shift=UP*0.2), run_time=1.5)

        self.wait(1.9)

        # [19.2s -> 28.2s] Energy pulse flowing through the pipeline into Silicon
        pulse_dot = Dot(color="#00F0FF", radius=0.18)
        pulse_dot.move_to(stage_mobs[0].get_center())

        self.play(FadeIn(pulse_dot), run_time=0.5)
        for i in range(1, len(stage_mobs)):
            self.play(
                pulse_dot.animate.move_to(stage_mobs[i].get_center()),
                Indicate(stage_mobs[i], color="#00F0FF", scale_factor=1.05),
                run_time=0.8
            )
        self.play(FadeOut(pulse_dot), run_time=0.4)

        silicon_box = RoundedRectangle(corner_radius=0.15, width=11.2, height=0.9, stroke_color="#00F0FF", stroke_width=2, fill_color="#0F172A", fill_opacity=0.95)
        silicon_text = Text("CPU Execution: Decades of Computer Science Powering Every Click!", font_size=15, color="#00F0FF").scale_to_fit_width(10.4)
        silicon_card = VGroup(silicon_box, silicon_text).move_to(np.array([0.0, -1.6, 0]))

        self.play(FadeIn(silicon_card, shift=UP*0.3), run_time=1.5)
        self.wait(3.5)