from manim import *
import numpy as np

class Scene01(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("K-Means Clustering: Intuition & Overview", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("अनसुपरवाइज्ड लर्निंग (Unsupervised Learning) & डेटा क्लस्टरिंग", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Main Backdrop Card
        card = RoundedRectangle(
            corner_radius=0.2, width=12.6, height=5.2,
            stroke_color="#1E293B", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.85
        ).shift(DOWN * 0.4)
        self.play(FadeIn(card), run_time=1.0)

        # 3. Scatter Points in Feature Space (Unlabeled Data)
        np.random.seed(42)
        c1_pts = np.random.randn(12, 2) * 0.45 + np.array([-3.2, 0.4])
        c2_pts = np.random.randn(12, 2) * 0.45 + np.array([0.0, -1.2])
        c3_pts = np.random.randn(12, 2) * 0.45 + np.array([3.2, 0.7])
        all_pts = np.vstack([c1_pts, c2_pts, c3_pts])

        dots = VGroup()
        for pt in all_pts:
            d = Dot(point=[pt[0], pt[1] - 0.4, 0], radius=0.08, color="#94A3B8")
            dots.add(d)

        info_pill = RoundedRectangle(
            corner_radius=0.15, width=7.2, height=0.55,
            color="#64748B", fill_color="#1E293B", fill_opacity=0.9
        ).move_to(UP * 1.7)
        info_txt = Text("Unlabeled Data Points: No Class Labels Provided", font_size=13, color="#CBD5E1", weight=BOLD).move_to(info_pill.get_center())
        info_grp = VGroup(info_pill, info_txt)

        self.play(FadeIn(info_grp), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(d, scale=0.5) for d in dots], lag_ratio=0.05), run_time=2.5)
        self.wait(3.0)

        # 4. Challenge Tag: Grouping into K Clusters
        target_pill = RoundedRectangle(
            corner_radius=0.15, width=7.8, height=0.55,
            color="#38BDF8", fill_color="#082F49", fill_opacity=0.95
        ).move_to(UP * 1.7)
        target_txt = Text("Goal: Partition Data into K=3 Distinct Clusters", font_size=13, color="#38BDF8", weight=BOLD).move_to(target_pill.get_center())
        self.play(ReplacementTransform(info_grp, VGroup(target_pill, target_txt)), run_time=1.2)
        self.wait(3.5)

        # 5. Centroids Appear
        mu1 = Star(n=4, outer_radius=0.22, inner_radius=0.10, color="#38BDF8", fill_opacity=1.0).move_to([-3.2, 0.0, 0])
        mu2 = Star(n=4, outer_radius=0.22, inner_radius=0.10, color="#10B981", fill_opacity=1.0).move_to([0.0, -1.6, 0])
        mu3 = Star(n=4, outer_radius=0.22, inner_radius=0.10, color="#F59E0B", fill_opacity=1.0).move_to([3.2, 0.3, 0])

        lbl1 = Text("Centroid μ1", font_size=11, color="#38BDF8", weight=BOLD).next_to(mu1, UP, buff=0.15)
        lbl2 = Text("Centroid μ2", font_size=11, color="#10B981", weight=BOLD).next_to(mu2, DOWN, buff=0.15)
        lbl3 = Text("Centroid μ3", font_size=11, color="#F59E0B", weight=BOLD).next_to(mu3, UP, buff=0.15)
        centroids = VGroup(mu1, lbl1, mu2, lbl2, mu3, lbl3)

        self.play(FadeIn(centroids, scale=1.3), run_time=1.8)
        self.wait(2.5)

        # 6. Colors Wave: Cluster Assignment
        anims = []
        for i, d in enumerate(dots):
            if i < 12:
                anims.append(d.animate.set_color("#38BDF8"))
            elif i < 24:
                anims.append(d.animate.set_color("#10B981"))
            else:
                anims.append(d.animate.set_color("#F59E0B"))
        self.play(*anims, run_time=2.2)
        self.wait(2.5)

        # 7. Cluster Enclosing Hulls
        c1_ring = Circle(radius=1.3, color="#38BDF8", stroke_width=2.0).move_to([-3.2, 0.0, 0])
        c2_ring = Circle(radius=1.3, color="#10B981", stroke_width=2.0).move_to([0.0, -1.6, 0])
        c3_ring = Circle(radius=1.3, color="#F59E0B", stroke_width=2.0).move_to([3.2, 0.3, 0])
        rings = VGroup(c1_ring, c2_ring, c3_ring)

        self.play(Create(rings), run_time=2.0)
        self.wait(3.5)

        # 8. Summary Footer
        footer = Text("High Intra-cluster Similarity  |  Low Inter-cluster Similarity", font_size=13, color="#FDE68A", weight=BOLD)
        footer.move_to(DOWN * 2.7)
        self.play(FadeIn(footer, shift=UP*0.1), run_time=1.2)
        self.wait(10.0)
