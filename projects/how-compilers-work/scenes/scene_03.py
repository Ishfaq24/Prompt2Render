from manim import *
import numpy as np

class Scene03(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("3. Syntax Analysis: Constructing the Abstract Syntax Tree", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 3.1s] A stream of tokens has vocabulary, but no grammar
        flat_tokens = VGroup(
            Text("[ID: total]", font_size=14, color="#388BFD"),
            Text("[=]", font_size=14, color="#F59E0B"),
            Text("[ID: count]", font_size=14, color="#388BFD"),
            Text("[*]", font_size=14, color="#F59E0B"),
            Text("[INT: 2]", font_size=14, color="#10B981"),
            Text("[+]", font_size=14, color="#F59E0B"),
            Text("[INT: 5]", font_size=14, color="#10B981")
        ).arrange(RIGHT, buff=0.2).shift(UP * 2.2)
        flat_box = SurroundingRectangle(flat_tokens, color="#334155", buff=0.15, stroke_width=1.5)
        flat_group = VGroup(flat_box, flat_tokens)

        self.play(FadeIn(flat_group, shift=DOWN*0.2), run_time=1.0)
        self.wait(1.1)

        # [3.4s -> 6.4s] That is where syntax analysis, or parsing, takes over
        parser_tag = VGroup(
            RoundedRectangle(corner_radius=0.15, width=3.5, height=0.65, color="#A855F7", fill_opacity=0.2),
            Text("Phase 2: Context-Free Grammar Parser", font_size=15, color="#A855F7")
        ).shift(UP * 1.2)
        self.play(FadeIn(parser_tag), run_time=1.0)
        self.wait(2.0)

        # [6.7s -> 12.9s] Grammar rules and transforming tokens
        self.play(FadeOut(parser_tag), flat_group.animate.to_edge(UP, buff=1.0).scale(0.85), run_time=1.2)
        grammar_rule = Text("Assignment  ->  IDENTIFIER '=' Expression\nExpression  ->  Term '+' Term\nTerm        ->  Factor '*' Factor",
                            font="monospace", font_size=13, color="#94A3B8").to_edge(LEFT, buff=0.8).shift(DOWN * 0.2)
        self.play(Write(grammar_rule), run_time=2.0)
        self.wait(3.0)

        # [13.2s -> 16.8s] Constructing the Abstract Syntax Tree (AST)
        self.play(FadeOut(grammar_rule), run_time=0.8)

        def make_node(label, color, pos):
            c = Circle(radius=0.40, stroke_color=color, stroke_width=2, fill_color="#1E293B", fill_opacity=0.95)
            t = Text(label, font_size=15, color=WHITE).move_to(c)
            g = VGroup(c, t).move_to(pos)
            return g

        # Node coordinates - safely elevated to avoid bottom caption overlap
        pos_assign = np.array([0.5, 1.4, 0])
        pos_total  = np.array([-2.2, 0.2, 0])
        pos_add    = np.array([2.5, 0.2, 0])
        pos_mul    = np.array([1.2, -0.9, 0])
        pos_five   = np.array([3.8, -0.9, 0])
        pos_count  = np.array([0.2, -2.0, 0])
        pos_two    = np.array([2.2, -2.0, 0])

        node_assign = make_node("=", "#F59E0B", pos_assign)
        node_total  = make_node("total", "#388BFD", pos_total)
        node_add    = make_node("+", "#F59E0B", pos_add)
        node_mul    = make_node("*", "#F59E0B", pos_mul)
        node_five   = make_node("5", "#10B981", pos_five)
        node_count  = make_node("count", "#388BFD", pos_count)
        node_two    = make_node("2", "#10B981", pos_two)

        edge1 = Line(pos_assign, pos_total, color="#64748B", stroke_width=2)
        edge2 = Line(pos_assign, pos_add, color="#64748B", stroke_width=2)
        edge3 = Line(pos_add, pos_mul, color="#64748B", stroke_width=2)
        edge4 = Line(pos_add, pos_five, color="#64748B", stroke_width=2)
        edge5 = Line(pos_mul, pos_count, color="#64748B", stroke_width=2)
        edge6 = Line(pos_mul, pos_two, color="#64748B", stroke_width=2)

        # [17.1s -> 21.4s] Reveal hierarchical structure
        self.play(
            Create(edge1), Create(edge2),
            FadeIn(node_assign), FadeIn(node_total), FadeIn(node_add),
            run_time=2.0
        )
        self.wait(2.2)

        # [21.7s -> 28.4s] Multiplication deeper than addition (precedence)
        self.play(
            Create(edge3), Create(edge4), Create(edge5), Create(edge6),
            FadeIn(node_mul), FadeIn(node_five), FadeIn(node_count), FadeIn(node_two),
            run_time=2.5
        )

        prec_box = SurroundingRectangle(VGroup(node_mul, node_count, node_two), color="#00F0FF", buff=0.18, stroke_width=2)
        prec_label = Text("Higher Precedence\n(* before +)", font_size=13, color="#00F0FF", line_spacing=0.85).next_to(prec_box, LEFT, buff=0.35)

        self.play(Create(prec_box), Write(prec_label), run_time=1.5)
        self.wait(2.7)

        # [28.8s -> 33.3s] Final unambiguous relationship and order
        self.play(
            Indicate(node_assign, color="#F59E0B", scale_factor=1.12),
            Indicate(prec_box, color="#00F0FF", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(2.5)