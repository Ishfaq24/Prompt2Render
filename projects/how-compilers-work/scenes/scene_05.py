from manim import *
import numpy as np

class Scene05(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("5. Intermediate Representation: Solving the M x N Problem", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 11.4s] The M x N Matrix explosion
        def lang_box(txt, col):
            return VGroup(
                RoundedRectangle(corner_radius=0.1, width=1.6, height=0.6, stroke_color=col, stroke_width=1.5, fill_color=col, fill_opacity=0.15),
                Text(txt, font_size=14, color=WHITE)
            )

        sources = VGroup(
            lang_box("C / C++", "#388BFD"),
            lang_box("Rust", "#F97316"),
            lang_box("Python", "#EAB308")
        ).arrange(DOWN, buff=0.45).to_edge(LEFT, buff=1.2).shift(DOWN * 0.2)

        targets = VGroup(
            lang_box("x86_64", "#10B981"),
            lang_box("ARM64", "#06B6D4"),
            lang_box("RISC-V", "#A855F7")
        ).arrange(DOWN, buff=0.45).to_edge(RIGHT, buff=1.2).shift(DOWN * 0.2)

        cross_lines = VGroup()
        for s in sources:
            for t in targets:
                cross_lines.add(Line(s.get_right(), t.get_left(), stroke_color="#EF4444", stroke_width=1.2, stroke_opacity=0.6))

        m_by_n_label = Text("M x N = Combinatorial Explosion (50+ Compilers!)", font_size=15, color="#EF4444").shift(UP * 1.8)

        self.play(FadeIn(sources), FadeIn(targets), Create(cross_lines), Write(m_by_n_label), run_time=3.0)
        self.wait(7.4)

        # [11.8s -> 15.9s] Collapse into Intermediate Representation (Hub)
        ir_box = VGroup(
            RoundedRectangle(corner_radius=0.15, width=2.6, height=2.4, stroke_color="#00F0FF", stroke_width=2, fill_color="#0F172A", fill_opacity=0.95),
            Text("Universal\nIR\n(LLVM IR)", font_size=16, color="#00F0FF", line_spacing=0.8)
        ).move_to(DOWN * 0.2)

        ir_lines_in = VGroup(*(Line(s.get_right(), ir_box.get_left(), stroke_color="#388BFD", stroke_width=2) for s in sources))
        ir_lines_out = VGroup(*(Line(ir_box.get_right(), t.get_left(), stroke_color="#10B981", stroke_width=2) for t in targets))

        solution_label = Text("M + N Solution: Decoupled Frontend & Backend!", font_size=15, color="#10B981").shift(UP * 1.8)

        self.play(
            FadeOut(cross_lines),
            FadeOut(m_by_n_label),
            FadeIn(ir_box),
            Create(ir_lines_in),
            Create(ir_lines_out),
            FadeIn(solution_label),
            run_time=2.5
        )
        self.wait(1.6)

        # [16.2s -> 23.9s] Lowering AST to Three-Address Code listing
        self.play(
            FadeOut(sources), FadeOut(targets),
            FadeOut(ir_lines_in), FadeOut(ir_lines_out),
            FadeOut(solution_label),
            ir_box.animate.scale(0.7).to_edge(UP, buff=1.0).to_edge(LEFT, buff=0.8),
            run_time=1.5
        )

        tac_header = Text("Three-Address Code (TAC / Linear IR):", font_size=16, color="#00F0FF")
        tac_code = VGroup(
            Text("; Expression: total = count * 2 + 5;", font="monospace", font_size=12, color="#64748B"),
            Text("t0 = count * 2", font="monospace", font_size=14, color="#F59E0B"),
            Text("t1 = t0 + 5", font="monospace", font_size=14, color="#F59E0B"),
            Text("total = t1", font="monospace", font_size=14, color="#10B981")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18)

        tac_content = VGroup(tac_header, tac_code).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        tac_box = RoundedRectangle(corner_radius=0.15, width=5.6, height=2.6, stroke_color="#00F0FF", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        tac_card = VGroup(tac_box, tac_content).move_to(np.array([0.0, 0.4, 0]))

        self.play(FadeIn(tac_card, shift=UP*0.2), run_time=2.0)
        self.wait(4.2)

        # [24.2s -> 29.8s] Highlight temporary variables and linear structure
        props = VGroup(
            Text("* Platform-independent abstraction", font_size=13, color="#94A3B8"),
            Text("* Infinite virtual registers (t0, t1...)", font_size=13, color="#10B981"),
            Text("* At most 1 operator per instruction", font_size=13, color="#388BFD")
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.14).move_to(np.array([0.0, -1.6, 0]))

        self.play(FadeIn(props, lag_ratio=0.15), run_time=2.0)
        self.wait(3.5)

        # [30.1s -> 35.2s] Target dozens of architectures with one shared optimizer
        self.play(
            Indicate(tac_card, color="#00F0FF", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(3.0)