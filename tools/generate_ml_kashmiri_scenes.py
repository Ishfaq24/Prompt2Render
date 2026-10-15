"""Generates production-grade Manim CE scenes for Machine Learning in Kashmiri.

Scenes are designed with:
- Dark theme (#0B0F19 background, high-contrast crisp palettes)
- Clear typography with English technical labels + Kashmiri script titles
- Precise timings dynamically synchronized to narration audio lengths
- Rich mathematical expressions, coordinate graphs, neural/agent widgets, and data flows
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ_DIR = ROOT / "projects" / "machine-learning-kashmiri"
SCENES_DIR = PROJ_DIR / "scenes"
SCENES_DIR.mkdir(parents=True, exist_ok=True)

def generate_scenes():
    # Read audio durations if available, else use standard targets
    amap_file = PROJ_DIR / "build" / "audio_map.json"
    durations = {"01": 28.0, "02": 32.0, "03": 30.0, "04": 30.0, "05": 30.0}
    if amap_file.exists():
        amap = json.loads(amap_file.read_text(encoding="utf-8"))
        for stem, info in amap.get("sections", {}).items():
            durations[stem] = float(info["dur"])

    # =========================================================================
    # SCENE 01: Paradigm Shift (Traditional Programming vs Machine Learning)
    # =========================================================================
    scene_01 = f'''from manim import *
import numpy as np

class Scene01(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"
        total_time = {durations['01']:.2f}

        # 1. Header Band
        title = Text("Machine Learning: Paradigm Shift", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ کیا چھُ؟ (Rules vs Learning)", font="Arial", font_size=16, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.2)

        # 2. Left Card: Traditional Programming
        left_card = RoundedRectangle(
            corner_radius=0.2, width=5.8, height=4.6,
            stroke_color="#334155", stroke_width=2.0,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(LEFT * 3.3 + DOWN * 0.4)
        
        left_title = Text("Traditional Programming", font_size=18, weight=BOLD, color="#94A3B8").move_to(left_card.get_top() + DOWN * 0.45)
        trad_sub = Text("روایتی پروگرامنگ (قواعد دِنہٕ سٟتؠ)", font="Arial", font_size=12, color="#64748B").next_to(left_title, DOWN, buff=0.1)

        in_data = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.55, color="#475569", fill_color="#1E293B", fill_opacity=0.9).move_to(LEFT * 3.3 + UP * 0.5)
        in_data_txt = Text("Data (ان پُٹ ڈیٹا)", font_size=12, color=WHITE).move_to(in_data.get_center())
        
        in_rules = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.55, color="#6366F1", fill_color="#312E81", fill_opacity=0.9).move_to(LEFT * 3.3 + DOWN * 0.25)
        in_rules_txt = Text("Rules (انسان ہٕنٛدِ قواعد)", font_size=12, color="#A5B4FC").move_to(in_rules.get_center())

        arrow_trad = Arrow(start=LEFT * 3.3 + DOWN * 0.65, end=LEFT * 3.3 + DOWN * 1.35, color="#94A3B8", buff=0.08)
        
        out_answers = RoundedRectangle(corner_radius=0.1, width=3.6, height=0.6, color="#10B981", fill_color="#064E3B", fill_opacity=0.9).move_to(LEFT * 3.3 + DOWN * 1.8)
        out_answers_txt = Text("Answers / Output (جواب)", font_size=13, weight=BOLD, color="#34D399").move_to(out_answers.get_center())

        left_grp = VGroup(left_card, left_title, trad_sub, in_data, in_data_txt, in_rules, in_rules_txt, arrow_trad, out_answers, out_answers_txt)

        # 3. Right Card: Machine Learning
        right_card = RoundedRectangle(
            corner_radius=0.2, width=5.8, height=4.6,
            stroke_color="#38BDF8", stroke_width=2.5,
            fill_color="#082F49", fill_opacity=0.75
        ).move_to(RIGHT * 3.3 + DOWN * 0.4)

        right_title = Text("Machine Learning", font_size=20, weight=BOLD, color="#38BDF8").move_to(right_card.get_top() + DOWN * 0.45)
        ml_sub = Text("مشین لرننگ (ڈیٹا پؠٹھٕ سؠکھُن)", font="Arial", font_size=12, color="#7DD3FC").next_to(right_title, DOWN, buff=0.1)

        ml_data = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.55, color="#0284C7", fill_color="#075985", fill_opacity=0.9).move_to(RIGHT * 3.3 + UP * 0.5)
        ml_data_txt = Text("Data (تاریخی ڈیٹا)", font_size=12, color=WHITE).move_to(ml_data.get_center())

        ml_answers = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.55, color="#10B981", fill_color="#064E3B", fill_opacity=0.9).move_to(RIGHT * 3.3 + DOWN * 0.25)
        ml_answers_txt = Text("Answers (ماضی ہٕنٛدِ جواب)", font_size=12, color="#6EE7B7").move_to(ml_answers.get_center())

        arrow_ml = Arrow(start=RIGHT * 3.3 + DOWN * 0.65, end=RIGHT * 3.3 + DOWN * 1.35, color="#38BDF8", buff=0.08)

        out_model = RoundedRectangle(corner_radius=0.15, width=4.0, height=0.7, color="#F59E0B", fill_color="#78350F", fill_opacity=0.95).move_to(RIGHT * 3.3 + DOWN * 1.8)
        out_model_txt = Text("Learned Rules / Model (ماڈل)", font_size=13, weight=BOLD, color="#FCD34D").move_to(out_model.get_center())

        right_grp = VGroup(right_card, right_title, ml_sub, ml_data, ml_data_txt, ml_answers, ml_answers_txt, arrow_ml, out_model, out_model_txt)

        self.play(FadeIn(left_grp, shift=RIGHT*0.3), run_time=1.8)
        self.wait(1.5)
        self.play(FadeIn(right_grp, shift=LEFT*0.3), run_time=1.8)
        self.wait(2.0)

        # Pulse highlight on Learned Model
        pulse_ring = RoundedRectangle(corner_radius=0.2, width=4.3, height=0.9, color="#F59E0B", stroke_width=3.5).move_to(out_model.get_center())
        self.play(Create(pulse_ring), out_model.animate.scale(1.05), run_time=1.2)
        self.play(FadeOut(pulse_ring), out_model.animate.scale(1/1.05), run_time=1.0)
        
        elapsed = 1.2 + 1.8 + 1.5 + 1.8 + 2.0 + 1.2 + 1.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''

    # =========================================================================
    # SCENE 02: Three Paradigms of Machine Learning
    # =========================================================================
    scene_02 = f'''from manim import *

class Scene02(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"
        total_time = {durations['02']:.2f}

        # 1. Header
        title = Text("Three Paradigms of Machine Learning", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ ہٕنٛدی ترٛے اہم قسٕم", font="Arial", font_size=16, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.2)

        # 2. Three Cards
        # Card 1: Supervised
        c1 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#0284C7", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.9).move_to(LEFT * 4.3 + DOWN * 0.45)
        t1 = Text("Supervised", font_size=18, weight=BOLD, color="#38BDF8").move_to(c1.get_top() + DOWN * 0.45)
        s1 = Text("سُوپر وائزڈ (لیبلڈ ڈیٹا)", font="Arial", font_size=12, color="#7DD3FC").next_to(t1, DOWN, buff=0.1)
        tag1 = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.5, color="#0369A1", fill_color="#075985", fill_opacity=0.8).move_to(c1.get_center() + UP * 0.5)
        tag1_txt = Text("Input X -> Label Y", font_size=11, color=WHITE, weight=BOLD).move_to(tag1.get_center())
        # Dot plot icon
        dot1 = Dot(point=c1.get_center() + LEFT*0.6 + DOWN*0.2, color="#38BDF8")
        dot2 = Dot(point=c1.get_center() + RIGHT*0.6 + DOWN*0.6, color="#F43F5E")
        line1 = Line(start=c1.get_center() + LEFT*1.0 + DOWN*0.8, end=c1.get_center() + RIGHT*1.0 + DOWN*0.0, color="#64748B")
        ex1_a = Text("Classification (کلاسیفیکیشن)", font_size=11, color="#CBD5E1")
        ex1_b = Text("Regression (ریگریشن)", font_size=11, color="#CBD5E1").next_to(ex1_a, DOWN, buff=0.1)
        ex1 = VGroup(ex1_a, ex1_b).move_to(c1.get_bottom() + UP * 0.6)
        grp1 = VGroup(c1, t1, s1, tag1, tag1_txt, dot1, dot2, line1, ex1)

        # Card 2: Unsupervised
        c2 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.9).move_to(DOWN * 0.45)
        t2 = Text("Unsupervised", font_size=18, weight=BOLD, color="#34D399").move_to(c2.get_top() + DOWN * 0.45)
        s2 = Text("اَن سُوپر وائزڈ (بغیر لیبل)", font="Arial", font_size=12, color="#6EE7B7").next_to(t2, DOWN, buff=0.1)
        tag2 = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.5, color="#047857", fill_color="#065F46", fill_opacity=0.8).move_to(c2.get_center() + UP * 0.5)
        tag2_txt = Text("Unlabeled Data X", font_size=11, color=WHITE, weight=BOLD).move_to(tag2.get_center())
        # Cluster circles
        cl1 = Circle(radius=0.35, color="#34D399", fill_opacity=0.2).move_to(c2.get_center() + LEFT*0.6 + DOWN*0.35)
        cl2 = Circle(radius=0.35, color="#A78BFA", fill_opacity=0.2).move_to(c2.get_center() + RIGHT*0.6 + DOWN*0.35)
        ex2_a = Text("Clustering (کلسٹرنگ)", font_size=11, color="#CBD5E1")
        ex2_b = Text("Pattern Discovery (پیٹرن)", font_size=11, color="#CBD5E1").next_to(ex2_a, DOWN, buff=0.1)
        ex2 = VGroup(ex2_a, ex2_b).move_to(c2.get_bottom() + UP * 0.6)
        grp2 = VGroup(c2, t2, s2, tag2, tag2_txt, cl1, cl2, ex2)

        # Card 3: Reinforcement
        c3 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.9).move_to(RIGHT * 4.3 + DOWN * 0.45)
        t3 = Text("Reinforcement", font_size=18, weight=BOLD, color="#FBBF24").move_to(c3.get_top() + DOWN * 0.45)
        s3 = Text("ری اِنفورسمنٹ (انعام و سزا)", font="Arial", font_size=12, color="#FDE68A").next_to(t3, DOWN, buff=0.1)
        tag3 = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.5, color="#B45309", fill_color="#92400E", fill_opacity=0.8).move_to(c3.get_center() + UP * 0.5)
        tag3_txt = Text("Agent <-> Environment", font_size=11, color=WHITE, weight=BOLD).move_to(tag3.get_center())
        # Loop badge
        loop_arrow = CurvedArrow(start_point=c3.get_center() + LEFT*0.7 + DOWN*0.4, end_point=c3.get_center() + RIGHT*0.7 + DOWN*0.4, angle=TAU/3, color="#FBBF24")
        ex3_a = Text("Reward & Penalty (انعام)", font_size=11, color="#CBD5E1")
        ex3_b = Text("Robotics & Games (گیمز)", font_size=11, color="#CBD5E1").next_to(ex3_a, DOWN, buff=0.1)
        ex3 = VGroup(ex3_a, ex3_b).move_to(c3.get_bottom() + UP * 0.6)
        grp3 = VGroup(c3, t3, s3, tag3, tag3_txt, loop_arrow, ex3)

        self.play(FadeIn(grp1, shift=UP*0.2), run_time=1.5)
        self.wait(1.5)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.5)
        self.wait(1.5)
        self.play(FadeIn(grp3, shift=UP*0.2), run_time=1.5)
        self.wait(2.0)

        elapsed = 1.2 + 1.5 + 1.5 + 1.5 + 1.5 + 1.5 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''

    # =========================================================================
    # SCENE 03: Loss Function Optimization & Gradient Descent
    # =========================================================================
    scene_03 = f'''from manim import *
import numpy as np

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"
        total_time = {durations['03']:.2f}

        # 1. Header
        title = Text("How Models Learn: Loss & Gradient Descent", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("لاس فنکشن (غلطی ناپن) تہٕ گریڈینٹ ڈیسینٹ", font="Arial", font_size=16, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.2)

        # 2. Formula Cards on Left
        card_formula = RoundedRectangle(
            corner_radius=0.2, width=5.2, height=4.5,
            stroke_color="#334155", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(LEFT * 3.7 + DOWN * 0.45)

        f_title = Text("Objective & Update Rules", font_size=16, weight=BOLD, color="#38BDF8").move_to(card_formula.get_top() + DOWN * 0.4)
        
        # Loss formula
        loss_lbl = Text("1. Mean Squared Error (Loss):", font_size=12, color="#94A3B8").move_to(card_formula.get_top() + DOWN * 1.0 + LEFT * 0.4)
        loss_math = MathTex(r"J(w) = \\frac{{1}}{{N}} \\sum_{{i=1}}^{{N}} (y_i - \\hat{{y}}_i)^2", font_size=26, color=YELLOW_C).next_to(loss_lbl, DOWN, buff=0.25).align_to(loss_lbl, LEFT)

        # Update formula
        up_lbl = Text("2. Gradient Descent Update:", font_size=12, color="#94A3B8").move_to(card_formula.get_top() + DOWN * 2.3 + LEFT * 0.4)
        up_math = MathTex(r"w_{{new}} = w_{{old}} - \\alpha \\nabla J(w)", font_size=26, color="#38BDF8").next_to(up_lbl, DOWN, buff=0.25).align_to(up_lbl, LEFT)

        note_kash = Text("ہر قدمَس سٟتؠ چھِ غلطی کم گژھان", font="Arial", font_size=12, color="#34D399").move_to(card_formula.get_bottom() + UP * 0.45)

        left_side = VGroup(card_formula, f_title, loss_lbl, loss_math, up_lbl, up_math, note_kash)
        self.play(FadeIn(left_side), run_time=1.5)

        # 3. Parabolic Loss Curve on Right
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[0, 9, 2],
            x_length=5.6,
            y_length=4.2,
            axis_config={{"color": "#64748B", "stroke_width": 2}},
        ).move_to(RIGHT * 3.3 + DOWN * 0.45)

        x_lbl = Text("Weight (w)", font_size=12, color="#CBD5E1").next_to(axes.x_axis, DOWN, buff=0.15)
        y_lbl = Text("Loss J(w)", font_size=12, color="#CBD5E1").next_to(axes.y_axis, UP, buff=0.15)

        parabola = axes.plot(lambda x: x**2, x_range=[-2.8, 2.8], color="#38BDF8", stroke_width=3.5)
        min_dot = Dot(point=axes.c2p(0, 0), radius=0.08, color="#10B981")
        min_lbl = Text("Global Min w*", font_size=11, color="#10B981", weight=BOLD).next_to(min_dot, DOWN, buff=0.15)

        self.play(Create(axes), FadeIn(x_lbl), FadeIn(y_lbl), Create(parabola), run_time=1.8)
        self.play(FadeIn(min_dot), FadeIn(min_lbl), run_time=0.8)

        # 4. Animated Optimizer Ball Stepping Down
        ball = Dot(point=axes.c2p(2.5, 6.25), radius=0.14, color="#F59E0B")
        ball_lbl = Text("Initial Loss", font_size=11, color="#FBBF24").next_to(ball, RIGHT, buff=0.15)
        self.play(FadeIn(ball), FadeIn(ball_lbl), run_time=1.0)
        self.wait(1.0)

        # Step 1
        self.play(ball.animate.move_to(axes.c2p(1.6, 2.56)), FadeOut(ball_lbl), run_time=1.2)
        # Step 2
        self.play(ball.animate.move_to(axes.c2p(0.9, 0.81)), run_time=1.2)
        # Step 3 to optimal
        self.play(ball.animate.move_to(axes.c2p(0.0, 0.0)), run_time=1.5)
        
        # Convergence glow
        glow_ring = Circle(radius=0.4, color="#10B981", stroke_width=3.0).move_to(axes.c2p(0, 0))
        conv_txt = Text("Optimized!", font_size=12, color="#10B981", weight=BOLD).next_to(axes.c2p(0, 0), UP, buff=0.25)
        self.play(Create(glow_ring), FadeIn(conv_txt), run_time=1.0)
        self.play(FadeOut(glow_ring), run_time=0.8)

        elapsed = 1.2 + 1.5 + 1.8 + 0.8 + 1.0 + 1.0 + 1.2 + 1.2 + 1.5 + 1.0 + 0.8
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''

    # =========================================================================
    # SCENE 04: Overfitting vs Underfitting
    # =========================================================================
    scene_04 = f'''from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"
        total_time = {durations['04']:.2f}

        # 1. Header
        title = Text("Overfitting vs Underfitting (Generalization)", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("ماڈل پیچیدگی تہٕ متوازن جنرلائزیشن", font="Arial", font_size=16, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.2)

        # Common data points for three sub-plots
        pts_x = [-1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8]
        pts_y = [2.8, 1.5, 0.4, 0.1, 0.5, 1.6, 2.7]

        # Panel 1: Underfitting
        p1 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#EF4444", stroke_width=2.0, fill_color="#450A0A", fill_opacity=0.75).move_to(LEFT * 4.3 + DOWN * 0.45)
        t1 = Text("Underfitting", font_size=18, weight=BOLD, color="#F87171").move_to(p1.get_top() + DOWN * 0.4)
        s1 = Text("انڈرفِٹِنٛگ (زیادٕ سادٕ ماڈل)", font="Arial", font_size=11, color="#FECACA").next_to(t1, DOWN, buff=0.08)
        
        ax1 = Axes(x_range=[-2.2, 2.2, 1], y_range=[-0.5, 3.5, 1], x_length=3.2, y_length=2.4, axis_config={{"color": "#64748B", "stroke_width": 1.5}}).move_to(p1.get_center() + DOWN * 0.15)
        dots1 = VGroup(*[Dot(ax1.c2p(x, y), radius=0.06, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        line_under = ax1.plot(lambda x: 1.4, color="#EF4444", stroke_width=3.0)
        b1 = Text("High Bias (بڑی غلطی)", font_size=11, color="#F87171", weight=BOLD).move_to(p1.get_bottom() + UP * 0.45)
        grp1 = VGroup(p1, t1, s1, ax1, dots1, line_under, b1)

        # Panel 2: Good Fit
        p2 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#10B981", stroke_width=2.5, fill_color="#064E3B", fill_opacity=0.85).move_to(DOWN * 0.45)
        t2 = Text("Optimal Fit", font_size=18, weight=BOLD, color="#34D399").move_to(p2.get_top() + DOWN * 0.4)
        s2 = Text("متوازن ماڈل (اصل جنرلائزیشن)", font="Arial", font_size=11, color="#A7F3D0").next_to(t2, DOWN, buff=0.08)
        
        ax2 = Axes(x_range=[-2.2, 2.2, 1], y_range=[-0.5, 3.5, 1], x_length=3.2, y_length=2.4, axis_config={{"color": "#64748B", "stroke_width": 1.5}}).move_to(p2.get_center() + DOWN * 0.15)
        dots2 = VGroup(*[Dot(ax2.c2p(x, y), radius=0.06, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        curve_opt = ax2.plot(lambda x: 0.8 * x**2 + 0.15, color="#10B981", stroke_width=3.5)
        b2 = Text("Balanced & Robust", font_size=11, color="#34D399", weight=BOLD).move_to(p2.get_bottom() + UP * 0.45)
        grp2 = VGroup(p2, t2, s2, ax2, dots2, curve_opt, b2)

        # Panel 3: Overfitting
        p3 = RoundedRectangle(corner_radius=0.2, width=4.0, height=4.6, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.75).move_to(RIGHT * 4.3 + DOWN * 0.45)
        t3 = Text("Overfitting", font_size=18, weight=BOLD, color="#FBBF24").move_to(p3.get_top() + DOWN * 0.4)
        s3 = Text("اوورفِٹِنٛگ (رٹہٕ مارُن)", font="Arial", font_size=11, color="#FDE68A").next_to(t3, DOWN, buff=0.08)
        
        ax3 = Axes(x_range=[-2.2, 2.2, 1], y_range=[-0.5, 3.5, 1], x_length=3.2, y_length=2.4, axis_config={{"color": "#64748B", "stroke_width": 1.5}}).move_to(p3.get_center() + DOWN * 0.15)
        dots3 = VGroup(*[Dot(ax3.c2p(x, y), radius=0.06, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        # Oscillating curve passing through noise
        curve_over = ax3.plot(lambda x: 0.8*x**2 + 0.15 + 0.4*np.sin(6*x), color="#F59E0B", stroke_width=2.8)
        b3 = Text("High Variance (شور رٹُن)", font_size=11, color="#FBBF24", weight=BOLD).move_to(p3.get_bottom() + UP * 0.45)
        grp3 = VGroup(p3, t3, s3, ax3, dots3, curve_over, b3)

        self.play(FadeIn(grp1, shift=LEFT*0.3), run_time=1.5)
        self.wait(1.5)
        self.play(FadeIn(grp2, shift=UP*0.3), run_time=1.5)
        self.wait(1.5)
        self.play(FadeIn(grp3, shift=RIGHT*0.3), run_time=1.5)
        self.wait(2.0)

        # Star marker on Optimal Fit
        star = Star(n=5, outer_radius=0.25, inner_radius=0.12, color="#34D399", fill_opacity=1.0).next_to(p2, UP, buff=0.1)
        self.play(FadeIn(star, scale=1.3), run_time=1.0)
        self.wait(1.5)

        elapsed = 1.2 + 1.5 + 1.5 + 1.5 + 1.5 + 1.5 + 2.0 + 1.0 + 1.5
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''

    # =========================================================================
    # SCENE 05: Real-World Applications & Summary
    # =========================================================================
    scene_05 = f'''from manim import *

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"
        total_time = {durations['05']:.2f}

        # 1. Header
        title = Text("Real-World Applications of Machine Learning", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("اصل دُنیاہَس مَنٛز استعمال تہٕ اہم خلاصہٕ", font="Arial", font_size=16, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.2)

        # 2. 2x2 Feature Grid
        # Box 1: Healthcare / Medical Imaging
        b1 = RoundedRectangle(corner_radius=0.15, width=5.8, height=1.9, stroke_color="#0284C7", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.85).move_to(LEFT * 3.3 + UP * 0.7)
        t1 = Text("Medical Imaging & Healthcare", font_size=14, weight=BOLD, color="#38BDF8").move_to(b1.get_top() + DOWN * 0.35)
        d1 = Text("صحت عامہ: ایکس رے تہٕ ایم آر آئی جانچ، بیماری تشخیص", font="Arial", font_size=11, color="#CBD5E1").next_to(t1, DOWN, buff=0.15)
        box1 = VGroup(b1, t1, d1)

        # Box 2: NLP & Kashmiri AI
        b2 = RoundedRectangle(corner_radius=0.15, width=5.8, height=1.9, stroke_color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.85).move_to(RIGHT * 3.3 + UP * 0.7)
        t2 = Text("Speech & Kashmiri Translation", font_size=14, weight=BOLD, color="#34D399").move_to(b2.get_top() + DOWN * 0.35)
        d2 = Text("کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ تہٕ آواز ہٕنٛز شناخت", font="Arial", font_size=11, color="#CBD5E1").next_to(t2, DOWN, buff=0.15)
        box2 = VGroup(b2, t2, d2)

        # Box 3: Autonomous Vehicles
        b3 = RoundedRectangle(corner_radius=0.15, width=5.8, height=1.9, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.85).move_to(LEFT * 3.3 + DOWN * 1.5)
        t3 = Text("Autonomous Systems & Robotics", font_size=14, weight=BOLD, color="#FBBF24").move_to(b3.get_top() + DOWN * 0.35)
        d3 = Text("خود مختار گاڑؠن ہٕنٛز ڈرائیونگ تہٕ خودکار روبوٹس", font="Arial", font_size=11, color="#CBD5E1").next_to(t3, DOWN, buff=0.15)
        box3 = VGroup(b3, t3, d3)

        # Box 4: Recommendation Systems
        b4 = RoundedRectangle(corner_radius=0.15, width=5.8, height=1.9, stroke_color="#8B5CF6", stroke_width=2.0, fill_color="#4C1D95", fill_opacity=0.85).move_to(RIGHT * 3.3 + DOWN * 1.5)
        t4 = Text("Recommendation & Prediction", font_size=14, weight=BOLD, color="#A78BFA").move_to(b4.get_top() + DOWN * 0.35)
        d4 = Text("یوٹیوب، ای کامرس تجاویز تہٕ مالی پیشن گوئی", font="Arial", font_size=11, color="#CBD5E1").next_to(t4, DOWN, buff=0.15)
        box4 = VGroup(b4, t4, d4)

        self.play(FadeIn(box1, shift=RIGHT*0.2), FadeIn(box2, shift=LEFT*0.2), run_time=1.8)
        self.wait(1.5)
        self.play(FadeIn(box3, shift=RIGHT*0.2), FadeIn(box4, shift=LEFT*0.2), run_time=1.8)
        self.wait(2.5)

        # 3. Thank You / Concluding Banner
        thx_box = RoundedRectangle(corner_radius=0.2, width=8.2, height=1.2, stroke_color="#38BDF8", stroke_width=2.5, fill_color="#0F172A", fill_opacity=0.98).move_to(DOWN * 0.4)
        thx_txt1 = Text("Machine Learning: Shaping the Future of AI", font_size=16, weight=BOLD, color=WHITE).move_to(thx_box.get_center() + UP * 0.22)
        thx_txt2 = Text("شُکریہ! Thank You for Learning with Prompt2Render", font="Arial", font_size=13, color="#38BDF8").move_to(thx_box.get_center() + DOWN * 0.22)
        thx_grp = VGroup(thx_box, thx_txt1, thx_txt2)

        self.play(FadeIn(thx_grp, scale=1.1), run_time=1.5)
        self.wait(2.0)

        elapsed = 1.2 + 1.8 + 1.5 + 1.8 + 2.5 + 1.5 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''

    # Write scenes
    (SCENES_DIR / "scene_01.py").write_text(scene_01, encoding="utf-8")
    (SCENES_DIR / "scene_02.py").write_text(scene_02, encoding="utf-8")
    (SCENES_DIR / "scene_03.py").write_text(scene_03, encoding="utf-8")
    (SCENES_DIR / "scene_04.py").write_text(scene_04, encoding="utf-8")
    (SCENES_DIR / "scene_05.py").write_text(scene_05, encoding="utf-8")
    print(f"Generated 5 Manim scenes under {SCENES_DIR}")

if __name__ == "__main__":
    generate_scenes()
