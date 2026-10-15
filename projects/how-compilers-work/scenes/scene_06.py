from manim import *
import numpy as np

class Scene06(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # Title Band
        title = Text("6. Optimization: The Engine of Pure Performance", font_size=26, color="#00F0FF").scale_to_fit_width(12.0)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # [0.0s -> 4.1s] The most sophisticated stage: The Optimizer
        opt_badge = VGroup(
            RoundedRectangle(corner_radius=0.15, width=4.2, height=0.65, color="#F59E0B", fill_opacity=0.2),
            Text("Phase 4: Intermediate Code Optimizer", font_size=15, color="#F59E0B")
        ).shift(UP * 2.2)
        self.play(FadeIn(opt_badge, shift=DOWN*0.2), run_time=1.0)
        self.wait(2.1)

        # [4.4s -> 10.5s] Human code vs Machine efficiency
        self.play(opt_badge.animate.scale(0.85).to_edge(UP, buff=1.0).to_edge(LEFT, buff=0.8), run_time=1.0)

        # Wide code panel (width 5.6) so comments never poke out
        code_box = RoundedRectangle(corner_radius=0.15, width=5.6, height=3.2, stroke_color="#388BFD", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.9)
        code_card_title = Text("Intermediate Representation Listing:", font_size=14, color="#94A3B8")

        line1 = Text("dead_val = 100 * 0;", font="monospace", font_size=13, color="#64748B")
        line2 = Text("t0 = count * 2;", font="monospace", font_size=13, color="#F59E0B")
        line3 = Text("t1 = t0 + (3 + 2);", font="monospace", font_size=13, color="#F59E0B")
        line4 = Text("total = t1;", font="monospace", font_size=13, color="#10B981")

        lines_grp = VGroup(line1, line2, line3, line4).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
        code_content = VGroup(code_card_title, lines_grp).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        code_panel = VGroup(code_box, code_content).move_to(np.array([-3.4, 0.0, 0]))

        self.play(FadeIn(code_panel, shift=RIGHT*0.3), run_time=1.5)
        self.wait(3.5)

        # [10.9s -> 17.3s] Data flow & control flow analysis
        scan_line = Line(code_box.get_left(), code_box.get_right(), color="#00F0FF", stroke_width=2.5)
        scan_line.move_to(code_box.get_top())

        self.play(
            scan_line.animate.move_to(code_box.get_bottom()),
            run_time=2.5
        )
        self.play(FadeOut(scan_line), run_time=0.5)
        self.wait(3.4)

        # [17.6s -> 22.6s] Pass 1: Constant Folding
        pass1_badge = VGroup(
            RoundedRectangle(corner_radius=0.1, width=4.4, height=0.6, color="#00F0FF", fill_opacity=0.2),
            Text("Pass 1: Constant Folding (3+2 -> 5)", font_size=13, color="#00F0FF")
        ).move_to(np.array([3.5, 0.9, 0]))

        new_line3 = Text("t1 = t0 + 5;", font="monospace", font_size=13, color="#10B981").move_to(line3.get_center(), aligned_edge=LEFT)

        self.play(
            FadeIn(pass1_badge, shift=LEFT*0.2),
            Transform(line3, new_line3),
            run_time=1.5
        )
        self.wait(3.5)

        # [23.0s -> 29.3s] Pass 2: Strength Reduction (count * 2 -> count << 1)
        pass2_badge = VGroup(
            RoundedRectangle(corner_radius=0.1, width=4.4, height=0.6, color="#10B981", fill_opacity=0.2),
            Text("Pass 2: Strength Reduction (*2 -> <<1)", font_size=13, color="#10B981")
        ).next_to(pass1_badge, DOWN, buff=0.25)

        new_line2 = Text("t0 = count << 1;  // 1 cycle", font="monospace", font_size=13, color="#10B981").move_to(line2.get_center(), aligned_edge=LEFT)

        self.play(
            FadeIn(pass2_badge, shift=LEFT*0.2),
            Transform(line2, new_line2),
            run_time=1.5
        )
        self.wait(4.8)

        # [29.6s -> 37.0s] Pass 3: Dead Code Elimination
        pass3_badge = VGroup(
            RoundedRectangle(corner_radius=0.1, width=4.4, height=0.6, color="#EF4444", fill_opacity=0.2),
            Text("Pass 3: Dead Code Elimination", font_size=13, color="#EF4444")
        ).next_to(pass2_badge, DOWN, buff=0.25)

        strike = Line(line1.get_left(), line1.get_right(), color="#EF4444", stroke_width=2.5)

        self.play(
            FadeIn(pass3_badge, shift=LEFT*0.2),
            Create(strike),
            line1.animate.set_opacity(0.2),
            run_time=1.5
        )
        self.wait(1.5)

        # Fade out dead code completely without shifting remaining lines into title!
        self.play(
            FadeOut(line1), FadeOut(strike),
            run_time=1.0
        )

        final_badge = Text("Optimized: 40% Faster, Zero Dead Cycles!", font_size=14, color="#10B981").next_to(code_box, DOWN, buff=0.3)
        self.play(Write(final_badge), Indicate(code_box, color="#10B981", scale_factor=1.03), run_time=2.0)
        self.wait(1.3)