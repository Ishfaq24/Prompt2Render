from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 36.84

        title = Text("Overfitting vs Underfitting (Generalization)", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("ماڈل پیچیدگی تہٕ متوازن جنرلائزیشن", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        pts_x = [-1.4, -0.9, -0.4, 0.1, 0.6, 1.1, 1.5]
        pts_y = [1.8, 0.9, 0.3, 0.1, 0.4, 1.1, 2.0]

        # Panel 1: Underfitting
        p1 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#EF4444", stroke_width=1.8, fill_color="#450A0A", fill_opacity=0.75).move_to(LEFT * 4.2 + DOWN * 0.55)
        t1 = Text("Underfitting", font_size=16, weight=BOLD, color="#F87171").move_to(p1.get_top() + DOWN * 0.35)
        s1 = Text("انڈرفِٹِنٛگ (زیادٕ سادٕ ماڈل)", font="Arial", font_size=10, color="#FECACA").next_to(t1, DOWN, buff=0.08)
        ax1 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={"color": "#64748B", "stroke_width": 1.2}, tips=False).move_to(p1.get_center() + DOWN * 0.2)
        dots1 = VGroup(*[Dot(ax1.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        line_u = ax1.plot(lambda x: 0.9, color="#EF4444", stroke_width=2.5)
        b1 = Text("High Bias (بڑی غلطی)", font="Arial", font_size=11, color="#F87171", weight=BOLD).move_to(p1.get_bottom() + UP * 0.45)
        grp1 = VGroup(p1, t1, s1, ax1, dots1, line_u, b1)

        # Panel 2: Good Fit
        p2 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#10B981", stroke_width=2.2, fill_color="#064E3B", fill_opacity=0.85).move_to(DOWN * 0.55)
        t2 = Text("Optimal Fit", font_size=16, weight=BOLD, color="#34D399").move_to(p2.get_top() + DOWN * 0.35)
        s2 = Text("متوازن ماڈل (اصل جنرلائزیشن)", font="Arial", font_size=10, color="#A7F3D0").next_to(t2, DOWN, buff=0.08)
        ax2 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={"color": "#64748B", "stroke_width": 1.2}, tips=False).move_to(p2.get_center() + DOWN * 0.2)
        dots2 = VGroup(*[Dot(ax2.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        curve_opt = ax2.plot(lambda x: 0.7 * x**2 + 0.15, color="#10B981", stroke_width=2.8)
        b2 = Text("Balanced & Robust", font="Segoe UI", font_size=11, color="#34D399", weight=BOLD).move_to(p2.get_bottom() + UP * 0.45)
        grp2 = VGroup(p2, t2, s2, ax2, dots2, curve_opt, b2)

        # Panel 3: Overfitting
        p3 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#F59E0B", stroke_width=1.8, fill_color="#78350F", fill_opacity=0.75).move_to(RIGHT * 4.2 + DOWN * 0.55)
        t3 = Text("Overfitting", font_size=16, weight=BOLD, color="#FBBF24").move_to(p3.get_top() + DOWN * 0.35)
        s3 = Text("اوورفِٹِنٛگ (رٹہٕ مارُن)", font="Arial", font_size=10, color="#FDE68A").next_to(t3, DOWN, buff=0.08)
        ax3 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={"color": "#64748B", "stroke_width": 1.2}, tips=False).move_to(p3.get_center() + DOWN * 0.2)
        dots3 = VGroup(*[Dot(ax3.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        curve_over = ax3.plot(lambda x: 0.7*x**2 + 0.15 + 0.28*np.sin(6*x), color="#F59E0B", stroke_width=2.2)
        b3 = Text("High Variance (شور رٹُن)", font="Arial", font_size=11, color="#FBBF24", weight=BOLD).move_to(p3.get_bottom() + UP * 0.45)
        grp3 = VGroup(p3, t3, s3, ax3, dots3, curve_over, b3)

        self.play(FadeIn(grp1, shift=LEFT*0.2), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(grp3, shift=RIGHT*0.2), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.2 + 1.0 + 1.2 + 1.0 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
