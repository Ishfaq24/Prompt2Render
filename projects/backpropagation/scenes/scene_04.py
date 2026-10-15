from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#080B14"

        # -------------------------------------------------------------
        # 1. Elegant Header Band [0.0 - 1.0s]
        # -------------------------------------------------------------
        title = Text("Computing the Output Error: The Seed of Backpropagation", font_size=23, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        title_line = Line(LEFT * 5.2, RIGHT * 5.2, stroke_width=1.5, stroke_color="#38BDF8").next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN * 0.2), Create(title_line), run_time=1.0)

        # -------------------------------------------------------------
        # 2. MSE Loss Parabola & Target Geometry (Left Stage)
        # -------------------------------------------------------------
        axes = Axes(
            x_range=[0, 1.35, 0.2],
            y_range=[0, 1.0, 0.2],
            x_length=5.6,
            y_length=3.8,
            axis_config={"color": "#475569", "stroke_width": 2.0, "include_numbers": True, "font_size": 13}
        ).move_to(LEFT * 3.4 + DOWN * 0.4)

        x_lbl = MathTex(r"\hat{y} \text{ (Prediction)}", font_size=15, color="#94A3B8").next_to(axes.x_axis, DOWN, buff=0.25).align_to(axes.x_axis, RIGHT)
        y_lbl = MathTex(r"L \text{ (Loss)}", font_size=15, color="#94A3B8").next_to(axes.y_axis, UP, buff=0.2)

        curve = axes.plot(lambda x: 0.5 * (x ** 2), x_range=[0, 1.3], color="#FBBF24", stroke_width=3.5)
        curve_glow = axes.plot(lambda x: 0.5 * (x ** 2), x_range=[0, 1.3], color="#FBBF24", stroke_width=7.0, stroke_opacity=0.25)
        curve_lbl = MathTex(r"L = \frac{1}{2}(\hat{y} - y)^2", font_size=16, color="#FDE68A").move_to(axes.c2p(1.05, 0.85))

        target_dot = Dot(axes.c2p(0.0, 0.0), radius=0.09, color="#10B981")
        target_lbl = MathTex(r"y = 0.0 \text{ (Target)}", font_size=13, color="#34D399").next_to(target_dot, DOWN, buff=0.25).shift(RIGHT * 0.5)

        # -------------------------------------------------------------
        # 3. Mathematical Equations (Right Stage Top Alignment)
        # -------------------------------------------------------------
        math_top_y = 2.0
        math_x = 3.4

        eq_loss = MathTex(
            r"L(\hat{y}, y) = \frac{1}{2} (\hat{y} - y)^2",
            font_size=22,
            color=WHITE
        ).move_to(np.array([math_x, math_top_y, 0]))
        eq_loss.set_color_by_tex(r"\frac{1}{2}", "#38BDF8")
        eq_loss.set_color_by_tex(r"(\hat{y} - y)^2", "#FCD34D")

        # [1.0 - 5.5s] Reveal axes, loss curve, and base equation
        self.play(
            Create(axes), Write(x_lbl), Write(y_lbl),
            Create(target_dot), Write(target_lbl),
            run_time=1.8
        )
        self.play(
            Create(curve_glow), Create(curve), Write(curve_lbl),
            FadeIn(eq_loss, shift=DOWN * 0.2),
            run_time=2.0
        )
        self.wait(0.7)

        # -------------------------------------------------------------
        # 4. Derivative Step & Cancellation [5.5 - 13.0s]
        # -------------------------------------------------------------
        eq_diff_step = MathTex(
            r"\frac{\partial L}{\partial \hat{y}} = \frac{1}{2} \cdot 2 (\hat{y} - y)^{2-1}",
            font_size=20,
            color=WHITE
        ).next_to(eq_loss, DOWN, buff=0.28).align_to(eq_loss, LEFT)

        eq_clean_grad = MathTex(
            r"\frac{\partial L}{\partial \hat{y}} = \hat{y} - y",
            font_size=23,
            color="#34D399"
        ).next_to(eq_loss, DOWN, buff=0.28).align_to(eq_loss, LEFT)

        cancel_note = Text(
            "Exponent 2 cancels 1/2 cleanly",
            font_size=11,
            color="#7DD3FC"
        ).next_to(eq_diff_step, DOWN, buff=0.18).align_to(eq_loss, LEFT)

        self.play(Write(eq_diff_step), run_time=1.8)
        self.play(FadeIn(cancel_note), run_time=1.0)
        self.wait(1.5)

        # Swap intermediate derivative with clean gradient formula to save vertical real estate
        self.play(
            FadeOut(cancel_note),
            ReplacementTransform(eq_diff_step, eq_clean_grad),
            run_time=1.6
        )
        self.wait(1.6)

        # -------------------------------------------------------------
        # 5. Operating Point at y_hat = 0.82 & Tangent Slope [13.0 - 21.8s]
        # -------------------------------------------------------------
        y_val = 0.82
        loss_val = 0.5 * (y_val ** 2)
        pt_coords = axes.c2p(y_val, loss_val)

        op_dot = Dot(pt_coords, radius=0.1, color="#F43F5E")
        op_glow = Dot(pt_coords, radius=0.22, color="#F43F5E", fill_opacity=0.3)
        op_lbl = MathTex(r"\hat{y} = 0.82", font_size=14, color="#FDA4AF").next_to(op_dot, UP + RIGHT, buff=0.12)

        tan_line = axes.plot(
            lambda x: loss_val + 0.82 * (x - y_val),
            x_range=[0.48, 1.15],
            color="#F43F5E",
            stroke_width=2.5
        )

        eq_eval = MathTex(
            r"\frac{\partial L}{\partial \hat{y}} = 0.82 - 0.00 = +0.82",
            font_size=21,
            color="#FCD34D"
        ).next_to(eq_clean_grad, DOWN, buff=0.28).align_to(eq_loss, LEFT)

        self.play(
            FadeIn(op_glow), Create(op_dot), Write(op_lbl),
            Create(tan_line),
            Write(eq_eval),
            run_time=2.2
        )

        # Right triangle indicator positioned cleanly
        slope_p1 = axes.c2p(0.82, loss_val)
        slope_p2 = axes.c2p(1.05, loss_val)
        slope_p3 = axes.c2p(1.05, loss_val + 0.82 * (1.05 - 0.82))
        leg_h = Line(slope_p1, slope_p2, stroke_color="#94A3B8", stroke_width=1.5)
        leg_v = Line(slope_p2, slope_p3, stroke_color="#94A3B8", stroke_width=1.5)
        slope_lbl = MathTex(r"\text{Slope} = +0.82", font_size=11, color="#FDA4AF").next_to(leg_v, RIGHT, buff=0.1)
        slope_triangle = VGroup(leg_h, leg_v, slope_lbl)

        self.play(Create(slope_triangle), run_time=1.6)
        self.wait(5.0)

        # -------------------------------------------------------------
        # 6. Directional Interpretation: Push Downward [21.8 - 29.8s]
        # -------------------------------------------------------------
        # Curve arrow safely positioned within axes bounds
        push_arrow = CurvedArrow(
            axes.c2p(0.72, 0.26),
            axes.c2p(0.20, 0.04),
            angle=-TAU / 11,
            color="#34D399",
            stroke_width=3.2
        )
        push_lbl = Text("Nudge Downward (-∇L)", font_size=11, color="#34D399", weight=BOLD).move_to(axes.c2p(0.50, 0.22))

        # Interpretation Card positioned safely below equations
        interp_box = RoundedRectangle(
            corner_radius=0.12,
            width=5.5,
            height=0.9,
            stroke_color="#10B981",
            stroke_width=1.5,
            fill_color="#064E3B",
            fill_opacity=0.9
        ).move_to(np.array([math_x, -0.7, 0]))

        t_line1 = Text("Positive Slope  ->  Increasing y_hat increases Loss", font_size=11, color="#A7F3D0")
        t_line2 = Text("Network must nudge y_hat in the negative direction!", font_size=11, color=WHITE, weight=BOLD)
        interp_content = VGroup(t_line1, t_line2).arrange(DOWN, buff=0.1).move_to(interp_box.get_center())
        interp_group = VGroup(interp_box, interp_content)

        self.play(
            Create(push_arrow),
            Write(push_lbl),
            FadeIn(interp_group, shift=UP * 0.15),
            run_time=2.2
        )
        self.wait(5.8)

        # -------------------------------------------------------------
        # 7. The Seed of the Entire Backward Pass [29.8 - 48.43s]
        # -------------------------------------------------------------
        seed_pill = RoundedRectangle(
            corner_radius=0.12,
            width=5.5,
            height=0.9,
            stroke_color="#F59E0B",
            stroke_width=2.0,
            fill_color="#451A03",
            fill_opacity=0.92
        ).next_to(interp_box, DOWN, buff=0.28)

        seed_title = Text("THE SEED OF BACKPROPAGATION", font_size=12, color="#FCD34D", weight=BOLD)
        seed_desc = Text("Every weight update in the network stems from this single scalar", font_size=10, color="#FDE68A")
        seed_content = VGroup(seed_title, seed_desc).arrange(DOWN, buff=0.1).move_to(seed_pill.get_center())
        seed_group = VGroup(seed_pill, seed_content)

        # Luminous expanding pulse from the operating point
        pulse_ring = SurroundingRectangle(op_dot, color=YELLOW, buff=0.12, corner_radius=0.1)

        self.play(
            FadeIn(seed_group, shift=UP * 0.15),
            Indicate(eq_eval, color="#FBBF24", scale_factor=1.08),
            run_time=2.0
        )
        self.add(pulse_ring)
        self.play(
            pulse_ring.animate.scale(5.5).set_stroke(opacity=0.0),
            Indicate(seed_pill, color="#FBBF24"),
            run_time=2.2,
            rate_func=rate_functions.ease_out_quad
        )
        self.remove(pulse_ring)
        self.wait(7.23)