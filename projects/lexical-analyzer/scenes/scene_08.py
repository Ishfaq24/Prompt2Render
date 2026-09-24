from manim import *
import numpy as np

class Scene08(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("8. Ambiguity Resolution: Maximal Munch and Priority Rules", font_size=23, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=5.2, height=0.55, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Disambiguation: Deterministic Lexer Conflict Resolution", font_size=13, color="#00F0FF").scale_to_fit_width(4.8)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.5)

        # [10.0s -> 25.2s] Panel 1: Maximal Munch / Longest Match (Left, x = -3.5)
        munch_box = RoundedRectangle(corner_radius=0.15, width=5.2, height=3.3, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        munch_title = Text("Rule 1: Maximal Munch (Longest Match)", font_size=12, color="#388BFD").scale_to_fit_width(4.5)

        input_text = "while_counter"
        boxes_munch = VGroup()
        for ch in input_text:
            bg = Square(side_length=0.32, stroke_color="#334155", stroke_width=1, fill_color="#1E293B", fill_opacity=0.85)
            t = Text(ch, font="monospace", font_size=12, color=WHITE)
            boxes_munch.add(VGroup(bg, t))
        boxes_munch.arrange(RIGHT, buff=0.03)

        dilemma = Text("Dilemma: Stop at 'while'? OR consume all?", font_size=10, color="#FFB703").scale_to_fit_width(4.5)
        resolution1 = VGroup(
            RoundedRectangle(corner_radius=0.08, width=4.6, height=0.55, stroke_color="#10B981", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.95),
            Text("Result: <ID, 'while_counter'> (Greedy Match)", font="monospace", font_size=10, color="#10B981").scale_to_fit_width(4.3)
        )

        munch_content = VGroup(munch_title, boxes_munch, dilemma, resolution1).arrange(DOWN, buff=0.2)
        munch_panel = VGroup(munch_box, munch_content).move_to(np.array([-3.5, 0.0, 0]))

        self.play(FadeIn(munch_panel, shift=RIGHT*0.3), run_time=1.5)
        self.wait(3.5)
        self.play(Indicate(boxes_munch, color="#00F0FF", scale_factor=1.05), run_time=1.5)
        self.wait(4.0)

        # [25.5s -> 40.6s] Panel 2: Rule Priority (Right, x = 3.5)
        prio_box = RoundedRectangle(corner_radius=0.15, width=5.2, height=3.3, stroke_color="#A855F7", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        prio_title = Text("Rule 2: Priority by Declaration Order", font_size=12, color="#A855F7").scale_to_fit_width(4.5)

        input_exact = Text("Exact Source String: 'while'", font="monospace", font_size=11, color=WHITE).scale_to_fit_width(4.2)
        rule_list = VGroup(
            VGroup(
                Text("1. Keyword Rule: 'while' -> <KEYWORD>", font="monospace", font_size=10, color="#10B981").scale_to_fit_width(3.6),
                Text("[WINS]", font="monospace", font_size=10, color="#10B981")
            ).arrange(RIGHT, buff=0.1),
            VGroup(
                Text("2. Ident Pattern: [a-zA-Z_]\\w* -> <ID>", font="monospace", font_size=10, color="#64748B").scale_to_fit_width(3.6),
                Text("[LOSES]", font="monospace", font_size=10, color="#64748B")
            ).arrange(RIGHT, buff=0.1)
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)

        resolution2 = VGroup(
            RoundedRectangle(corner_radius=0.08, width=4.6, height=0.55, stroke_color="#A855F7", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.95),
            Text("Keywords declared first take precedence!", font_size=10, color="#E9D5FF").scale_to_fit_width(4.2)
        )

        prio_content = VGroup(prio_title, input_exact, rule_list, resolution2).arrange(DOWN, buff=0.18)
        prio_panel = VGroup(prio_box, prio_content).move_to(np.array([3.5, 0.0, 0]))

        self.play(FadeIn(prio_panel, shift=LEFT*0.3), run_time=1.5)
        self.wait(3.5)
        self.play(Indicate(rule_list[0], color="#10B981", scale_factor=1.05), run_time=1.5)
        self.wait(4.5)

        # [40.9s -> 54.6s] Grand Finale: The Complete Pipeline Flow to Parser
        footer_card = VGroup(
            RoundedRectangle(corner_radius=0.12, width=11.2, height=0.75, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.95),
            Text("From Raw Characters -> Deterministic Automata -> Pure Tokens Ready for Syntax Parsing!", font_size=12, color="#38BDF8").scale_to_fit_width(10.5)
        ).move_to(np.array([0.0, -2.2, 0]))

        self.play(FadeIn(footer_card, shift=UP*0.3), run_time=1.5)
        self.wait(3.5)
        self.play(
            Indicate(munch_panel, color="#00F0FF", scale_factor=1.02),
            Indicate(prio_panel, color="#A855F7", scale_factor=1.02),
            Indicate(footer_card, color="#10B981", scale_factor=1.02),
            run_time=2.0
        )
        self.wait(3.0)
        self.play(Indicate(resolution1, color="#10B981", scale_factor=1.03), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(resolution2, color="#A855F7", scale_factor=1.03), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(footer_card, color="#00F0FF", scale_factor=1.02), run_time=1.5)
        self.wait(7.3)
