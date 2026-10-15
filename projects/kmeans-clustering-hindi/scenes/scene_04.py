from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Visual Convergence & Decision Boundaries", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("विजुअल कन्वर्जेंस और वोरोनोई निर्णय सीमाएं", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Main Visual Canvas Card
        bg_card = RoundedRectangle(
            corner_radius=0.2, width=12.2, height=5.2,
            stroke_color="#1E293B", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.85
        ).shift(DOWN * 0.4)
        self.play(FadeIn(bg_card), run_time=1.0)

        # 3. True cluster centers
        t1, t2, t3 = np.array([-3.0, 0.4, 0]), np.array([0.0, -1.2, 0]), np.array([3.0, 0.8, 0])

        np.random.seed(99)
        c1 = [Dot(t1 + np.append(np.random.randn(2)*0.45, 0) + DOWN*0.2, radius=0.08, color="#38BDF8") for _ in range(10)]
        c2 = [Dot(t2 + np.append(np.random.randn(2)*0.45, 0) + DOWN*0.2, radius=0.08, color="#10B981") for _ in range(10)]
        c3 = [Dot(t3 + np.append(np.random.randn(2)*0.45, 0) + DOWN*0.2, radius=0.08, color="#F59E0B") for _ in range(10)]
        all_dots = VGroup(*c1, *c2, *c3)
        self.play(LaggedStart(*[FadeIn(d, scale=0.5) for d in all_dots], lag_ratio=0.04), run_time=2.0)

        # 4. Iteration 0: Random Displaced Centroids
        m1 = Star(n=4, outer_radius=0.25, inner_radius=0.12, color="#38BDF8", fill_opacity=1.0).move_to([-1.5, 1.2, 0])
        m2 = Star(n=4, outer_radius=0.25, inner_radius=0.12, color="#10B981", fill_opacity=1.0).move_to([1.5, -0.2, 0])
        m3 = Star(n=4, outer_radius=0.25, inner_radius=0.12, color="#F59E0B", fill_opacity=1.0).move_to([0.5, 1.8, 0])
        cents = VGroup(m1, m2, m3)

        iter_badge = RoundedRectangle(corner_radius=0.12, width=3.4, height=0.5, color="#F59E0B", fill_color="#1E293B", fill_opacity=0.9).move_to(UP * 1.7 + RIGHT * 3.8)
        iter_txt = Text("Iteration 0: Random Seeds", font_size=12, color="#FDE68A", weight=BOLD).move_to(iter_badge.get_center())
        iter_grp = VGroup(iter_badge, iter_txt)

        self.play(FadeIn(cents, scale=1.5), FadeIn(iter_grp), run_time=1.8)
        self.wait(3.5)

        # 5. Iteration 1: Centroids move halfway
        iter1_txt = Text("Iteration 1: Updating Means", font_size=12, color="#38BDF8", weight=BOLD).move_to(iter_badge.get_center())
        self.play(
            ReplacementTransform(iter_txt, iter1_txt),
            m1.animate.move_to([-2.4, 0.6, 0]),
            m2.animate.move_to([0.2, -0.9, 0]),
            m3.animate.move_to([2.2, 0.9, 0]),
            run_time=3.0
        )
        self.wait(4.0)

        # 6. Iteration 2: Centroids reach stable true positions
        iter2_txt = Text("Iteration 2: Stabilized at Centers", font_size=12, color="#10B981", weight=BOLD).move_to(iter_badge.get_center())
        iter_badge.animate.set_color("#10B981")
        self.play(
            ReplacementTransform(iter1_txt, iter2_txt),
            m1.animate.move_to(t1 + DOWN*0.2),
            m2.animate.move_to(t2 + DOWN*0.2),
            m3.animate.move_to(t3 + DOWN*0.2),
            run_time=2.5
        )
        self.wait(3.0)

        # 7. Voronoi Separation Lines
        v_line1 = Line([-1.5, -2.5, 0], [-1.5, 1.8, 0], color="#64748B", stroke_width=1.5)
        v_line2 = Line([1.5, -2.5, 0], [1.5, 1.8, 0], color="#64748B", stroke_width=1.5)
        self.play(Create(v_line1), Create(v_line2), run_time=1.5)
        self.wait(2.5)

        # 8. Guaranteed Convergence Banner
        conv_pill = RoundedRectangle(
            corner_radius=0.15, width=8.5, height=0.6,
            color="#10B981", fill_color="#064E3B", fill_opacity=0.9
        ).move_to(DOWN * 2.6)
        conv_txt = Text("Guaranteed Convergence: WCSS Decreases Monotonically", font_size=13, color="#6EE7B7", weight=BOLD).move_to(conv_pill.get_center())
        self.play(FadeIn(VGroup(conv_pill, conv_txt), shift=UP*0.1), run_time=1.2)
        self.wait(14.0)
