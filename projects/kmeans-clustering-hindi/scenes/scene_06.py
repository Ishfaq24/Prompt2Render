from manim import *

class Scene06(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Initialization Trap & K-Means++ Seeding", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("इनिशियलाइजेशन की समस्या और K-Means++ स्मार्ट सीडिंग", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Split Stage: Bad Random Seeding vs K-Means++
        # Left Box: Standard Random
        l_box = RoundedRectangle(
            corner_radius=0.18, width=5.6, height=4.8,
            stroke_color="#F43F5E", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(LEFT * 3.2 + DOWN * 0.4)
        l_hdr = Text("Standard Random Seeding", font_size=13, color="#F43F5E", weight=BOLD).move_to(l_box.get_top() + DOWN * 0.35)
        l_warn = Text("Hazard: Poor Local Minima!", font_size=11, color="#FDA4AF", weight=BOLD).next_to(l_hdr, DOWN, buff=0.2)

        # Clustered bad seeds in one corner
        bad_seed1 = Dot(LEFT*4.2 + DOWN*0.2, radius=0.14, color="#F43F5E")
        bad_seed2 = Dot(LEFT*3.8 + DOWN*0.5, radius=0.14, color="#F43F5E")
        bad_seed3 = Dot(LEFT*4.0 + UP*0.1, radius=0.14, color="#F43F5E")
        bad_seeds = VGroup(bad_seed1, bad_seed2, bad_seed3)
        bad_lbl = Text("All 3 seeds clumped together!\nFails to discover distant clusters.", font_size=10, color="#E2E8F0").move_to(l_box.get_bottom() + UP * 0.6)

        self.play(FadeIn(VGroup(l_box, l_hdr, l_warn, bad_seeds, bad_lbl), shift=RIGHT*0.2), run_time=2.0)
        self.wait(5.0)

        # Right Box: K-Means++
        r_box = RoundedRectangle(
            corner_radius=0.18, width=5.6, height=4.8,
            stroke_color="#10B981", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(RIGHT * 3.2 + DOWN * 0.4)
        r_hdr = Text("K-Means++ Smart Seeding", font_size=13, color="#10B981", weight=BOLD).move_to(r_box.get_top() + DOWN * 0.35)

        r_sub = Text("Arthur & Vassilvitskii (2007)", font_size=10, color="#94A3B8").next_to(r_hdr, DOWN, buff=0.15)
        r_formula_txt = Text("Selection Probability Formula:", font_size=11, color="#6EE7B7").next_to(r_sub, DOWN, buff=0.25)
        r_formula = MathTex(
            r"P(x) = \frac{D(x)^2}{\sum_{x'} D(x')^2}",
            font_size=18, color="#FDE68A"
        ).next_to(r_formula_txt, DOWN, buff=0.2)

        r_expl = Text("D(x) = Distance to closest existing centroid.\nPoints far away get high probability!", font_size=10, color="#CBD5E1").next_to(r_formula, DOWN, buff=0.25)
        r_sklearn = Text("Default in scikit-learn KMeans", font_size=11, color="#38BDF8", weight=BOLD).move_to(r_box.get_bottom() + UP * 0.4)

        self.play(FadeIn(VGroup(r_box, r_hdr, r_sub, r_formula_txt, r_formula, r_expl, r_sklearn), shift=LEFT*0.2), run_time=2.2)
        self.wait(6.0)

        # Highlight K-Means++ Formula
        self.play(Indicate(r_formula, scale_factor=1.12, color="#10B981"), run_time=2.0)
        self.wait(22.0)
