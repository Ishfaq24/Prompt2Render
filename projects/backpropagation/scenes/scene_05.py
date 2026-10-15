from manim import *
import numpy as np

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        y_target = 0.0
        y_hat = 0.576
        hidden_activations = np.array([0.465, 0.570, 0.557])
        sigmoid_derivative = y_hat * (1.0 - y_hat)
        delta_out = (y_hat - y_target) * sigmoid_derivative
        weight_grads = delta_out * hidden_activations

        # -------------------------------------------------------------
        # 1. Title Banner [0.0 - 1.0s]
        # -------------------------------------------------------------
        title = Text("Backpropagation Through the Output Layer", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        title_line = Line(LEFT * 6.2, RIGHT * 6.2, stroke_width=1.2, stroke_color="#334155").next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN * 0.2), Create(title_line), run_time=1.0)

        # -------------------------------------------------------------
        # 2. Output & Hidden Layer Architecture (Left Stage)
        # -------------------------------------------------------------
        hid_pos = [np.array([-5.1, 1.2, 0]), np.array([-5.1, 0.0, 0]), np.array([-5.1, -1.2, 0])]
        out_pos = np.array([-2.4, 0.0, 0])

        def make_node(pos, color, fill_c, label_tex, r=0.3):
            glow = Circle(radius=r * 1.4, stroke_opacity=0, fill_color=color, fill_opacity=0.15).move_to(pos)
            core = Circle(radius=r, color=color, stroke_width=2.2, fill_color=fill_c, fill_opacity=0.45).move_to(pos)
            lbl = MathTex(label_tex, font_size=16, color=WHITE).move_to(pos)
            return VGroup(glow, core, lbl)

        hid_nodes = VGroup(*[make_node(p, "#C084FC", "#7E22CE", f"a_{{1,{i+1}}}") for i, p in enumerate(hid_pos)])
        out_node = make_node(out_pos, "#34D399", "#059669", r"\hat{y}", r=0.35)

        edges_w2 = VGroup()
        w_labels = VGroup()
        for i, h_n in enumerate(hid_nodes):
            edge = Line(h_n[1].get_right(), out_node[1].get_left(), stroke_width=2.2, stroke_color="#475569")
            w_lbl = MathTex(f"W_{{2,{i+1}}}", font_size=13, color="#FCD34D").move_to(edge.get_center() + UP * 0.2)
            edges_w2.add(edge)
            w_labels.add(w_lbl)

        lbl_hid_col = Text("HIDDEN LAYER", font_size=11, weight=BOLD, color="#C084FC").next_to(hid_nodes[0], UP, buff=0.35)
        lbl_out_col = Text("OUTPUT", font_size=11, weight=BOLD, color="#34D399").next_to(out_node, UP, buff=0.6)

        net_group = VGroup(edges_w2, w_labels, hid_nodes, out_node, lbl_hid_col, lbl_out_col)

        # -------------------------------------------------------------
        # 3. Mathematical Foundations (Right Stage) [1.0 - 6.0s]
        # -------------------------------------------------------------
        math_x = 2.85

        delta_def = MathTex(
            r"\delta_{\text{out}} \equiv \frac{\partial L}{\partial z_2} = \frac{\partial L}{\partial \hat{y}} \cdot \frac{\partial \hat{y}}{\partial z_2}",
            font_size=18,
            color=WHITE
        ).move_to(np.array([math_x, 2.05, 0]))
        delta_def.set_color_by_tex(r"\delta_{\text{out}}", "#FCD34D")

        self.play(FadeIn(net_group, lag_ratio=0.08), run_time=2.0)
        self.play(Write(delta_def), run_time=1.8)
        self.wait(1.2)

        # -------------------------------------------------------------
        # 4. Sigmoid Derivative [6.0 - 16.0s]
        # -------------------------------------------------------------
        sig_deriv_eq = MathTex(
            r"\frac{\partial \hat{y}}{\partial z_2} = \sigma^{\prime}(z_2) = \hat{y}(1 - \hat{y})",
            font_size=17,
            color="#C084FC"
        ).next_to(delta_def, DOWN, buff=0.22).align_to(delta_def, LEFT)

        sig_val_eq = MathTex(
            rf"\sigma^{{\prime}}(z_2) = {y_hat:.3f} \times (1 - {y_hat:.3f}) = {sigmoid_derivative:.3f}",
            font_size=16,
            color="#E9D5FF"
        ).next_to(sig_deriv_eq, DOWN, buff=0.16).align_to(delta_def, LEFT)

        self.play(Write(sig_deriv_eq), run_time=2.0)
        self.play(
            Flash(out_node[1], color="#C084FC", flash_radius=0.48),
            Write(sig_val_eq),
            run_time=2.0
        )
        self.wait(6.0)

        # -------------------------------------------------------------
        # 5. Output Delta Evaluation [16.0 - 24.0s]
        # -------------------------------------------------------------
        delta_eval = MathTex(
            rf"\delta_{{\text{{out}}}} = ({y_hat:.3f} - {y_target:.0f}) \times {sigmoid_derivative:.3f} \approx {delta_out:.3f}",
            font_size=17,
            color="#FCD34D"
        ).next_to(sig_val_eq, DOWN, buff=0.22).align_to(delta_def, LEFT)

        delta_halo = Circle(radius=0.52, stroke_color="#FCD34D", stroke_width=2.2, fill_color="#FCD34D", fill_opacity=0.2).move_to(out_pos)

        self.play(Write(delta_eval), run_time=1.8)
        self.play(
            FadeIn(delta_halo),
            Indicate(out_node[1], color="#FCD34D", scale_factor=1.18),
            run_time=1.8
        )
        self.wait(4.4)

        # -------------------------------------------------------------
        # 6. Physical Meaning Card [24.0 - 32.0s]
        # -------------------------------------------------------------
        sens_badge = RoundedRectangle(
            corner_radius=0.1,
            width=5.9,
            height=0.58,
            stroke_color="#10B981",
            stroke_width=1.5,
            fill_color="#064E3B",
            fill_opacity=0.88
        ).next_to(delta_eval, DOWN, buff=0.20).align_to(delta_def, LEFT)

        sens_text = Text("delta_out measures loss sensitivity to pre-activation z_2", font_size=11, color="#A7F3D0", weight=BOLD).move_to(sens_badge.get_center())
        sens_group = VGroup(sens_badge, sens_text)

        self.play(FadeIn(sens_group, shift=UP * 0.1), run_time=1.4)

        pulse_c = Circle(radius=0.35, stroke_color="#10B981", stroke_width=2.0).move_to(out_pos)
        self.play(
            pulse_c.animate.scale(2.4).set_stroke(opacity=0.0),
            run_time=1.6,
            rate_func=rate_functions.ease_out_quad
        )
        self.wait(5.0)

        # -------------------------------------------------------------
        # 7. Weight Gradients via Output Delta [32.0 - 42.5s]
        # -------------------------------------------------------------
        grad_formula = MathTex(
            r"\frac{\partial L}{\partial W_{2,j}} = \delta_{\text{out}} \cdot a_{1,j}",
            font_size=18,
            color="#34D399"
        ).next_to(sens_group, DOWN, buff=0.20).align_to(delta_def, LEFT)

        rev_pulses = VGroup(*[
            Arrow(out_pos, h_p, buff=0.38, color="#34D399", stroke_width=2.8, tip_length=0.18)
            for h_p in hid_pos
        ])

        self.play(
            Write(grad_formula),
            AnimationGroup(*[GrowArrow(a) for a in rev_pulses], lag_ratio=0.15),
            run_time=2.2
        )
        self.play(
            AnimationGroup(*[Indicate(h[1], color="#34D399", scale_factor=1.15) for h in hid_nodes], lag_ratio=0.1),
            FadeOut(rev_pulses),
            run_time=1.8
        )
        self.wait(6.5)

        # -------------------------------------------------------------
        # 8. Weight Update Rule [42.5 - 51.89s]
        # -------------------------------------------------------------
        update_pill = RoundedRectangle(
            corner_radius=0.12,
            width=5.9,
            height=0.72,
            stroke_color="#38BDF8",
            stroke_width=1.6,
            fill_color="#082F49",
            fill_opacity=0.92
        ).next_to(grad_formula, DOWN, buff=0.18).align_to(delta_def, LEFT)

        update_tex = MathTex(
            r"W_2^{\mathrm{new}} \leftarrow W_2^{\mathrm{old}} - \eta\,\nabla_{W_2}L",
            font_size=17,
            color="#E0F2FE"
        ).move_to(update_pill.get_center())
        update_group = VGroup(update_pill, update_tex)

        self.play(FadeIn(update_group, shift=UP * 0.12), run_time=1.6)

        self.play(
            edges_w2.animate.set_stroke(color="#38BDF8", width=3.0),
            run_time=1.5
        )
        self.play(
            edges_w2.animate.set_stroke(color="#475569", width=2.2),
            Indicate(update_pill, color="#38BDF8"),
            run_time=1.8
        )
        self.wait(5.49)