from manim import *
import numpy as np

class Scene02(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("2. Lexical Analysis: Scanning Text into Atomic Tokens", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 3.7s] The compilation journey starts with the lexer
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.0, height=0.7, color="#FFB703", fill_opacity=0.15),
            Text("Phase 1: Lexical Scanner", font_size=17, color="#FFB703")
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=1.0)
        self.wait(1.7)

        # [4.0s -> 8.5s] Raw unbroken stream of individual characters
        char_label = Text("Raw Character Stream:", font_size=16, color="#94A3B8").move_to(np.array([-4.5, 1.4, 0]), aligned_edge=LEFT)
        raw_code = "total = count * 2 + 5;  // compute"
        char_boxes = VGroup()
        for ch in raw_code:
            bg = Square(side_length=0.32, stroke_color="#334155", stroke_width=1, fill_color="#1E293B", fill_opacity=0.8)
            t = Text(ch, font="monospace", font_size=16, color=WHITE).move_to(bg)
            char_boxes.add(VGroup(bg, t))
        char_boxes.arrange(RIGHT, buff=0.04).move_to(np.array([0.0, 0.8, 0]))

        self.play(Write(char_label), FadeIn(char_boxes, lag_ratio=0.03), run_time=2.0)
        self.wait(2.4)

        # [8.8s -> 18.2s] Scanner cursor / regex grouping characters into tokens
        # Placed clearly BELOW char_boxes so it never overlaps char_label
        scanner_box = RoundedRectangle(corner_radius=0.08, width=1.8, height=0.55, color="#00F0FF", stroke_width=2.5)
        scanner_box.move_to(char_boxes[0:5].get_center())
        scan_label = Text("Scanner Window (FSM / Regex)", font_size=14, color="#00F0FF").next_to(scanner_box, DOWN, buff=0.25)

        self.play(Create(scanner_box), FadeIn(scan_label), run_time=1.2)
        self.wait(1.0)

        # Animate scan across characters
        self.play(
            scanner_box.animate.move_to(char_boxes[8:13].get_center()),
            scan_label.animate.next_to(char_boxes[8:13], DOWN, buff=0.25),
            run_time=2.0
        )
        self.wait(1.5)
        self.play(
            scanner_box.animate.move_to(char_boxes[16:21].get_center()),
            scan_label.animate.next_to(char_boxes[16:21], DOWN, buff=0.25),
            run_time=2.0
        )
        self.wait(2.7)

        # [18.6s -> 26.7s] Produce distinct color-coded token badges
        self.play(FadeOut(scanner_box), FadeOut(scan_label), run_time=0.8)

        tokens_title = Text("Structured Token Stream:", font_size=16, color="#10B981").move_to(np.array([-4.5, -0.4, 0]), aligned_edge=LEFT)
        self.play(Write(tokens_title), run_time=0.8)

        token_defs = [
            ("ID", "total", "#388BFD"),
            ("ASSIGN", "=", "#F59E0B"),
            ("ID", "count", "#388BFD"),
            ("OP", "*", "#F59E0B"),
            ("INT", "2", "#10B981"),
            ("OP", "+", "#F59E0B"),
            ("INT", "5", "#10B981"),
            ("SEMI", ";", "#A855F7"),
        ]

        tokens_group = VGroup()
        for tag, val, col in token_defs:
            b = RoundedRectangle(corner_radius=0.12, width=1.3, height=0.85, stroke_color=col, stroke_width=1.5, fill_color=col, fill_opacity=0.15)
            t_tag = Text(tag, font_size=11, color=col).shift(UP * 0.18)
            t_val = Text(val, font_size=15, color=WHITE).shift(DOWN * 0.15)
            tokens_group.add(VGroup(b, t_tag, t_val))
        tokens_group.arrange(RIGHT, buff=0.15).move_to(np.array([0.0, -1.3, 0]))

        self.play(FadeIn(tokens_group, lag_ratio=0.15), run_time=3.0)
        self.wait(3.5)

        # [27.0s -> 34.9s] Comments and whitespace stripped away
        comment_part = char_boxes[21:]
        strike = Line(comment_part.get_left(), comment_part.get_right(), color="#EF4444", stroke_width=3)
        discard_label = Text("Whitespace & Comments Stripped", font_size=14, color="#EF4444").next_to(comment_part, UP, buff=0.25)

        self.play(
            Create(strike),
            FadeIn(discard_label),
            comment_part.animate.set_opacity(0.25),
            run_time=1.5
        )
        self.wait(1.5)
        self.play(
            Indicate(tokens_group, color="#10B981", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(2.9)