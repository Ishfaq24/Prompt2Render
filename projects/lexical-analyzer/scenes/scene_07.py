from manim import *
import numpy as np

class Scene07(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("7. DFA State Minimization: Hopcroft's Efficiency", font_size=24, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.8, height=0.55, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Optimization: Hopcroft's Partition Refinement", font_size=13, color="#FFB703").scale_to_fit_width(4.4)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.0)

        # [7.8s -> 16.7s] Left Card: Raw DFA with Redundant States (x = -3.5)
        raw_box = RoundedRectangle(corner_radius=0.15, width=4.8, height=3.3, stroke_color="#64748B", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        raw_title = Text("Raw DFA (6 States - Redundant)", font_size=12, color="#94A3B8")

        # 6 circle states arranged in 2 rows
        r_s0 = Circle(radius=0.25, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-5.2, 0.4, 0]))
        r_s1 = Circle(radius=0.25, stroke_color="#388BFD", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-4.0, 0.7, 0]))
        r_s2 = Circle(radius=0.25, stroke_color="#388BFD", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-4.0, 0.1, 0]))
        r_s3 = Circle(radius=0.25, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-2.8, 0.7, 0]))
        r_s4 = Circle(radius=0.25, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-2.8, 0.1, 0]))
        r_s5 = Circle(radius=0.25, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-1.6, 0.4, 0]))

        t_s0 = Text("s0", font_size=10, color=WHITE).move_to(r_s0)
        t_s1 = Text("s1", font_size=10, color=WHITE).move_to(r_s1)
        t_s2 = Text("s2", font_size=10, color=WHITE).move_to(r_s2)
        t_s3 = Text("s3*", font_size=9, color="#10B981").move_to(r_s3)
        t_s4 = Text("s4*", font_size=9, color="#10B981").move_to(r_s4)
        t_s5 = Text("s5", font_size=10, color=WHITE).move_to(r_s5)

        raw_nodes = VGroup(r_s0, r_s1, r_s2, r_s3, r_s4, r_s5, t_s0, t_s1, t_s2, t_s3, t_s4, t_s5)
        raw_note = Text("s1 = s2 (equivalent) | s3 = s4 (equivalent)", font_size=9, color="#FFB703").scale_to_fit_width(4.2)
        raw_content = VGroup(raw_title, raw_nodes, raw_note).arrange(DOWN, buff=0.22)
        raw_card = VGroup(raw_box, raw_content).move_to(np.array([-3.5, -0.1, 0]))

        self.play(FadeIn(raw_card, shift=RIGHT*0.3), run_time=1.5)
        self.wait(4.5)

        # [16.7s -> 31.7s] Partition Refinement process in Center
        arrow_min = Arrow(raw_card.get_right(), np.array([1.2, -0.1, 0]), color="#FFB703", buff=0.1, stroke_width=2.5)

        # Right Card: Minimal DFA (x = 3.5)
        min_box = RoundedRectangle(corner_radius=0.15, width=4.8, height=3.3, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        min_title = Text("Minimal DFA (3 States)", font_size=13, color="#10B981")

        # 3 minimal states
        m0 = Circle(radius=0.38, stroke_color=WHITE, stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([2.0, 0.4, 0]))
        m0_t = Text("M0", font_size=11, color=WHITE).move_to(m0)
        m0_sub = Text("{s0, s5}", font_size=8, color="#94A3B8").next_to(m0, DOWN, buff=0.06)

        m1 = Circle(radius=0.38, stroke_color="#00F0FF", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([3.6, 0.4, 0]))
        m1_t = Text("M1", font_size=11, color="#00F0FF").move_to(m1)
        m1_sub = Text("{s1, s2}", font_size=8, color="#94A3B8").next_to(m1, DOWN, buff=0.06)

        m2_out = Circle(radius=0.42, stroke_color="#10B981", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([5.2, 0.4, 0]))
        m2_in = Circle(radius=0.34, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.0).move_to(m2_out)
        m2_t = Text("M2*", font_size=11, color="#10B981").move_to(m2_out)
        m2_sub = Text("{s3, s4}", font_size=8, color="#10B981").next_to(m2_out, DOWN, buff=0.06)

        e_m01 = Arrow(m0.get_right(), m1.get_left(), color="#00F0FF", buff=0.05, stroke_width=2)
        e_m12 = Arrow(m1.get_right(), m2_out.get_left(), color="#10B981", buff=0.05, stroke_width=2)

        min_nodes = VGroup(m0, m0_t, m0_sub, m1, m1_t, m1_sub, m2_out, m2_in, m2_t, m2_sub, e_m01, e_m12)
        min_note = Text("Smallest possible transition table!", font_size=10, color="#10B981")
        min_content = VGroup(min_title, min_nodes, min_note).arrange(DOWN, buff=0.2)
        min_card = VGroup(min_box, min_content).move_to(np.array([3.5, -0.1, 0]))

        self.play(GrowArrow(arrow_min), FadeIn(min_card, shift=LEFT*0.3), run_time=1.5)
        self.wait(4.5)

        # [32.0s -> 40.5s] Bottom Summary Callout
        footer_pill = VGroup(
            RoundedRectangle(corner_radius=0.1, width=10.6, height=0.6, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95),
            Text("Hopcroft Theorem: Produces the provably unique minimal DFA for optimal CPU cache locality", font_size=11, color="#10B981").scale_to_fit_width(10.0)
        ).move_to(np.array([0.0, -2.1, 0]))

        self.play(FadeIn(footer_pill, shift=UP*0.2), Indicate(min_card, color="#10B981", scale_factor=1.03), run_time=1.8)
        self.wait(3.5)
        self.play(Indicate(m0, color=WHITE), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(m1, color="#00F0FF"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(m2_out, color="#10B981"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(footer_pill, color="#10B981", scale_factor=1.02), run_time=1.5)
        self.wait(4.0)
