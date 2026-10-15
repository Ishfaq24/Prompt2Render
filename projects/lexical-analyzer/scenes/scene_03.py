from manim import *
import numpy as np

class Scene03(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("3. Input Buffering: Dual Buffers and Lookahead Retraction", font_size=23, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.6, height=0.55, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("I/O Architecture: 2N Buffering & Sentinels", font_size=13, color="#FFB703").scale_to_fit_width(4.2)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.0)

        # [7.1s -> 14.4s] Double Buffer Layout (Buffer A & Buffer B)
        buf_container = RoundedRectangle(corner_radius=0.15, width=10.8, height=2.4, stroke_color="#64748B", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9).move_to(np.array([0.0, 0.4, 0]))

        # Buffer A Header and Buffer B Header
        buf_a_label = Text("Buffer A (N bytes)", font_size=12, color="#388BFD").move_to(np.array([-2.7, 1.25, 0]))
        buf_b_label = Text("Buffer B (N bytes)", font_size=12, color="#10B981").move_to(np.array([2.7, 1.25, 0]))
        div_line = DashedLine(np.array([0.0, 1.4, 0]), np.array([0.0, -0.6, 0]), stroke_color="#64748B", stroke_width=1.5)

        # Characters in buffer
        chars_a = ["i", "f", " ", "x", " ", ">", "=", " ", "eof"]
        chars_b = ["1", "0", " ", "{", " ", "y", "+", "+", "eof"]

        boxes_a = VGroup()
        for ch in chars_a:
            bg = Square(side_length=0.45, stroke_color="#334155", stroke_width=1, fill_color="#1E293B", fill_opacity=0.85)
            color = "#EF4444" if ch == "eof" else WHITE
            t = Text(ch, font="monospace", font_size=12, color=color)
            boxes_a.add(VGroup(bg, t))
        boxes_a.arrange(RIGHT, buff=0.06).move_to(np.array([-2.7, 0.4, 0]))

        boxes_b = VGroup()
        for ch in chars_b:
            bg = Square(side_length=0.45, stroke_color="#334155", stroke_width=1, fill_color="#1E293B", fill_opacity=0.85)
            color = "#EF4444" if ch == "eof" else WHITE
            t = Text(ch, font="monospace", font_size=12, color=color)
            boxes_b.add(VGroup(bg, t))
        boxes_b.arrange(RIGHT, buff=0.06).move_to(np.array([2.7, 0.4, 0]))

        buf_group = VGroup(buf_container, buf_a_label, buf_b_label, div_line, boxes_a, boxes_b)
        self.play(FadeIn(buf_group), run_time=1.5)
        self.wait(4.0)

        # [14.7s -> 23.1s] Two Pointers: lexeme_begin and forward
        ptr_begin = VGroup(
            Text("lexeme_begin", font="monospace", font_size=10, color="#10B981").scale_to_fit_width(1.3),
            Arrow(np.array([0, -0.6, 0]), np.array([0, 0, 0]), buff=0.05, stroke_width=2.5, color="#10B981", max_tip_length_to_length_ratio=0.35)
        ).arrange(DOWN, buff=0.06).next_to(boxes_a[5], DOWN, buff=0.15)

        ptr_forward = VGroup(
            Arrow(np.array([0, 0.6, 0]), np.array([0, 0, 0]), buff=0.05, stroke_width=2.5, color="#00F0FF", max_tip_length_to_length_ratio=0.35),
            Text("forward", font="monospace", font_size=10, color="#00F0FF")
        ).arrange(DOWN, buff=0.06).next_to(boxes_a[5], UP, buff=0.15)

        self.play(FadeIn(ptr_begin), FadeIn(ptr_forward), run_time=1.2)
        self.wait(3.0)

        # [23.4s -> 32.3s] Lookahead demonstration: forward moves to inspect "=" after ">"
        self.play(
            ptr_forward.animate.next_to(boxes_a[6], UP, buff=0.15),
            boxes_a[5][0].animate.set_stroke(color="#10B981", width=2),
            boxes_a[6][0].animate.set_stroke(color="#00F0FF", width=2),
            run_time=1.5
        )
        self.wait(2.5)

        # Lookahead explanation card at bottom
        token_found_card = VGroup(
            RoundedRectangle(corner_radius=0.1, width=6.2, height=0.7, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.95),
            Text("Token Matched: <GE, '>='>  (No retract needed)", font="monospace", font_size=11, color="#10B981").scale_to_fit_width(5.6)
        ).move_to(np.array([0.0, -1.8, 0]))

        self.play(FadeIn(token_found_card, shift=UP*0.2), run_time=1.0)
        self.wait(4.5)

        # [32.6s -> 40.6s] EOF Sentinels eliminate per-character bounds checks
        sentinel_box = VGroup(
            RoundedRectangle(corner_radius=0.1, width=8.8, height=0.65, stroke_color="#EF4444", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95),
            Text("Sentinel 'eof' Marker: 1 test per buffer reload instead of 2 tests per char!", font_size=11, color="#FCA5A5").scale_to_fit_width(8.2)
        ).move_to(np.array([0.0, -1.8, 0]))

        self.play(
            Transform(token_found_card, sentinel_box),
            Indicate(boxes_a[8], color="#EF4444", scale_factor=1.2),
            Indicate(boxes_b[8], color="#EF4444", scale_factor=1.2),
            run_time=2.0
        )
        self.wait(3.0)
        self.play(Indicate(ptr_forward, color="#00F0FF", scale_factor=1.2), run_time=1.5)
        self.wait(3.0)
        self.play(Indicate(sentinel_box, color="#EF4444", scale_factor=1.03), run_time=1.5)
        self.wait(5.7)
