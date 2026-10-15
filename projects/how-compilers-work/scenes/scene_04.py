from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("4. Semantic Analysis: Type Checking and Symbol Scopes", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 7.9s] Grammatically flawless vs nonsensical expression
        bad_expr = Text('string_var = "hello" * &calculate;', font="monospace", font_size=16, color="#EF4444").shift(UP * 2.0)
        bad_card = SurroundingRectangle(bad_expr, color="#EF4444", buff=0.15, stroke_width=1.5)
        bad_tag = Text("Valid Grammar, but Semantically Meaningless!", font_size=14, color="#EF4444").next_to(bad_card, UP, buff=0.15)
        bad_group = VGroup(bad_card, bad_expr, bad_tag)

        self.play(FadeIn(bad_group, shift=DOWN*0.2), run_time=1.5)
        self.wait(2.5)
        self.play(FadeOut(bad_group), run_time=1.0)
        self.wait(2.9)

        # [8.2s -> 11.9s] Semantic analysis enforces language rules
        phase_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.0, height=0.65, color="#10B981", fill_opacity=0.2),
            Text("Phase 3: Semantic Analysis & Typing", font_size=15, color="#10B981")
        ).shift(UP * 2.2)
        self.play(FadeIn(phase_badge), run_time=1.0)
        self.wait(2.7)

        # [12.2s -> 18.4s] Symbol table lookup
        self.play(phase_badge.animate.scale(0.85).to_edge(UP, buff=1.0).to_edge(LEFT, buff=0.8), run_time=1.0)

        # Symbol Table Card on Left
        sym_header = Text("Symbol Table (Scope: Local)", font_size=14, color="#00F0FF")
        sym_rows = VGroup(
            Text("Name   | Type   | Scope | Address", font="monospace", font_size=12, color="#94A3B8"),
            Text("count  | int32  | local | [rbp-4]", font="monospace", font_size=12, color="#10B981"),
            Text("total  | int32  | local | [rbp-8]", font="monospace", font_size=12, color="#10B981")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14)
        sym_content = VGroup(sym_header, sym_rows).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
        sym_box = SurroundingRectangle(sym_content, color="#388BFD", buff=0.2, stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.85)
        sym_card = VGroup(sym_box, sym_content).move_to(np.array([-3.8, 0.0, 0]))

        self.play(FadeIn(sym_card, shift=RIGHT*0.3), run_time=1.5)
        self.wait(3.7)

        # [18.7s -> 23.0s] Type checking verification on Right
        ast_type_tree = VGroup(
            Text("Type Inference Cascade:", font_size=15, color="#F59E0B"),
            Text("1. Lookup 'count'   -> int32  [OK]", font="monospace", font_size=13, color="#10B981"),
            Text("2. Literal '2'      -> int32  [OK]", font="monospace", font_size=13, color="#10B981"),
            Text("3. 'count' * 2      -> int32  [OK]", font="monospace", font_size=13, color="#10B981"),
            Text("4. (expr) + 5       -> int32  [OK]", font="monospace", font_size=13, color="#10B981"),
            Text("5. Assign to 'total'-> int32 = int32", font="monospace", font_size=13, color="#00F0FF")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        type_box = SurroundingRectangle(ast_type_tree, color="#10B981", buff=0.22, stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.85)
        type_panel = VGroup(type_box, ast_type_tree).move_to(np.array([3.4, 0.2, 0]))

        self.play(FadeIn(type_panel, shift=LEFT*0.3), run_time=1.5)
        self.wait(2.8)

        # [23.3s -> 27.9s] Implicit type conversions mention
        status_pos = np.array([3.4, -1.9, 0])
        conv_badge = VGroup(
            RoundedRectangle(corner_radius=0.1, width=4.5, height=0.6, color="#A855F7", fill_opacity=0.2),
            Text("Implicit Cast: int -> float (if needed)", font_size=13, color="#A855F7")
        ).move_to(status_pos)
        self.play(FadeIn(conv_badge), run_time=1.2)
        self.wait(3.4)

        # [28.3s -> 34.4s] Compile-time type safety check complete - smoothly replace conv_badge
        pass_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.5, height=0.65, color="#10B981", fill_opacity=0.3),
            Text("AST Type-Checked & Decorated!", font_size=15, color="#10B981")
        ).move_to(status_pos)

        self.play(
            Transform(conv_badge, pass_badge),
            Indicate(type_panel, color="#10B981", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(4.1)