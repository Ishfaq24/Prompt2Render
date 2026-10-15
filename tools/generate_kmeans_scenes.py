"""Generates production-grade Manim CE scenes for K-Means Clustering (Hindi).

Each scene is mathematically accurate, visually rich, and paced to the exact
duration of its narration audio.
"""
from pathlib import Path

SCENES_DIR = Path("projects/kmeans-clustering-hindi/scenes")
SCENES_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SCENE 01: Introduction & Unsupervised Clustering (37.78s)
# =============================================================================
scene_01_code = '''from manim import *
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
'''

# =============================================================================
# SCENE 02: Mathematical Formulation & Objective Function (43.90s)
# =============================================================================
scene_02_code = '''from manim import *

class Scene02(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Mathematical Foundations & WCSS Objective", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("सेंट्रोइड्स, यूक्लिडियन दूरी और Within-Cluster Sum of Squares", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Left Card: Centroid and Distance Metric
        left_box = RoundedRectangle(
            corner_radius=0.18, width=5.8, height=4.9,
            stroke_color="#334155", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(LEFT * 3.3 + DOWN * 0.4)
        left_hdr = Text("1. Centroid & Distance Metric", font_size=14, color="#38BDF8", weight=BOLD).move_to(left_box.get_top() + DOWN * 0.35)

        t_centroid = Text("Centroid (Cluster Mean Vector):", font_size=12, color="#94A3B8").move_to(left_box.get_top() + DOWN * 0.85)
        eq_centroid = MathTex(r"\\mu_k = \\frac{1}{|C_k|} \\sum_{x_i \\in C_k} x_i", font_size=19, color="#67E8F9").next_to(t_centroid, DOWN, buff=0.2)

        t_dist = Text("Euclidean Distance Metric:", font_size=12, color="#94A3B8").next_to(eq_centroid, DOWN, buff=0.4)
        eq_dist = MathTex(r"d(x_i, \\mu_k) = \\|x_i - \\mu_k\\|_2 = \\sqrt{\\sum_{j=1}^d (x_{ij} - \\mu_{kj})^2}", font_size=16, color="#34D399").next_to(t_dist, DOWN, buff=0.2)

        left_grp = VGroup(left_box, left_hdr, t_centroid, eq_centroid, t_dist, eq_dist)
        self.play(FadeIn(left_grp, shift=RIGHT*0.2), run_time=2.0)
        self.wait(5.0)

        # 3. Right Card: The Objective Function (Inertia / WCSS)
        right_box = RoundedRectangle(
            corner_radius=0.18, width=5.8, height=4.9,
            stroke_color="#334155", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(RIGHT * 3.3 + DOWN * 0.4)
        right_hdr = Text("2. WCSS (Inertia) Objective Function", font_size=14, color="#F59E0B", weight=BOLD).move_to(right_box.get_top() + DOWN * 0.35)

        t_wcss = Text("Within-Cluster Sum of Squares:", font_size=12, color="#94A3B8").move_to(right_box.get_top() + DOWN * 0.85)
        eq_wcss = MathTex(
            r"J = \\sum_{k=1}^K \\sum_{x_i \\in C_k} \\|x_i - \\mu_k\\|^2",
            font_size=21, color="#FDE68A"
        ).next_to(t_wcss, DOWN, buff=0.25)

        t_goal = Text("Optimization Goal:", font_size=12, color="#F43F5E", weight=BOLD).next_to(eq_wcss, DOWN, buff=0.4)
        eq_opt = MathTex(r"\\min_{C, \\mu} \\; J", font_size=22, color="#F43F5E").next_to(t_goal, DOWN, buff=0.2)

        desc = Text("Minimizes variance inside each cluster\\nto achieve tight, compact groups.", font_size=11, color="#CBD5E1").next_to(eq_opt, DOWN, buff=0.3)

        right_grp = VGroup(right_box, right_hdr, t_wcss, eq_wcss, t_goal, eq_opt, desc)
        self.play(FadeIn(right_grp, shift=LEFT*0.2), run_time=2.0)
        self.wait(6.0)

        # 4. Highlight WCSS formula
        self.play(Indicate(eq_wcss, scale_factor=1.1, color="#F59E0B"), run_time=2.0)
        self.wait(5.0)

        # 5. Highlight Optimization Goal
        self.play(Indicate(eq_opt, scale_factor=1.12, color="#10B981"), run_time=2.0)
        self.wait(18.0)
'''

# =============================================================================
# SCENE 03: Lloyd's Algorithm: 4 Iterative Steps (46.21s)
# =============================================================================
scene_03_code = '''from manim import *

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Lloyd's Algorithm: The 4 Core Iterative Steps", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("लॉयड का एल्गोरिदम: चक्रीय कार्यप्रणाली और कन्वर्जेंस", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. The 4 Step Cards
        coords = [
            (LEFT * 4.4 + UP * 0.4, "Step 1: Initialization", "Choose K initial centroids\\nrandomly in feature space", "#38BDF8"),
            (LEFT * 1.5 + DOWN * 0.8, "Step 2: Assignment", "Assign each point x_i\\nto the nearest centroid", "#10B981"),
            (RIGHT * 1.5 + UP * 0.4, "Step 3: Update", "Recalculate centroids as\\nthe mean of assigned points", "#F59E0B"),
            (RIGHT * 4.4 + DOWN * 0.8, "Step 4: Convergence", "Check if centroids stopped\\nmoving or delta J < epsilon", "#EC4899"),
        ]

        cards = []
        for pos, stitle, sdesc, col in coords:
            box = RoundedRectangle(
                corner_radius=0.15, width=2.7, height=2.8,
                stroke_color=col, stroke_width=1.5,
                fill_color="#0F172A", fill_opacity=0.9
            ).move_to(pos)
            h = Text(stitle, font_size=12, color=col, weight=BOLD).move_to(box.get_top() + DOWN * 0.4)
            d = Text(sdesc, font_size=10, color="#CBD5E1").move_to(box.get_center() + DOWN * 0.2)
            cards.append(VGroup(box, h, d))

        for i, card in enumerate(cards):
            self.play(FadeIn(card, shift=UP*0.2), run_time=1.5)
            self.wait(3.5 if i < 3 else 5.0)

        # 3. Connecting Flow Arrows
        a1 = Arrow(cards[0].get_right(), cards[1].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        a2 = Arrow(cards[1].get_right(), cards[2].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        a3 = Arrow(cards[2].get_right(), cards[3].get_left(), buff=0.15, color="#64748B", stroke_width=2.5)
        arrows = VGroup(a1, a2, a3)
        self.play(Create(arrows), run_time=2.0)
        self.wait(3.0)

        # 4. Repeat Loop Back
        loop_curve = CurvedArrow(
            cards[3].get_bottom() + LEFT * 0.3,
            cards[1].get_bottom() + RIGHT * 0.3,
            radius=4.5, color="#F59E0B", stroke_width=3.0
        )
        loop_lbl = Text("Repeat Until Convergence (Centroids Stable)", font_size=12, color="#FDE68A", weight=BOLD).next_to(loop_curve, DOWN, buff=0.15)
        self.play(Create(loop_curve), FadeIn(loop_lbl), run_time=2.0)
        self.wait(15.0)
'''

# =============================================================================
# SCENE 04: Visual Convergence & Voronoi Boundaries (41.34s)
# =============================================================================
scene_04_code = '''from manim import *
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
'''

# =============================================================================
# SCENE 05: Optimal K Selection: The Elbow Method (45.42s)
# =============================================================================
scene_05_code = '''from manim import *

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Optimal K Selection: The Elbow Method", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("सर्वश्रेष्ठ K का चयन और एल्बो वक्र (WCSS vs Clusters)", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Coordinate Axes for Elbow Curve
        axes = Axes(
            x_range=[1, 8, 1],
            y_range=[0, 1000, 200],
            x_length=6.5,
            y_length=4.0,
            axis_config={"color": "#64748B", "include_numbers": True, "font_size": 11}
        ).move_to(LEFT * 2.8 + DOWN * 0.4)

        x_lbl = Text("Number of Clusters (K)", font_size=12, color="#94A3B8").next_to(axes.x_axis, DOWN, buff=0.25)
        y_lbl = Text("WCSS / Inertia (J)", font_size=12, color="#94A3B8").next_to(axes.y_axis, UP, buff=0.25).rotate(90 * DEGREES)

        self.play(Create(axes), FadeIn(x_lbl), FadeIn(y_lbl), run_time=2.0)
        self.wait(3.0)

        # 3. Data points on the curve: K=1 to 7
        k_vals = [1, 2, 3, 4, 5, 6, 7]
        wcss_vals = [920, 510, 210, 160, 130, 110, 95]
        pts = [axes.c2p(k, w) for k, w in zip(k_vals, wcss_vals)]

        # Draw connecting line
        curve_lines = VGroup()
        for i in range(len(pts) - 1):
            seg = Line(pts[i], pts[i+1], color="#F59E0B", stroke_width=3.5)
            curve_lines.add(seg)

        dots = VGroup(*[Dot(p, radius=0.09, color="#FDE68A") for p in pts])

        self.play(Create(curve_lines), Create(dots), run_time=3.5)
        self.wait(4.0)

        # 4. Right Side Explanation Card
        right_box = RoundedRectangle(
            corner_radius=0.18, width=4.8, height=4.2,
            stroke_color="#334155", stroke_width=1.5,
            fill_color="#0F172A", fill_opacity=0.9
        ).move_to(RIGHT * 3.6 + DOWN * 0.4)

        rh = Text("Identifying The Elbow", font_size=14, color="#38BDF8", weight=BOLD).move_to(right_box.get_top() + DOWN * 0.4)
        r1 = Text("• K = 1 -> 3: Steep drop in WCSS\\n  (Dramatic variance reduction)", font_size=11, color="#CBD5E1").next_to(rh, DOWN, buff=0.35)
        r2 = Text("• K > 3: Rate of drop slows down\\n  (Diminishing returns per cluster)", font_size=11, color="#CBD5E1").next_to(r1, DOWN, buff=0.3)
        r3 = Text("• Elbow Point (K = 3):\\n  Optimal trade-off point!", font_size=12, color="#10B981", weight=BOLD).next_to(r2, DOWN, buff=0.35)

        self.play(FadeIn(VGroup(right_box, rh, r1, r2, r3), shift=LEFT*0.2), run_time=2.0)
        self.wait(4.5)

        # 5. Highlight the Elbow Point at K=3
        elbow_circle = Circle(radius=0.25, color="#10B981", stroke_width=2.5).move_to(pts[2])
        elbow_arrow = Arrow(pts[2] + UR * 0.8, pts[2] + UR * 0.15, buff=0.05, color="#10B981", stroke_width=3.0)
        elbow_badge = Text("Elbow Point: K = 3", font_size=12, color="#10B981", weight=BOLD).next_to(elbow_arrow, UR, buff=0.1)

        self.play(Create(elbow_circle), Create(elbow_arrow), FadeIn(elbow_badge), run_time=1.8)
        self.play(Indicate(elbow_circle, scale_factor=1.3, color="#34D399"), run_time=2.0)
        self.wait(20.0)
'''

# =============================================================================
# SCENE 06: Initialization Sensitivity & K-Means++ (41.80s)
# =============================================================================
scene_06_code = '''from manim import *

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
        bad_lbl = Text("All 3 seeds clumped together!\\nFails to discover distant clusters.", font_size=10, color="#E2E8F0").move_to(l_box.get_bottom() + UP * 0.6)

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
            r"P(x) = \\frac{D(x)^2}{\\sum_{x\'} D(x\')^2}",
            font_size=18, color="#FDE68A"
        ).next_to(r_formula_txt, DOWN, buff=0.2)

        r_expl = Text("D(x) = Distance to closest existing centroid.\\nPoints far away get high probability!", font_size=10, color="#CBD5E1").next_to(r_formula, DOWN, buff=0.25)
        r_sklearn = Text("Default in scikit-learn KMeans", font_size=11, color="#38BDF8", weight=BOLD).move_to(r_box.get_bottom() + UP * 0.4)

        self.play(FadeIn(VGroup(r_box, r_hdr, r_sub, r_formula_txt, r_formula, r_expl, r_sklearn), shift=LEFT*0.2), run_time=2.2)
        self.wait(6.0)

        # Highlight K-Means++ Formula
        self.play(Indicate(r_formula, scale_factor=1.12, color="#10B981"), run_time=2.0)
        self.wait(22.0)
'''

# =============================================================================
# SCENE 07: Applications, Strengths & Limitations (41.42s)
# =============================================================================
scene_07_code = '''from manim import *

class Scene07(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("Summary: Strengths, Limitations & Applications", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("फायदे, सीमाएं, वास्तविक अनुप्रयोग और निष्कर्ष", font="Nirmala UI", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.2), FadeIn(subtitle), run_time=1.5)

        # 2. Three Pillar Cards
        coords = [
            (LEFT * 4.2 + DOWN * 0.3, "1. Core Strengths", [
                "• High Computational Speed",
                "• Time Complexity: O(t * K * n * d)",
                "• Easy to Implement & Interpret",
                "• Scales to Millions of Samples"
            ], "#10B981"),
            (DOWN * 0.3, "2. Key Limitations", [
                "• Assumes Spherical Clusters",
                "• Sensitive to Scale (Scale First!)",
                "• Highly Sensitive to Outliers",
                "• Requires Manual Choice of K"
            ], "#F43F5E"),
            (RIGHT * 4.2 + DOWN * 0.3, "3. Real-World Uses", [
                "• Customer Segmentation",
                "• Image Color Quantization",
                "• Document & Topic Grouping",
                "• Anomaly / Fraud Detection"
            ], "#38BDF8"),
        ]

        cards = []
        for pos, chdr, citems, col in coords:
            box = RoundedRectangle(
                corner_radius=0.15, width=3.8, height=4.2,
                stroke_color=col, stroke_width=1.5,
                fill_color="#0F172A", fill_opacity=0.9
            ).move_to(pos)
            h = Text(chdr, font_size=13, color=col, weight=BOLD).move_to(box.get_top() + DOWN * 0.4)
            lines = VGroup(*[Text(it, font_size=10, color="#CBD5E1") for it in citems]).arrange(DOWN, aligned_edge=LEFT, buff=0.25).move_to(box.get_center() + DOWN * 0.2)
            cards.append(VGroup(box, h, lines))

        for i, card in enumerate(cards):
            self.play(FadeIn(card, shift=UP*0.2), run_time=1.5)
            self.wait(3.0 if i < 2 else 5.0)

        # 3. Final Takeaway Banner
        banner = RoundedRectangle(
            corner_radius=0.15, width=10.5, height=0.6,
            color="#F59E0B", fill_color="#451A03", fill_opacity=0.9
        ).move_to(DOWN * 2.7)
        banner_txt = Text("K-Means: The Essential Foundation of Unsupervised Learning", font_size=13, color="#FDE68A", weight=BOLD).move_to(banner.get_center())
        self.play(FadeIn(VGroup(banner, banner_txt), shift=UP*0.1), run_time=1.2)
        self.wait(18.0)
'''

# Write each scene
scenes = [
    ("scene_01.py", scene_01_code),
    ("scene_02.py", scene_02_code),
    ("scene_03.py", scene_03_code),
    ("scene_04.py", scene_04_code),
    ("scene_05.py", scene_05_code),
    ("scene_06.py", scene_06_code),
    ("scene_07.py", scene_07_code),
]

for filename, content in scenes:
    target = SCENES_DIR / filename
    target.write_text(content, encoding="utf-8")
    print(f"Generated {target}")

print("All 7 Manim scenes generated successfully.")
