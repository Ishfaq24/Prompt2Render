from manim import *
import numpy as np

class Scene09(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # 1. Title Band
        title = Text("Modern Breakthroughs: Overcoming Vanishing Gradients", font_size=25, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # 2. Main Stage Container Card
        stage_bg = RoundedRectangle(
            corner_radius=0.2,
            width=13.0,
            height=5.2,
            stroke_color="#1E293B",
            stroke_width=1.5,
            fill_color="#0F172A",
            fill_opacity=0.6
        ).shift(UP * 0.1)
        self.play(FadeIn(stage_bg), run_time=0.8)

        # [0.0s - 3.2s] Intro Pill: Three Innovations
        intro_pill = RoundedRectangle(corner_radius=0.15, width=9.2, height=0.6, color="#38BDF8", stroke_width=1.5, fill_color="#082F49", fill_opacity=0.9).move_to(DOWN * 1.8)
        intro_text = Text("Three Architectural Innovations Broke Through The Vanishing Gradient Wall", font_size=12, color="#BAE6FD", weight=BOLD).move_to(intro_pill.get_center())
        intro_group = VGroup(intro_pill, intro_text)

        self.play(FadeIn(intro_group, shift=UP * 0.15), run_time=1.0)
        self.wait(0.4)

        # =========================================================================
        # ACT 1: ReLU Activation (3.2s - 24.8s)
        # =========================================================================
        self.play(FadeOut(intro_group), run_time=0.6)

        # Left Side: ReLU Coordinates & Plot
        axes_relu = Axes(
            x_range=[-3.0, 3.0, 1.0],
            y_range=[-0.5, 3.0, 1.0],
            x_length=4.5,
            y_length=2.8,
            axis_config={"color": "#64748B", "include_numbers": True, "font_size": 11}
        ).move_to(LEFT * 3.6 + UP * 0.6)

        relu_curve = axes_relu.plot(lambda x: max(0.0, x), color="#10B981", stroke_width=3.5)
        relu_lbl = MathTex(r"\text{ReLU}(z) = \max(0, z)", font_size=15, color="#6EE7B7").next_to(axes_relu, UP, buff=0.15)

        # Derivative curve (piecewise: 0 for z<0, 1 for z>0)
        deriv_neg = axes_relu.plot(lambda x: 0.0, x_range=[-3.0, 0.0], color="#F43F5E", stroke_width=3.0)
        deriv_pos = axes_relu.plot(lambda x: 1.0, x_range=[0.0, 3.0], color="#F59E0B", stroke_width=3.0)
        deriv_lbl = MathTex(r"\text{ReLU}^{\prime}(z) = 1 \quad (z > 0)", font_size=15, color="#FDE68A").move_to(LEFT * 3.6 + DOWN * 1.2)

        relu_group = VGroup(axes_relu, relu_curve, relu_lbl)

        self.play(Create(axes_relu), Create(relu_curve), Write(relu_lbl), run_time=1.8)
        self.wait(1.2)

        # [11.8s - 15.8s] Derivative is exactly 1 for positive pre-activations
        self.play(Create(deriv_neg), Create(deriv_pos), Write(deriv_lbl), run_time=1.5)
        self.wait(3.8)

        # Right Side: Comparison Card (Sigmoid Shrinkage vs ReLU 1.0 Highway)
        chain_box = RoundedRectangle(
            corner_radius=0.15,
            width=5.5,
            height=3.4,
            stroke_color="#334155",
            stroke_width=1.5,
            fill_color="#1E293B",
            fill_opacity=0.85
        ).move_to(RIGHT * 3.4 + UP * 0.1)

        box_title = Text("1. Rectified Linear Unit (ReLU)", font_size=13, weight=BOLD, color="#6EE7B7").move_to(chain_box.get_top() + DOWN * 0.35)

        sig_line = MathTex(r"\text{Sigmoid: } 0.25 \times 0.25 \times \dots \to 0 \quad (\text{Vanishes})", font_size=13, color="#FDA4AF").move_to(chain_box.get_center() + UP * 0.4)
        relu_line = MathTex(r"\text{ReLU: } 1.0 \times 1.0 \times 1.0 = 1.0 \quad (\text{Sustained})", font_size=13, color="#6EE7B7").move_to(chain_box.get_center() + DOWN * 0.2)
        deep_line = Text("Enables Training Across Hundreds of Layers", font_size=11, color="#FDE68A", weight=BOLD).move_to(chain_box.get_bottom() + UP * 0.4)

        chain_group = VGroup(chain_box, box_title, sig_line, relu_line, deep_line)

        # [16.1s - 19.0s] Multiplying chain of ones does not shrink
        self.play(FadeIn(chain_group, shift=LEFT * 0.2), run_time=1.3)
        self.wait(2.0)

        # [19.3s - 24.6s] Deep networks enabled highlight
        self.play(Indicate(deep_line, color="#10B981", scale_factor=1.08), run_time=1.5)
        self.wait(4.2)

        # =========================================================================
        # ACT 2: Batch Normalization (24.8s - 38.6s)
        # =========================================================================
        act1_group = VGroup(relu_group, deriv_neg, deriv_pos, deriv_lbl, chain_group)
        self.play(FadeOut(act1_group), run_time=1.0)

        # BN Container & Equations
        bn_card = RoundedRectangle(
            corner_radius=0.18,
            width=11.6,
            height=3.8,
            stroke_color="#6366F1",
            stroke_width=1.5,
            fill_color="#1E1B4B",
            fill_opacity=0.75
        ).move_to(UP * 0.1)

        bn_title = Text("2. Batch Normalization: Stabilizing Layer Distributions", font_size=15, weight=BOLD, color="#A5B4FC").move_to(bn_card.get_top() + DOWN * 0.4)

        eq_mean = MathTex(r"\mu_{\mathcal{B}} = \frac{1}{m}\sum_{i=1}^m x_i, \quad \sigma_{\mathcal{B}}^2 = \frac{1}{m}\sum_{i=1}^m (x_i - \mu_{\mathcal{B}})^2", font_size=15, color=WHITE).move_to(bn_card.get_center() + UP * 0.5)
        eq_norm = MathTex(r"\hat{x}_i = \frac{x_i - \mu_{\mathcal{B}}}{\sqrt{\sigma_{\mathcal{B}}^2 + \epsilon}}, \quad y_i = \gamma \hat{x}_i + \beta", font_size=15, color="#FDE68A").move_to(bn_card.get_center() + DOWN * 0.2)

        bn_pill = RoundedRectangle(corner_radius=0.12, width=9.8, height=0.55, color="#10B981", stroke_width=1.2, fill_color="#064E3B", fill_opacity=0.9).move_to(bn_card.get_bottom() + UP * 0.55)
        bn_desc = Text("Centers Pre-Activations Near Zero Where Derivatives Are Non-Zero & Stabilizes Training", font_size=11, color="#A7F3D0", weight=BOLD).move_to(bn_pill.get_center())

        bn_group = VGroup(bn_card, bn_title, eq_mean, eq_norm, bn_pill, bn_desc)

        # [24.9s - 38.5s] Batch Normalization narration
        self.play(FadeIn(bn_card), Write(bn_title), run_time=1.5)
        self.wait(1.5)

        self.play(Write(eq_mean), Write(eq_norm), run_time=2.0)
        self.wait(3.0)

        self.play(FadeIn(bn_pill), Write(bn_desc), run_time=1.2)
        self.wait(4.6)

        # =========================================================================
        # ACT 3: Residual Skip Connections (ResNet) (38.6s - 58.6s)
        # =========================================================================
        self.play(FadeOut(bn_group), run_time=1.0)

        # ResNet Block Diagram
        res_card = RoundedRectangle(
            corner_radius=0.18,
            width=11.6,
            height=3.8,
            stroke_color="#EC4899",
            stroke_width=1.5,
            fill_color="#31102A",
            fill_opacity=0.7
        ).move_to(UP * 0.1)

        res_title = Text("3. Residual Skip Connections (ResNet): The Gradient Highway", font_size=14, weight=BOLD, color="#F472B6").move_to(res_card.get_top() + DOWN * 0.30)

        # Left diagram: Nodes & Highway shifted down slightly to provide breathing room for arc
        y_dia = -0.3
        node_in = Circle(radius=0.34, color="#38BDF8", fill_color="#0369A1", fill_opacity=0.85).move_to(LEFT * 5.0 + UP * y_dia)
        node_in_lbl = MathTex(r"x", font_size=16, color=WHITE).move_to(node_in.get_center())

        block_w = RoundedRectangle(corner_radius=0.1, width=2.2, height=1.2, color="#818CF8", fill_color="#312E81", fill_opacity=0.85).move_to(LEFT * 2.5 + UP * y_dia)
        block_w_lbl = Text("Weight Layers\n  F(x)", font_size=11, color=WHITE).move_to(block_w.get_center())

        node_sum = Circle(radius=0.34, color="#10B981", fill_color="#065F46", fill_opacity=0.85).move_to(LEFT * 0.1 + UP * y_dia)
        node_sum_lbl = MathTex(r"+", font_size=20, color=WHITE).move_to(node_sum.get_center())

        node_out = Circle(radius=0.34, color="#38BDF8", fill_color="#0369A1", fill_opacity=0.85).move_to(RIGHT * 1.8 + UP * y_dia)
        node_out_lbl = MathTex(r"y", font_size=16, color=WHITE).move_to(node_out.get_center())

        arr_f1 = Arrow(node_in.get_right(), block_w.get_left(), buff=0.1, color=WHITE, stroke_width=2.5, tip_length=0.15)
        arr_f2 = Arrow(block_w.get_right(), node_sum.get_left(), buff=0.1, color=WHITE, stroke_width=2.5, tip_length=0.15)
        arr_f3 = Arrow(node_sum.get_right(), node_out.get_left(), buff=0.1, color=WHITE, stroke_width=2.5, tip_length=0.15)

        # Skip Highway (bypassing block)
        skip_path = CurvedArrow(
            node_in.get_top() + UP * 0.08,
            node_sum.get_top() + UP * 0.08,
            angle=-TAU / 4.4,
            color="#F59E0B",
            stroke_width=3.2,
            tip_length=0.18
        )
        skip_lbl = Text("Identity Highway (+x)", font_size=10, color="#FDE68A", weight=BOLD).next_to(skip_path, UP, buff=0.08)

        # Gradient Formula Box on Right
        grad_box = RoundedRectangle(corner_radius=0.12, width=3.8, height=2.2, color="#F472B6", stroke_width=1.2, fill_color="#500724", fill_opacity=0.9).move_to(RIGHT * 4.0 + UP * 0.05)
        grad_title = Text("Backprop Gradient Flow", font_size=11, color="#FBCFE8", weight=BOLD).move_to(grad_box.get_top() + DOWN * 0.3)
        grad_eq = MathTex(r"\frac{\partial \mathcal{L}}{\partial x} = \frac{\partial \mathcal{L}}{\partial y}\left(\frac{\partial F}{\partial x} + \mathbf{1}\right)", font_size=14, color=WHITE).move_to(grad_box.get_center())
        highway_note = Text("+1 Term Passes 100% Gradient!", font_size=9.5, color="#FDE68A", weight=BOLD).move_to(grad_box.get_bottom() + UP * 0.3)
        grad_group = VGroup(grad_box, grad_title, grad_eq, highway_note)

        diagram_group = VGroup(
            res_card, res_title,
            node_in, node_in_lbl, block_w, block_w_lbl,
            node_sum, node_sum_lbl, node_out, node_out_lbl,
            arr_f1, arr_f2, arr_f3, skip_path, skip_lbl,
            grad_group
        )

        # [38.8s - 46.8s] Skip connections bypass weight computation
        self.play(FadeIn(res_card), Write(res_title), run_time=1.2)
        self.play(
            FadeIn(node_in), Write(node_in_lbl),
            FadeIn(block_w), Write(block_w_lbl),
            FadeIn(node_sum), Write(node_sum_lbl),
            FadeIn(node_out), Write(node_out_lbl),
            Create(arr_f1), Create(arr_f2), Create(arr_f3),
            Create(skip_path), Write(skip_lbl),
            run_time=2.2
        )
        self.wait(3.5)

        # [47.1s - 58.4s] Gradient flows through skip connection without multiplicative shrinkage
        self.play(FadeIn(grad_group, shift=LEFT * 0.2), run_time=1.5)
        self.wait(1.5)

        # Gradient Highway Pulse flowing backward along skip path!
        pulse = Dot(color="#FDE68A", radius=0.12).move_to(node_sum.get_top() + UP * 0.1)
        self.play(FadeIn(pulse), run_time=0.3)
        self.play(
            MoveAlongPath(pulse, skip_path),
            rate_func=lambda t: 1 - t,
            run_time=2.5
        )
        self.play(FadeOut(pulse), run_time=0.3)
        self.wait(4.5)

        # =========================================================================
        # ACT 4: Synthesis: 3 Innovations Unlock Deep Networks (58.7s - 65.01s)
        # =========================================================================
        # Do not fade out everything; transition into the grand synthesis banner safely!
        self.play(FadeOut(diagram_group), run_time=0.8)

        # Three pillar summary cards
        c_w, c_h = 3.6, 2.0
        p1 = RoundedRectangle(corner_radius=0.12, width=c_w, height=c_h, color="#10B981", stroke_width=1.5, fill_color="#064E3B", fill_opacity=0.85).move_to(LEFT * 4.0 + UP * 0.7)
        p1_t = Text("1. ReLU Activation", font_size=12, weight=BOLD, color="#6EE7B7").move_to(p1.get_top() + DOWN * 0.35)
        p1_d = Text("Derivative = 1.0\nNo exponential decay\nActive gradient flow", font_size=10, color=WHITE).move_to(p1.get_center() + DOWN * 0.15)
        card1 = VGroup(p1, p1_t, p1_d)

        p2 = RoundedRectangle(corner_radius=0.12, width=c_w, height=c_h, color="#6366F1", stroke_width=1.5, fill_color="#1E1B4B", fill_opacity=0.85).move_to(UP * 0.7)
        p2_t = Text("2. Batch Normalization", font_size=12, weight=BOLD, color="#A5B4FC").move_to(p2.get_top() + DOWN * 0.35)
        p2_d = Text("Standardized inputs\nCentered near zero\nStabilized dynamics", font_size=10, color=WHITE).move_to(p2.get_center() + DOWN * 0.15)
        card2 = VGroup(p2, p2_t, p2_d)

        p3 = RoundedRectangle(corner_radius=0.12, width=c_w, height=c_h, color="#EC4899", stroke_width=1.5, fill_color="#500724", fill_opacity=0.85).move_to(RIGHT * 4.0 + UP * 0.7)
        p3_t = Text("3. Residual Shortcuts", font_size=12, weight=BOLD, color="#F472B6").move_to(p3.get_top() + DOWN * 0.35)
        p3_d = Text("Identity path +1\nUnattenuated highway\nArbitrary network depth", font_size=10, color=WHITE).move_to(p3.get_center() + DOWN * 0.15)
        card3 = VGroup(p3, p3_t, p3_d)

        # Footer banner safely positioned above Y = -2.5
        footer_box = RoundedRectangle(corner_radius=0.15, width=11.6, height=0.7, color="#F59E0B", stroke_width=1.5, fill_color="#451A03", fill_opacity=0.9).move_to(DOWN * 1.6)
        footer_txt = Text("Result: Deep Networks (100+ Layers) Transitioned From Impossible To Routine", font_size=12, weight=BOLD, color="#FDE68A").move_to(footer_box.get_center())
        footer_group = VGroup(footer_box, footer_txt)

        self.play(
            FadeIn(card1, shift=UP * 0.2),
            FadeIn(card2, shift=UP * 0.2),
            FadeIn(card3, shift=UP * 0.2),
            FadeIn(footer_group, shift=UP * 0.2),
            run_time=1.5
        )

        # Keep active vitality until the exact section duration (65.01s)
        self.play(
            Indicate(card1, color="#34D399", scale_factor=1.03),
            Indicate(card2, color="#818CF8", scale_factor=1.03),
            Indicate(card3, color="#F472B6", scale_factor=1.03),
            run_time=2.0
        )
        self.wait(2.21)