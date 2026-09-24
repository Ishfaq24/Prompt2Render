from manim import *
import numpy as np

class Scene02(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("2. The Core Trinity: Tokens, Patterns, and Lexemes", font_size=24, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.6, height=0.55, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Core Terminology & Definitions", font_size=13, color="#00F0FF").scale_to_fit_width(4.0)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(3.5)

        # [7.7s -> 14.6s] Pillar 1: Lexeme (Left, x = -3.8)
        lex_box = RoundedRectangle(corner_radius=0.15, width=3.4, height=3.4, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        lex_title = Text("1. Lexeme", font_size=15, color="#388BFD")
        lex_subtitle = Text("Concrete Character String", font_size=11, color="#94A3B8").scale_to_fit_width(3.0)
        lex_divider = Line(LEFT*1.3, RIGHT*1.3, stroke_color="#334155", stroke_width=1)
        lex_examples = VGroup(
            Text('"counter"', font="monospace", font_size=13, color="#00F0FF"),
            Text('"42"', font="monospace", font_size=13, color="#10B981"),
            Text('"+"', font="monospace", font_size=13, color="#FFB703"),
            Text('"while"', font="monospace", font_size=13, color="#A855F7")
        ).arrange(DOWN, buff=0.14)
        lex_content = VGroup(lex_title, lex_subtitle, lex_divider, lex_examples).arrange(DOWN, buff=0.16)
        lex_card = VGroup(lex_box, lex_content).move_to(np.array([-3.8, -0.2, 0]))

        self.play(FadeIn(lex_card, shift=RIGHT*0.3), run_time=1.2)
        self.wait(2.0)
        self.play(Indicate(lex_examples[0], color="#00F0FF"), run_time=1.0)
        self.wait(3.0)

        # [14.9s -> 23.7s] Pillar 2: Pattern (Center, x = 0.0)
        pat_box = RoundedRectangle(corner_radius=0.15, width=3.4, height=3.4, stroke_color="#10B981", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        pat_title = Text("2. Pattern", font_size=15, color="#10B981")
        pat_subtitle = Text("Formal Descriptive Rule", font_size=11, color="#94A3B8").scale_to_fit_width(3.0)
        pat_divider = Line(LEFT*1.3, RIGHT*1.3, stroke_color="#334155", stroke_width=1)
        pat_rules = VGroup(
            Text("[a-zA-Z_][a-zA-Z0-9_]*", font="monospace", font_size=10, color="#10B981").scale_to_fit_width(3.0),
            Text("[0-9]+", font="monospace", font_size=11, color="#10B981"),
            Text("\\+", font="monospace", font_size=11, color="#FFB703"),
            Text("while", font="monospace", font_size=11, color="#A855F7")
        ).arrange(DOWN, buff=0.18)
        pat_content = VGroup(pat_title, pat_subtitle, pat_divider, pat_rules).arrange(DOWN, buff=0.16)
        pat_card = VGroup(pat_box, pat_content).move_to(np.array([0.0, -0.2, 0]))

        self.play(FadeIn(pat_card, shift=UP*0.2), run_time=1.2)
        self.wait(2.0)
        self.play(Indicate(pat_rules[0], color="#10B981"), run_time=1.5)
        self.wait(3.5)

        # [24.0s -> 36.3s] Pillar 3: Token (Right, x = 3.8)
        tok_box = RoundedRectangle(corner_radius=0.15, width=3.4, height=3.4, stroke_color="#A855F7", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        tok_title = Text("3. Token", font_size=15, color="#A855F7")
        tok_subtitle = Text("Abstract Symbol & Data", font_size=11, color="#94A3B8").scale_to_fit_width(3.0)
        tok_divider = Line(LEFT*1.3, RIGHT*1.3, stroke_color="#334155", stroke_width=1)
        tok_tuples = VGroup(
            Text("<ID, 'counter'>", font="monospace", font_size=11, color="#00F0FF"),
            Text("<INT, 42>", font="monospace", font_size=11, color="#10B981"),
            Text("<PLUS, ->", font="monospace", font_size=11, color="#FFB703"),
            Text("<KEYWORD, 'while'>", font="monospace", font_size=11, color="#A855F7")
        ).arrange(DOWN, buff=0.16)
        tok_content = VGroup(tok_title, tok_subtitle, tok_divider, tok_tuples).arrange(DOWN, buff=0.16)
        tok_card = VGroup(tok_box, tok_content).move_to(np.array([3.8, -0.2, 0]))

        self.play(FadeIn(tok_card, shift=LEFT*0.3), run_time=1.2)
        self.wait(2.0)

        # Connecting transformation arrows across the three cards
        arrow1 = Arrow(lex_card.get_right(), pat_card.get_left(), color="#388BFD", buff=0.1, stroke_width=2.5)
        arrow2 = Arrow(pat_card.get_right(), tok_card.get_left(), color="#10B981", buff=0.1, stroke_width=2.5)

        self.play(GrowArrow(arrow1), GrowArrow(arrow2), run_time=1.2)
        self.wait(2.0)

        summary_banner = Text("Lexeme matches Pattern -> Yields Structured Token", font_size=12, color="#FFB703").scale_to_fit_width(8.5).move_to(np.array([0.0, -2.2, 0]))
        self.play(FadeIn(summary_banner, shift=UP*0.2), run_time=1.0)
        self.wait(4.8)
