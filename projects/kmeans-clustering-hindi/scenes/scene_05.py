from manim import *

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
        r1 = Text("• K = 1 -> 3: Steep drop in WCSS\n  (Dramatic variance reduction)", font_size=11, color="#CBD5E1").next_to(rh, DOWN, buff=0.35)
        r2 = Text("• K > 3: Rate of drop slows down\n  (Diminishing returns per cluster)", font_size=11, color="#CBD5E1").next_to(r1, DOWN, buff=0.3)
        r3 = Text("• Elbow Point (K = 3):\n  Optimal trade-off point!", font_size=12, color="#10B981", weight=BOLD).next_to(r2, DOWN, buff=0.35)

        self.play(FadeIn(VGroup(right_box, rh, r1, r2, r3), shift=LEFT*0.2), run_time=2.0)
        self.wait(4.5)

        # 5. Highlight the Elbow Point at K=3
        elbow_circle = Circle(radius=0.25, color="#10B981", stroke_width=2.5).move_to(pts[2])
        elbow_arrow = Arrow(pts[2] + UR * 0.8, pts[2] + UR * 0.15, buff=0.05, color="#10B981", stroke_width=3.0)
        elbow_badge = Text("Elbow Point: K = 3", font_size=12, color="#10B981", weight=BOLD).next_to(elbow_arrow, UR, buff=0.1)

        self.play(Create(elbow_circle), Create(elbow_arrow), FadeIn(elbow_badge), run_time=1.8)
        self.play(Indicate(elbow_circle, scale_factor=1.3, color="#34D399"), run_time=2.0)
        self.wait(20.0)
