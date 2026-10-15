from manim import *
import numpy as np

class Scene06(Scene):
    def construct(self):
        self.camera.background_color = "#080B14"

        # -------------------------------------------------------------
        # 1. Title Banner [0.0 - 1.0s]
        # -------------------------------------------------------------
        title = Text("Backpropagation Through Hidden Layers: The Backward Recurrence", font_size=22, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        title_line = Line(LEFT * 5.8, RIGHT * 5.8, stroke_width=1.5, stroke_color="#A855F7").next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN * 0.2), Create(title_line), run_time=1.0)

        # -------------------------------------------------------------
        # 2. Complete Network Architecture (Shifted Safely to Left Stage)
        # -------------------------------------------------------------
        inp_pos = [np.array([-5.8, 1.0, 0]), np.array([-5.8, -1.0, 0])]
        hid_pos = [np.array([-4.0, 1.4, 0]), np.array([-4.0, 0.0, 0]), np.array([-4.0, -1.4, 0])]
        out_pos = np.array([-2.2, 0.0, 0])

        def make_node(pos, color, fill_c, label_tex, r=0.28):
            glow = Circle(radius=r * 1.4, stroke_opacity=0, fill_color=color, fill_opacity=0.15).move_to(pos)
            core = Circle(radius=r, color=color, stroke_width=2.2, fill_color=fill_c, fill_opacity=0.45).move_to(pos)
            lbl = MathTex(label_tex, font_size=15, color=WHITE).move_to(pos)
            return VGroup(glow, core, lbl)

        in_nodes = VGroup(*[make_node(p, "#38BDF8", "#0284C7", f"x_{i+1}") for i, p in enumerate(inp_pos)])
        hid_nodes = VGroup(*[make_node(p, "#C084FC", "#7E22CE", f"h_{i+1}") for i, p in enumerate(hid_pos)])
        out_node = make_node(out_pos, "#34D399", "#059669", r"\hat{y}", r=0.32)

        edges_w1 = VGroup()
        for i_n in in_nodes:
            for h_n in hid_nodes:
                edges_w1.add(Line(i_n[1].get_right(), h_n[1].get_left(), stroke_width=1.6, stroke_color="#334155"))

        edges_w2 = VGroup()
        for h_n in hid_nodes:
            edges_w2.add(Line(h_n[1].get_right(), out_node[1].get_left(), stroke_width=2.0, stroke_color="#334155"))

        lbl_in = Text("Inputs", font_size=11, color="#94A3B8").next_to(in_nodes[0], UP, buff=0.3)
        lbl_hid = Text("Hidden Layer", font_size=11, color="#94A3B8").next_to(hid_nodes[0], UP, buff=0.3)
        lbl_out = Text("Output", font_size=11, color="#94A3B8").next_to(out_node, UP, buff=0.75)

        net_group = VGroup(edges_w1, edges_w2, in_nodes, hid_nodes, out_node, lbl_in, lbl_hid, lbl_out)

        # -------------------------------------------------------------
        # 3. Floating Recurrence Typography (Right Stage) [1.0 - 7.5s]
        # -------------------------------------------------------------
        math_x = 2.4

        sub_title = Text("1. Proportional Error Attribution", font_size=13, weight=BOLD, color="#FCD34D")
        sub_title.move_to(np.array([math_x, 2.0, 0])).align_to(np.array([0.5, 0, 0]), LEFT)

        self.play(
            FadeIn(net_group, lag_ratio=0.06),
            Write(sub_title),
            run_time=2.2
        )
        self.wait(4.3)

        # -------------------------------------------------------------
        # 4. Error Flows Backward: W2 -> Hidden Layer [7.5 - 14.0s]
        # -------------------------------------------------------------
        delta_out_halo = Circle(radius=0.48, stroke_color="#F59E0B", stroke_width=2.2, fill_color="#F59E0B", fill_opacity=0.25).move_to(out_pos)
        self.play(FadeIn(delta_out_halo), Indicate(out_node[1], color="#F59E0B"), run_time=1.5)

        rev_w2_arrows = VGroup(*[
            Arrow(out_pos, h_p, buff=0.32, color="#F59E0B", stroke_width=2.6, tip_length=0.18)
            for h_p in hid_pos
        ])

        self.play(
            AnimationGroup(*[GrowArrow(a) for a in rev_w2_arrows], lag_ratio=0.15),
            run_time=2.0
        )
        self.wait(3.0)

        # -------------------------------------------------------------
        # 5. Scalar Hidden Delta Formulation [14.0 - 28.5s]
        # -------------------------------------------------------------
        scalar_eq = MathTex(
            r"\delta_j^{(1)} = \left( \sum_{k} W_{kj}^{(2)} \delta_k^{(2)} \right) \cdot \sigma^{\prime}(z_{1,j})",
            font_size=18,
            color=WHITE
        ).next_to(sub_title, DOWN, buff=0.22).align_to(sub_title, LEFT)
        scalar_eq.set_color_by_tex(r"\delta_j^{(1)}", "#C084FC")
        scalar_eq.set_color_by_tex(r"\sigma^{\prime}", "#38BDF8")

        self.play(Write(scalar_eq), run_time=2.0)

        for i, h_n in enumerate(hid_nodes):
            self.play(
                Indicate(h_n[1], color="#C084FC", scale_factor=1.2),
                Indicate(rev_w2_arrows[i], color="#FDE68A", scale_factor=1.1),
                run_time=1.8
            )

        # Fade out yellow arrows cleanly to eliminate screen clutter before next section
        self.play(FadeOut(rev_w2_arrows), run_time=1.0)
        self.wait(6.1)

        # -------------------------------------------------------------
        # 6. Vectorized Backward Recurrence [28.5 - 42.5s]
        # -------------------------------------------------------------
        sub_vec = Text("2. Vectorized Matrix Transpose Recurrence", font_size=13, weight=BOLD, color="#34D399")
        sub_vec.next_to(scalar_eq, DOWN, buff=0.32).align_to(sub_title, LEFT)

        vec_eq = MathTex(
            r"\boldsymbol{\delta}^{(l)} = \left( (W^{(l+1)})^T \boldsymbol{\delta}^{(l+1)} \right) \odot \sigma^{\prime}(\mathbf{z}^{(l)})",
            font_size=18,
            color=WHITE
        ).next_to(sub_vec, DOWN, buff=0.2).align_to(sub_title, LEFT)
        vec_eq.set_color_by_tex(r"\boldsymbol{\delta}^{(l)}", "#C084FC")
        vec_eq.set_color_by_tex(r"(W^{(l+1)})^T", "#FCD34D")
        vec_eq.set_color_by_tex(r"\odot", "#34D399")
        vec_eq.set_color_by_tex(r"\sigma^{\prime}", "#38BDF8")

        note_box = RoundedRectangle(
            corner_radius=0.1,
            width=5.9,
            height=0.72,
            stroke_color="#10B981",
            stroke_width=1.2,
            fill_color="#064E3B",
            fill_opacity=0.85
        ).next_to(vec_eq, DOWN, buff=0.2).align_to(sub_title, LEFT)

        note_l1 = Text("• W^T flips forward mapping to route error backwards", font_size=10, color="#A7F3D0")
        note_l2 = Text("• ⊙ (Hadamard) scales by local derivative gate", font_size=10, color="#A7F3D0")
        note_content = VGroup(note_l1, note_l2).arrange(DOWN, buff=0.08, aligned_edge=LEFT).move_to(note_box.get_center())
        note_group = VGroup(note_box, note_content)

        self.play(Write(sub_vec), run_time=1.2)
        self.play(Write(vec_eq), run_time=1.8)
        self.play(
            FadeIn(note_group),
            Indicate(vec_eq, color="#FCD34D", scale_factor=1.06),
            run_time=2.2
        )
        self.wait(8.8)

        # -------------------------------------------------------------
        # 7. Arbitrary Depth Propagation & Hidden Gradients [42.5 - 56.77s]
        # -------------------------------------------------------------
        grad_w1_eq = MathTex(
            r"\frac{\partial L}{\partial W_1} = \boldsymbol{\delta}^{(1)} \mathbf{x}^T \quad \iff \quad \frac{\partial L}{\partial W_{ij}^{(1)}} = \delta_i^{(1)} x_j",
            font_size=16,
            color="#38BDF8"
        ).next_to(note_box, DOWN, buff=0.22).align_to(sub_title, LEFT)

        rev_w1_arrows = VGroup(*[
            Arrow(h_p, i_p, buff=0.32, color="#38BDF8", stroke_width=1.8, tip_length=0.14)
            for i_p in inp_pos
            for h_p in hid_pos
        ])

        self.play(
            Write(grad_w1_eq),
            AnimationGroup(*[GrowArrow(a) for a in rev_w1_arrows], lag_ratio=0.05),
            run_time=2.4
        )

        # Dynamic cascade pulses through the entire network
        self.play(
            AnimationGroup(
                Indicate(out_node[1], color="#F59E0B"),
                *[Indicate(h[1], color="#C084FC") for h in hid_nodes],
                *[Indicate(i[1], color="#38BDF8") for i in in_nodes],
                lag_ratio=0.15
            ),
            FadeOut(rev_w1_arrows),
            run_time=2.4
        )
        self.wait(9.47)