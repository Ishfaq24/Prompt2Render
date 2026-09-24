from manim import *
import numpy as np

class Scene06(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("6. The Subset Construction: Determinizing the Machine", font_size=23, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.8, height=0.55, stroke_color="#10B981", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Determinization: Converting NFA into DFA", font_size=13, color="#10B981").scale_to_fit_width(4.4)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.0)

        # [11.5s -> 27.5s] Left Column: Epsilon-Closure & Composite Superstates
        left_box = RoundedRectangle(corner_radius=0.15, width=5.2, height=3.4, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        left_title = Text("NFA State Clustering (ε-closure)", font_size=13, color="#388BFD")
        left_states = VGroup(
            VGroup(
                Text("DFA State A", font="monospace", font_size=12, color="#00F0FF"),
                Text("= ε-closure({0}) -> {0, 1, 2, 4}", font="monospace", font_size=11, color="#E2E8F0")
            ).arrange(RIGHT, buff=0.15),
            VGroup(
                Text("DFA State B", font="monospace", font_size=12, color="#FFB703"),
                Text("= ε-closure(move(A, 'a')) -> {1, 3, 5}", font="monospace", font_size=11, color="#E2E8F0")
            ).arrange(RIGHT, buff=0.15),
            VGroup(
                Text("DFA State C", font="monospace", font_size=12, color="#10B981"),
                Text("= ε-closure(move(A, 'b')) -> {6, 7}*", font="monospace", font_size=11, color="#10B981")
            ).arrange(RIGHT, buff=0.15),
            Text("* Contains NFA accepting state -> DFA accepts!", font_size=10, color="#94A3B8").scale_to_fit_width(4.5)
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        left_content = VGroup(left_title, left_states).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        left_card = VGroup(left_box, left_content).move_to(np.array([-3.4, -0.1, 0]))

        self.play(FadeIn(left_card, shift=RIGHT*0.3), run_time=1.5)
        self.wait(4.5)

        # [27.8s -> 39.9s] Right Column: Deterministic 2D Transition Table (Dtran)
        right_box = RoundedRectangle(corner_radius=0.15, width=5.2, height=3.4, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        right_title = Text("DFA Transition Matrix Dtran[State, Char]", font_size=12, color="#10B981")

        # Table rows
        header_row = VGroup(
            Text("State", font="monospace", font_size=11, color="#94A3B8"),
            Text("Input 'a'", font="monospace", font_size=11, color="#00F0FF"),
            Text("Input 'b'", font="monospace", font_size=11, color="#FFB703"),
            Text("Token Emit", font="monospace", font_size=11, color="#10B981")
        ).arrange(RIGHT, buff=0.35)

        divider_row = Line(LEFT*2.2, RIGHT*2.2, color="#334155", stroke_width=1)

        row_a = VGroup(
            Text("A (start)", font="monospace", font_size=11, color=WHITE),
            Text("State B", font="monospace", font_size=11, color="#00F0FF"),
            Text("State C", font="monospace", font_size=11, color="#FFB703"),
            Text("none", font="monospace", font_size=11, color="#64748B")
        ).arrange(RIGHT, buff=0.42)

        row_b = VGroup(
            Text("State B ", font="monospace", font_size=11, color=WHITE),
            Text("State B", font="monospace", font_size=11, color="#00F0FF"),
            Text("State C", font="monospace", font_size=11, color="#FFB703"),
            Text("none", font="monospace", font_size=11, color="#64748B")
        ).arrange(RIGHT, buff=0.42)

        row_c = VGroup(
            Text("State C*", font="monospace", font_size=11, color="#10B981"),
            Text("error  ", font="monospace", font_size=11, color="#EF4444"),
            Text("error  ", font="monospace", font_size=11, color="#EF4444"),
            Text("<ID>  ", font="monospace", font_size=11, color="#10B981")
        ).arrange(RIGHT, buff=0.42)

        table_mobs = VGroup(header_row, divider_row, row_a, row_b, row_c).arrange(DOWN, buff=0.16)
        right_content = VGroup(right_title, table_mobs).arrange(DOWN, buff=0.2)
        right_card = VGroup(right_box, right_content).move_to(np.array([3.4, -0.1, 0]))

        self.play(FadeIn(right_card, shift=LEFT*0.3), run_time=1.5)
        self.wait(4.5)

        # Bottom Callout: Constant-time O(1) table lookup
        callout = VGroup(
            RoundedRectangle(corner_radius=0.1, width=8.8, height=0.6, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95),
            Text("Execution Speed: Exactly 1 memory lookup O(1) per source character!", font_size=11, color="#38BDF8").scale_to_fit_width(8.2)
        ).move_to(np.array([0.0, -2.2, 0]))

        self.play(FadeIn(callout, shift=UP*0.2), Indicate(right_card, color="#10B981", scale_factor=1.02), run_time=1.8)
        self.wait(3.5)
        self.play(Indicate(row_a[1], color="#00F0FF"), Indicate(row_a[2], color="#FFB703"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(row_c, color="#10B981"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(left_states[2], color="#10B981"), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(callout, color="#00F0FF", scale_factor=1.02), run_time=1.5)
        self.wait(3.4)
