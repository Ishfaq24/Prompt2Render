from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("4. Transition Diagrams: Capturing Lexical Logic", font_size=24, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.8, height=0.55, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("State Machine Model: Float Literal Recognition", font_size=13, color="#10B981").scale_to_fit_width(4.4)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.0)

        # [7.2s -> 15.5s] Build Transition Diagram Graph
        # State 0 (Start)
        s0_c = Circle(radius=0.45, stroke_color="#388BFD", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([-4.2, 0.4, 0]))
        s0_t = Text("0", font_size=15, color=WHITE).move_to(s0_c)
        start_arrow = Arrow(s0_c.get_left() + LEFT*0.7, s0_c.get_left(), color="#00F0FF", stroke_width=2.5, buff=0.08)
        start_lbl = Text("start", font_size=10, color="#00F0FF").next_to(start_arrow, UP, buff=0.08)
        state0 = VGroup(s0_c, s0_t, start_arrow, start_lbl)

        # State 1
        s1_c = Circle(radius=0.45, stroke_color="#388BFD", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([-1.4, 0.4, 0]))
        s1_t = Text("1", font_size=15, color=WHITE).move_to(s1_c)
        s1_loop = CurvedArrow(s1_c.get_top() + LEFT*0.15, s1_c.get_top() + RIGHT*0.15, radius=-0.5, color="#94A3B8", stroke_width=1.8)
        s1_loop_lbl = Text("digit", font="monospace", font_size=10, color="#94A3B8").next_to(s1_loop, UP, buff=0.05)
        state1 = VGroup(s1_c, s1_t, s1_loop, s1_loop_lbl)

        # State 2
        s2_c = Circle(radius=0.45, stroke_color="#388BFD", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([1.4, 0.4, 0]))
        s2_t = Text("2", font_size=15, color=WHITE).move_to(s2_c)
        state2 = VGroup(s2_c, s2_t)

        # State 3 (Accepting Double Circle with Retract Star)
        s3_out = Circle(radius=0.48, stroke_color="#10B981", stroke_width=2, fill_color="#1E293B", fill_opacity=0.95).move_to(np.array([4.2, 0.4, 0]))
        s3_in = Circle(radius=0.40, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.0).move_to(np.array([4.2, 0.4, 0]))
        s3_t = Text("3*", font_size=14, color="#10B981").move_to(s3_out)
        s3_loop = CurvedArrow(s3_out.get_top() + LEFT*0.15, s3_out.get_top() + RIGHT*0.15, radius=-0.5, color="#10B981", stroke_width=1.8)
        s3_loop_lbl = Text("digit", font="monospace", font_size=10, color="#10B981").next_to(s3_loop, UP, buff=0.05)
        state3 = VGroup(s3_out, s3_in, s3_t, s3_loop, s3_loop_lbl)

        # Connecting Edges
        edge_01 = Arrow(s0_c.get_right(), s1_c.get_left(), color="#388BFD", buff=0.08, stroke_width=2)
        lbl_01 = Text("digit", font="monospace", font_size=10, color="#388BFD").next_to(edge_01, UP, buff=0.08)

        edge_12 = Arrow(s1_c.get_right(), s2_c.get_left(), color="#FFB703", buff=0.08, stroke_width=2)
        lbl_12 = Text("'.'", font="monospace", font_size=12, color="#FFB703").next_to(edge_12, UP, buff=0.08)

        edge_23 = Arrow(s2_c.get_right(), s3_out.get_left(), color="#10B981", buff=0.08, stroke_width=2)
        lbl_23 = Text("digit", font="monospace", font_size=10, color="#10B981").next_to(edge_23, UP, buff=0.08)

        graph = VGroup(state0, state1, state2, state3, edge_01, lbl_01, edge_12, lbl_12, edge_23, lbl_23)

        self.play(FadeIn(graph, lag_ratio=0.1), run_time=2.0)
        self.wait(4.5)

        # [18.0s -> 22.6s] Traverse State Machine with active pulse
        scanner_token = Dot(color="#00F0FF", radius=0.12).move_to(s0_c)
        self.play(FadeIn(scanner_token), run_time=0.5)
        self.play(scanner_token.animate.move_to(s1_c), run_time=1.0)
        self.play(scanner_token.animate.move_to(s2_c), run_time=1.0)
        self.play(scanner_token.animate.move_to(s3_out), run_time=1.0)
        self.wait(2.0)

        # [22.9s -> 28.6s] Accepting state double-border emphasis
        accept_card = VGroup(
            RoundedRectangle(corner_radius=0.1, width=7.2, height=0.6, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.95),
            Text("Double Border = Accepting State (Valid Float Token Recognized)", font_size=11, color="#10B981").scale_to_fit_width(6.8)
        ).move_to(np.array([0.0, -1.2, 0]))

        self.play(FadeIn(accept_card, shift=UP*0.2), Indicate(state3, color="#10B981", scale_factor=1.05), run_time=1.5)
        self.wait(4.5)

        # [28.9s -> 39.4s] Asterisk (*) indicates Lookahead Retract
        retract_card = VGroup(
            RoundedRectangle(corner_radius=0.1, width=9.2, height=0.65, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95),
            Text("Asterisk (*) = Retract: Unread 1 lookahead character back into buffer", font_size=11, color="#FDE047").scale_to_fit_width(8.6)
        ).move_to(np.array([0.0, -2.1, 0]))

        self.play(FadeIn(retract_card, shift=UP*0.2), Indicate(s3_t, color="#FFB703", scale_factor=1.3), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(s0_c, color="#388BFD"), Indicate(s1_c, color="#388BFD"), run_time=1.5)
        self.wait(2.5)
        self.play(Indicate(s2_c, color="#FFB703"), Indicate(s3_out, color="#10B981"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(retract_card, color="#FFB703", scale_factor=1.03), run_time=1.5)
        self.wait(1.7)
