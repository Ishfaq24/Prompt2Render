from manim import *

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = 37.87

        title = Text("How Models Learn: Loss & Gradient Descent", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("لاس فنکشن (غلطی ناپن) تہٕ گریڈینٹ ڈیسینٹ", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # Left Card: Formulas
        card_f = RoundedRectangle(corner_radius=0.18, width=5.0, height=4.2, stroke_color="#334155", stroke_width=1.8, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 3.4 + DOWN * 0.55)
        f_top = Text("Optimization Objective", font_size=15, weight=BOLD, color="#38BDF8").move_to(card_f.get_top() + DOWN * 0.35)

        l_txt = Text("1. Mean Squared Error (Loss):", font_size=11, color="#94A3B8").move_to(card_f.get_top() + DOWN * 0.95 + LEFT * 0.4)
        l_mat = MathTex(r"J(w) = \frac{1}{N} \sum_{i=1}^{N} (y_i - \hat{y}_i)^2", font_size=22, color=YELLOW_C).next_to(l_txt, DOWN, buff=0.18).align_to(l_txt, LEFT)

        u_txt = Text("2. Gradient Descent Step:", font_size=11, color="#94A3B8").move_to(card_f.get_top() + DOWN * 2.15 + LEFT * 0.4)
        u_mat = MathTex(r"w_{new} = w_{old} - \alpha \frac{\partial J}{\partial w}", font_size=22, color="#38BDF8").next_to(u_txt, DOWN, buff=0.18).align_to(u_txt, LEFT)

        badge_k = RoundedRectangle(corner_radius=0.1, width=4.2, height=0.45, color="#059669", fill_color="#064E3B", fill_opacity=0.9).move_to(card_f.get_bottom() + UP * 0.45)
        badge_txt = Text("ہر قدمَس سٟتؠ چھِ غلطی کم گژھان", font="Arial", font_size=11, color="#6EE7B7").move_to(badge_k.get_center())

        grp_left = VGroup(card_f, f_top, l_txt, l_mat, u_txt, u_mat, badge_k, badge_txt)
        self.play(FadeIn(grp_left), run_time=1.4)

        # Right Side: Parabola
        axes = Axes(
            x_range=[-2.2, 2.2, 1],
            y_range=[0, 5, 1],
            x_length=4.8,
            y_length=3.4,
            axis_config={"color": "#64748B", "stroke_width": 1.8},
            tips=False
        ).move_to(RIGHT * 3.4 + DOWN * 0.55)

        x_l = Text("Weight (w)", font="Segoe UI", font_size=11, color="#94A3B8").next_to(axes.x_axis, DOWN, buff=0.15).shift(RIGHT * 1.2)
        y_l = Text("Loss J(w)", font="Segoe UI", font_size=11, color="#94A3B8").next_to(axes.y_axis, UP, buff=0.12)

        curve = axes.plot(lambda x: x**2, x_range=[-2.0, 2.0], color="#38BDF8", stroke_width=3.0)
        min_dot = Dot(point=axes.c2p(0, 0), radius=0.07, color="#10B981")
        min_lbl = Text("Minimum w*", font="Segoe UI", font_size=10, color="#10B981", weight=BOLD).next_to(min_dot, UP, buff=0.25)

        self.play(Create(axes), FadeIn(x_l), FadeIn(y_l), Create(curve), run_time=1.5)
        self.play(FadeIn(min_dot), FadeIn(min_lbl), run_time=0.6)

        # Animated ball stepping down
        ball = Dot(point=axes.c2p(1.8, 3.24), radius=0.11, color="#F59E0B")
        ball_tag = Text("Initial Error", font_size=10, color="#FBBF24").next_to(ball, RIGHT, buff=0.1)
        self.play(FadeIn(ball), FadeIn(ball_tag), run_time=0.8)
        self.wait(0.8)

        # Step 1
        self.play(ball.animate.move_to(axes.c2p(1.1, 1.21)), FadeOut(ball_tag), run_time=1.0)
        # Step 2
        self.play(ball.animate.move_to(axes.c2p(0.5, 0.25)), run_time=1.0)
        # Step 3 (Minimum)
        self.play(ball.animate.move_to(axes.c2p(0.0, 0.0)), run_time=1.2)

        glow = Circle(radius=0.3, color="#10B981", stroke_width=2.5).move_to(axes.c2p(0, 0))
        self.play(Create(glow), run_time=0.8)
        self.play(FadeOut(glow), run_time=0.6)

        elapsed = 1.0 + 1.4 + 1.5 + 0.6 + 0.8 + 0.8 + 1.0 + 1.0 + 1.2 + 0.8 + 0.6
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
