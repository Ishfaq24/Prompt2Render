from manim import *
import numpy as np

class Scene05(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("5. Thompson's Construction: From Regex to Nondeterministic Automata", font_size=22, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.8, height=0.55, stroke_color="#A855F7", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Automata Theory: Inductive NFA Rules", font_size=13, color="#A855F7").scale_to_fit_width(4.4)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.5)

        # [8.8s -> 25.3s] Explain NFA concept: Spontaneous epsilon (ε) transitions
        # Build 3 inductive cards side by side
        # Card 1: Concatenation (Left, x = -3.8)
        c1_box = RoundedRectangle(corner_radius=0.12, width=3.4, height=3.0, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        c1_title = Text("1. Concatenation: r1 . r2", font_size=13, color="#388BFD")
        c1_s0 = Circle(radius=0.25, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-4.8, 0.4, 0]))
        c1_s1 = Circle(radius=0.25, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-3.8, 0.4, 0]))
        c1_s2 = Circle(radius=0.25, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-2.8, 0.4, 0]))
        c1_e1 = Arrow(c1_s0.get_right(), c1_s1.get_left(), color="#388BFD", buff=0.05, stroke_width=1.8)
        c1_e2 = Arrow(c1_s1.get_right(), c1_s2.get_left(), color="#388BFD", buff=0.05, stroke_width=1.8)
        c1_l1 = Text("r1", font_size=11, color="#00F0FF").next_to(c1_e1, UP, buff=0.05)
        c1_l2 = Text("r2", font_size=11, color="#00F0FF").next_to(c1_e2, UP, buff=0.05)
        c1_note = Text("Chained in series", font_size=10, color="#94A3B8")
        c1_content = VGroup(c1_title, VGroup(c1_s0, c1_s1, c1_s2, c1_e1, c1_e2, c1_l1, c1_l2), c1_note).arrange(DOWN, buff=0.25)
        card1 = VGroup(c1_box, c1_content).move_to(np.array([-3.8, 0.1, 0]))

        # Card 2: Alternation (Center, x = 0.0)
        c2_box = RoundedRectangle(corner_radius=0.12, width=3.4, height=3.0, stroke_color="#FFB703", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        c2_title = Text("2. Alternation: r1 | r2", font_size=13, color="#FFB703")
        c2_in = Circle(radius=0.22, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([-1.2, 0.1, 0]))
        c2_top = Circle(radius=0.22, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([0.0, 0.6, 0]))
        c2_bot = Circle(radius=0.22, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([0.0, -0.4, 0]))
        c2_out = Circle(radius=0.22, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([1.2, 0.1, 0]))
        e_top_in = Arrow(c2_in.get_center(), c2_top.get_center(), color="#FFB703", buff=0.25, stroke_width=1.5)
        e_bot_in = Arrow(c2_in.get_center(), c2_bot.get_center(), color="#FFB703", buff=0.25, stroke_width=1.5)
        e_top_out = Arrow(c2_top.get_center(), c2_out.get_center(), color="#FFB703", buff=0.25, stroke_width=1.5)
        e_bot_out = Arrow(c2_bot.get_center(), c2_out.get_center(), color="#FFB703", buff=0.25, stroke_width=1.5)
        lbl_eps1 = Text("ε", font_size=11, color="#FFB703").move_to(np.array([-0.7, 0.5, 0]))
        lbl_eps2 = Text("ε", font_size=11, color="#FFB703").move_to(np.array([-0.7, -0.3, 0]))
        c2_note = Text("Parallel branches with ε", font_size=10, color="#94A3B8")
        c2_graph = VGroup(c2_in, c2_top, c2_bot, c2_out, e_top_in, e_bot_in, e_top_out, e_bot_out, lbl_eps1, lbl_eps2)
        c2_content = VGroup(c2_title, c2_graph, c2_note).arrange(DOWN, buff=0.2)
        card2 = VGroup(c2_box, c2_content).move_to(np.array([0.0, 0.1, 0]))

        # Card 3: Kleene Star (Right, x = 3.8)
        c3_box = RoundedRectangle(corner_radius=0.12, width=3.4, height=3.0, stroke_color="#A855F7", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        c3_title = Text("3. Kleene Star: r*", font_size=13, color="#A855F7")
        c3_s0 = Circle(radius=0.22, stroke_color=WHITE, stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([2.6, 0.1, 0]))
        c3_s1 = Circle(radius=0.22, stroke_color="#A855F7", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([3.8, 0.1, 0]))
        c3_s2 = Circle(radius=0.22, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.9).move_to(np.array([5.0, 0.1, 0]))
        c3_fwd = CurvedArrow(np.array([2.6, 0.35, 0]), np.array([5.0, 0.35, 0]), radius=-1.5, color="#A855F7", stroke_width=1.5)
        c3_bwd = CurvedArrow(np.array([5.0, -0.15, 0]), np.array([2.6, -0.15, 0]), radius=-1.5, color="#A855F7", stroke_width=1.5)
        c3_lbl_fwd = Text("ε (bypass)", font_size=9, color="#A855F7").next_to(c3_fwd, UP, buff=0.03)
        c3_lbl_bwd = Text("ε (loop)", font_size=9, color="#A855F7").next_to(c3_bwd, DOWN, buff=0.03)
        c3_mid = Arrow(c3_s0.get_right(), c3_s1.get_left(), color=WHITE, buff=0.05, stroke_width=1.5)
        c3_note = Text("Zero or more iterations", font_size=10, color="#94A3B8")
        c3_graph = VGroup(c3_s0, c3_s1, c3_s2, c3_fwd, c3_bwd, c3_lbl_fwd, c3_lbl_bwd, c3_mid)
        c3_content = VGroup(c3_title, c3_graph, c3_note).arrange(DOWN, buff=0.18)
        card3 = VGroup(c3_box, c3_content).move_to(np.array([3.8, 0.1, 0]))

        self.play(FadeIn(card1, shift=RIGHT*0.2), FadeIn(card2, shift=UP*0.2), FadeIn(card3, shift=LEFT*0.2), run_time=2.0)
        self.wait(5.0)

        # [25.6s -> 44.0s] Highlighting inductive power of Thompson's construction
        bottom_bar = VGroup(
            RoundedRectangle(corner_radius=0.1, width=10.6, height=0.65, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.95),
            Text("Inductive Guarantee: Every Regular Expression converts to an equivalent NFA in O(n) time", font_size=11, color="#38BDF8").scale_to_fit_width(10.0)
        ).move_to(np.array([0.0, -2.0, 0]))

        self.play(FadeIn(bottom_bar, shift=UP*0.2), run_time=1.2)
        self.wait(4.0)

        self.play(Indicate(card1, color="#00F0FF"), run_time=1.5)
        self.play(Indicate(card2, color="#FFB703"), run_time=1.5)
        self.play(Indicate(card3, color="#A855F7"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(c1_s1, color="#388BFD"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(c2_top, color="#FFB703"), Indicate(c2_bot, color="#FFB703"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(c3_fwd, color="#A855F7"), Indicate(c3_bwd, color="#A855F7"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(bottom_bar, color="#00F0FF", scale_factor=1.02), run_time=1.5)
        self.wait(3.6)
