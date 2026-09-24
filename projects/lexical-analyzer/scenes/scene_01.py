from manim import *
import numpy as np

class Scene01(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("1. The Gateway to the Compiler: Bridging Characters to Tokens", font_size=24, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # Stage Badge
        stage_badge = VGroup(
            RoundedRectangle(corner_radius=0.12, width=4.4, height=0.55, stroke_color="#FFB703", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.8),
            Text("Compiler Front End: Phase 1", font_size=13, color="#FFB703").scale_to_fit_width(3.8)
        ).shift(UP * 2.3)
        self.play(FadeIn(stage_badge, shift=DOWN*0.2), run_time=0.8)
        self.wait(1.5)

        # [0.0s -> 8.5s] Source file on the left: raw characters with whitespace and comments
        src_box = RoundedRectangle(corner_radius=0.15, width=4.4, height=3.2, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        src_title = Text("main.c (Raw Text Stream)", font="monospace", font_size=13, color="#388BFD")
        src_lines = VGroup(
            Text("int  sum  =  100 ;", font="monospace", font_size=13, color="#E2E8F0"),
            Text("   // compute running total", font="monospace", font_size=11, color="#64748B"),
            Text("sum = sum + delta ;", font="monospace", font_size=13, color="#E2E8F0"),
            Text("\\n\\t   /* trailing spaces */", font="monospace", font_size=11, color="#64748B")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
        src_content = VGroup(src_title, src_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        src_card = VGroup(src_box, src_content).move_to(np.array([-4.2, -0.2, 0]))

        self.play(FadeIn(src_card, shift=RIGHT*0.3), run_time=1.2)
        self.wait(4.0)

        # [8.5s -> 19.9s] Problem: Parsing raw characters directly creates explosive complexity
        complexity_warning = VGroup(
            RoundedRectangle(corner_radius=0.1, width=3.8, height=0.6, stroke_color="#EF4444", stroke_width=1.5, fill_color="#1E293B", fill_opacity=0.95),
            Text("Raw Chars -> Grammar Explosion!", font_size=11, color="#EF4444").scale_to_fit_width(3.4)
        ).move_to(np.array([-4.2, -2.1, 0]))

        self.play(FadeIn(complexity_warning, shift=UP*0.2), run_time=1.0)
        self.wait(3.5)
        self.play(Indicate(src_lines[1], color="#EF4444"), Indicate(src_lines[3], color="#EF4444"), run_time=1.5)
        self.wait(5.0)

        # [20.0s -> 25.8s] Center Gateway: Lexical Analyzer (Scanner)
        lexer_box = RoundedRectangle(corner_radius=0.15, width=2.8, height=3.2, stroke_color="#10B981", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.95)
        lexer_title = Text("Lexical Analyzer", font_size=14, color="#10B981")
        lexer_sub = Text("(Scanner)", font_size=12, color="#94A3B8")
        strip_pill = VGroup(
            RoundedRectangle(corner_radius=0.08, width=2.4, height=0.45, stroke_color="#64748B", stroke_width=1, fill_color="#1E293B", fill_opacity=0.8),
            Text("Strip Trivia & Whitespace", font_size=10, color="#94A3B8").scale_to_fit_width(2.2)
        )
        diag_pill = VGroup(
            RoundedRectangle(corner_radius=0.08, width=2.4, height=0.45, stroke_color="#00F0FF", stroke_width=1, fill_color="#1E293B", fill_opacity=0.8),
            Text("Track File Coordinates", font_size=10, color="#00F0FF").scale_to_fit_width(2.2)
        )
        lexer_content = VGroup(lexer_title, lexer_sub, strip_pill, diag_pill).arrange(DOWN, buff=0.18)
        lexer_gateway = VGroup(lexer_box, lexer_content).move_to(np.array([0.0, -0.2, 0]))

        arrow_in = Arrow(src_card.get_right(), lexer_gateway.get_left(), color="#388BFD", buff=0.12, stroke_width=2.5)

        self.play(FadeOut(complexity_warning), run_time=0.5)
        self.play(FadeIn(lexer_gateway, shift=DOWN*0.3), GrowArrow(arrow_in), run_time=1.5)
        self.wait(3.5)

        # [26.1s -> 37.5s] Output structured tokens on the right
        tok_box = RoundedRectangle(corner_radius=0.15, width=4.4, height=3.2, stroke_color="#A855F7", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        tok_title = Text("Structured Token Stream", font_size=13, color="#A855F7")
        tok_badges = VGroup(
            Text("<KEYWORD, 'int'>", font="monospace", font_size=12, color="#00F0FF"),
            Text("<IDENTIFIER, 'sum'>", font="monospace", font_size=12, color="#10B981"),
            Text("<ASSIGN, '='>", font="monospace", font_size=12, color="#FFB703"),
            Text("<INT_CONST, '100'>", font="monospace", font_size=12, color="#A855F7"),
            Text("<SEMICOLON, ';'>", font="monospace", font_size=12, color="#94A3B8")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        tok_content = VGroup(tok_title, tok_badges).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        tok_card = VGroup(tok_box, tok_content).move_to(np.array([4.2, -0.2, 0]))

        arrow_out = Arrow(lexer_gateway.get_right(), tok_card.get_left(), color="#10B981", buff=0.12, stroke_width=2.5)

        self.play(FadeIn(tok_card, shift=LEFT*0.3), GrowArrow(arrow_out), run_time=1.5)
        self.wait(2.5)

        # Animate parser destination indicator
        parser_pill = VGroup(
            RoundedRectangle(corner_radius=0.1, width=3.8, height=0.55, stroke_color="#A855F7", stroke_width=1.2, fill_color="#1E293B", fill_opacity=0.9),
            Text("Ready for Phase 2: Syntax Parser ->", font_size=11, color="#A855F7").scale_to_fit_width(3.4)
        ).move_to(np.array([4.2, -2.1, 0]))

        self.play(FadeIn(parser_pill, shift=UP*0.2), run_time=1.0)
        self.wait(2.0)
        self.play(Indicate(tok_card, color="#00F0FF", scale_factor=1.02), run_time=1.5)
        self.wait(3.2)
