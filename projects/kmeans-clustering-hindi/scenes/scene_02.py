from manim import *

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
        eq_centroid = MathTex(r"\mu_k = \frac{1}{|C_k|} \sum_{x_i \in C_k} x_i", font_size=19, color="#67E8F9").next_to(t_centroid, DOWN, buff=0.2)

        t_dist = Text("Euclidean Distance Metric:", font_size=12, color="#94A3B8").next_to(eq_centroid, DOWN, buff=0.4)
        eq_dist = MathTex(r"d(x_i, \mu_k) = \|x_i - \mu_k\|_2 = \sqrt{\sum_{j=1}^d (x_{ij} - \mu_{kj})^2}", font_size=16, color="#34D399").next_to(t_dist, DOWN, buff=0.2)

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
            r"J = \sum_{k=1}^K \sum_{x_i \in C_k} \|x_i - \mu_k\|^2",
            font_size=21, color="#FDE68A"
        ).next_to(t_wcss, DOWN, buff=0.25)

        t_goal = Text("Optimization Goal:", font_size=12, color="#F43F5E", weight=BOLD).next_to(eq_wcss, DOWN, buff=0.4)
        eq_opt = MathTex(r"\min_{C, \mu} \; J", font_size=22, color="#F43F5E").next_to(t_goal, DOWN, buff=0.2)

        desc = Text("Minimizes variance inside each cluster\nto achieve tight, compact groups.", font_size=11, color="#CBD5E1").next_to(eq_opt, DOWN, buff=0.3)

        right_grp = VGroup(right_box, right_hdr, t_wcss, eq_wcss, t_goal, eq_opt, desc)
        self.play(FadeIn(right_grp, shift=LEFT*0.2), run_time=2.0)
        self.wait(6.0)

        # 4. Highlight WCSS formula
        self.play(Indicate(eq_wcss, scale_factor=1.1, color="#F59E0B"), run_time=2.0)
        self.wait(5.0)

        # 5. Highlight Optimization Goal
        self.play(Indicate(eq_opt, scale_factor=1.12, color="#10B981"), run_time=2.0)
        self.wait(18.0)
