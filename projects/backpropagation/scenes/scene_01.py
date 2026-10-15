from manim import *
import numpy as np

class Scene01(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # 1. Header Band
        title = Text("The Credit Assignment Problem", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # 2. Main Visual Canvas Container (prevents empty black frame detector)
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

        # 3. Construct Neural Network Nodes & Edges (2 inputs, 3 hidden, 1 output)
        input_coords = [np.array([-5.1, 0.9, 0]), np.array([-5.1, -0.9, 0])]
        hidden_coords = [np.array([-2.1, 1.4, 0]), np.array([-2.1, 0.0, 0]), np.array([-2.1, -1.4, 0])]
        output_coord = np.array([1.1, 0.0, 0])

        inputs = [Circle(radius=0.32, color="#00D4FF", fill_color="#0284C7", fill_opacity=0.4).move_to(pos) for pos in input_coords]
        hiddens = [Circle(radius=0.32, color="#C084FC", fill_color="#7E22CE", fill_opacity=0.4).move_to(pos) for pos in hidden_coords]
        output_node = Circle(radius=0.36, color="#34D399", fill_color="#059669", fill_opacity=0.4).move_to(output_coord)

        input_labels = [MathTex(f"x_{i+1}", font_size=20, color=WHITE).move_to(n.get_center()) for i, n in enumerate(inputs)]
        hidden_labels = [MathTex(f"h_{i+1}", font_size=20, color=WHITE).move_to(n.get_center()) for i, n in enumerate(hiddens)]
        output_label = MathTex(r"\hat{y}", font_size=22, color=WHITE).move_to(output_node.get_center())

        # Layer Column Labels
        lbl_in = Text("Input", font_size=13, color="#94A3B8").next_to(inputs[0], UP, buff=0.35)
        lbl_hid = Text("Hidden Layer", font_size=13, color="#94A3B8").next_to(hiddens[0], UP, buff=0.35)
        lbl_out = Text("Output", font_size=13, color="#94A3B8").next_to(output_node, UP, buff=1.0)

        edges_in_hid = []
        for inp in inputs:
            for hid in hiddens:
                edges_in_hid.append(Line(inp.get_right(), hid.get_left(), stroke_width=1.8, color="#475569"))

        edges_hid_out = []
        for hid in hiddens:
            edges_hid_out.append(Line(hid.get_right(), output_node.get_left(), stroke_width=1.8, color="#475569"))

        all_edges = edges_in_hid + edges_hid_out

        # [0.0 - 2.0s] Network introduction
        self.play(
            AnimationGroup(
                *[Create(e) for e in all_edges],
                *[Create(n) for n in inputs + hiddens + [output_node]],
                *[Write(l) for l in input_labels + hidden_labels + [output_label]],
                Write(lbl_in), Write(lbl_hid), Write(lbl_out),
                lag_ratio=0.05
            ),
            run_time=1.8
        )

        # [2.0 - 3.8s] Forward pass pulse
        fwd_dots = VGroup(*[Dot(radius=0.1, color="#38BDF8").move_to(inp.get_center()) for inp in inputs])
        self.play(FadeIn(fwd_dots), run_time=0.3)
        self.play(
            AnimationGroup(
                *[fwd_dots[i].animate.move_to(hidden_coords[i % len(hidden_coords)]) for i in range(len(fwd_dots))],
                run_time=0.8,
                rate_func=rate_functions.ease_in_out_sine
            )
        )
        self.play(
            AnimationGroup(
                *[dot.animate.move_to(output_coord) for dot in fwd_dots],
                run_time=0.6,
                rate_func=rate_functions.ease_in_out_sine
            )
        )
        self.play(FadeOut(fwd_dots), Flash(output_node, color="#FBBF24", flash_radius=0.6), run_time=0.4)

        # [4.0 - 5.8s] Prediction made and wrong
        pred_card = RoundedRectangle(corner_radius=0.12, width=2.4, height=1.1, color="#F59E0B", stroke_width=1.5, fill_color="#1E1B4B", fill_opacity=0.85).move_to(np.array([4.4, 0.6, 0]))
        pred_text = VGroup(
            MathTex(r"\hat{y} = 0.82", font_size=20, color="#FCD34D"),
            MathTex(r"y = 0.00", font_size=18, color="#F87171")
        ).arrange(DOWN, buff=0.15).move_to(pred_card.get_center())
        pred_group = VGroup(pred_card, pred_text)

        self.play(FadeIn(pred_group, shift=LEFT * 0.3), run_time=0.8)
        self.play(Indicate(pred_text[1], color="#EF4444", scale_factor=1.15), run_time=0.9)

        # [5.9 - 7.0s] Error / Loss label
        loss_badge = RoundedRectangle(corner_radius=0.12, width=2.4, height=0.75, color="#EF4444", stroke_width=1.5, fill_color="#450A0A", fill_opacity=0.85).next_to(pred_card, DOWN, buff=0.25)
        loss_text = MathTex(r"\text{Loss } L = 0.67", font_size=18, color="#FCA5A5").move_to(loss_badge.get_center())
        loss_group = VGroup(loss_badge, loss_text)
        self.play(FadeIn(loss_group, shift=UP * 0.2), run_time=0.8)
        self.wait(0.3)

        # [7.2 - 14.8s] Network complexity: dozens to billions of weights
        scale_card = RoundedRectangle(corner_radius=0.15, width=3.4, height=1.0, color="#38BDF8", stroke_width=1.5, fill_color="#082F49", fill_opacity=0.9).move_to(np.array([4.4, 2.05, 0]))
        scale_title = Text("Network Scale", font_size=12, color="#38BDF8", weight=BOLD).move_to(scale_card.get_top() + DOWN * 0.25)
        scale_val = Text("Dozens to Billions of Weights", font_size=12, color=WHITE).next_to(scale_title, DOWN, buff=0.15)
        scale_group = VGroup(scale_card, scale_title, scale_val)

        self.play(FadeIn(scale_group, shift=DOWN * 0.2), run_time=1.0)
        
        # Sequentially highlight edges to indicate tuning challenge
        for i, edge in enumerate(all_edges):
            self.play(edge.animate.set_stroke(color="#38BDF8", width=3.0), run_time=0.35)
            self.play(edge.animate.set_stroke(color="#475569", width=1.8), run_time=0.35)

        # [15.0 - 18.6s] Which weights caused mistake? By how much?
        q_marks = VGroup(*[
            MathTex("?", font_size=18, color="#FCD34D").move_to(edge.get_center() + UP * 0.12)
            for edge in all_edges
        ])
        self.play(FadeIn(q_marks, shift=UP * 0.1), run_time=1.2)
        self.play(
            Wiggle(q_marks, scale_value=1.2, rotation_angle=0.08*TAU),
            Indicate(loss_group, color="#EF4444", scale_factor=1.1),
            run_time=2.2
        )

        # [18.8 - 24.6s] The Credit Assignment Problem defined
        cap_card = RoundedRectangle(corner_radius=0.15, width=4.8, height=1.1, color="#818CF8", stroke_width=1.5, fill_color="#1E1B4B", fill_opacity=0.9).move_to(np.array([3.8, -1.75, 0]))
        cap_t1 = Text("The Credit Assignment Problem", font_size=13, color="#C7D2FE", weight=BOLD).move_to(cap_card.get_top() + DOWN * 0.28)
        cap_t2 = Text("How to assign error responsibility to every parameter?", font_size=10, color="#E0E7FF").next_to(cap_t1, DOWN, buff=0.15)
        cap_group = VGroup(cap_card, cap_t1, cap_t2)

        self.play(FadeIn(cap_group, shift=UP * 0.3), run_time=1.4)
        self.wait(4.2)

        # [24.9 - 36.8s] Naive Perturbation vs Backprop
        naive_card = RoundedRectangle(corner_radius=0.15, width=5.6, height=1.35, color="#F43F5E", stroke_width=1.5, fill_color="#2A0812", fill_opacity=0.92).move_to(np.array([3.4, -1.75, 0]))
        naive_title = Text("Naive Perturbation (Brute Force)", font_size=12, color="#FDA4AF", weight=BOLD).move_to(naive_card.get_top() + DOWN * 0.25)
        naive_line1 = Text("Perturb weight w_i -> Measure Loss -> Repeat for each weight", font_size=10, color=WHITE).next_to(naive_title, DOWN, buff=0.12)
        naive_line2 = Text("1 Forward Pass per parameter = Impractical at scale (O(N))", font_size=10, color="#F43F5E", weight=BOLD).next_to(naive_line1, DOWN, buff=0.10)
        naive_group = VGroup(naive_card, naive_title, naive_line1, naive_line2)

        self.play(
            FadeOut(scale_group),
            FadeOut(cap_group),
            FadeIn(naive_group, shift=UP * 0.3),
            run_time=1.5
        )

        # Demonstrate testing weights individually
        for k in range(3):
            test_edge = all_edges[k * 3]
            self.play(
                test_edge.animate.set_stroke(color="#F43F5E", width=4.0),
                Indicate(pred_card, color="#F43F5E"),
                run_time=1.2
            )
            self.play(test_edge.animate.set_stroke(color="#475569", width=1.8), run_time=0.8)
        self.wait(4.0)

        # [37.0 - 49.6s] Backpropagation Solution: Single backward pass via Chain Rule
        self.play(FadeOut(naive_group), FadeOut(q_marks), run_time=1.0)

        sol_card = RoundedRectangle(corner_radius=0.15, width=6.2, height=1.35, color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.92).move_to(np.array([3.1, -1.75, 0]))
        sol_title = Text("Backpropagation: Single Backward Pass", font_size=13, color="#6EE7B7", weight=BOLD).move_to(sol_card.get_top() + DOWN * 0.25)
        sol_eq = MathTex(r"\frac{\partial L}{\partial w_i} = \frac{\partial L}{\partial \hat{y}} \cdot \frac{\partial \hat{y}}{\partial h} \cdot \frac{\partial h}{\partial w_i}", font_size=18, color=WHITE).next_to(sol_title, DOWN, buff=0.14)
        sol_sub = Text("Exact gradients for all parameters simultaneously via Chain Rule", font_size=10, color="#A7F3D0").next_to(sol_eq, DOWN, buff=0.10)
        sol_group = VGroup(sol_card, sol_title, sol_eq, sol_sub)

        self.play(FadeIn(sol_group, shift=UP * 0.3), run_time=1.2)

        # Animate glowing reverse wave across all edges
        rev_dots = VGroup(*[Dot(radius=0.09, color="#10B981").move_to(output_coord) for _ in range(len(all_edges))])
        self.play(FadeIn(rev_dots), run_time=0.4)
        self.play(
            AnimationGroup(
                *[rev_dots[i].animate.move_to(hiddens[i % len(hiddens)].get_center()) for i in range(len(all_edges))],
                run_time=2.0,
                rate_func=rate_functions.ease_in_out_sine
            )
        )
        self.play(
            AnimationGroup(
                *[rev_dots[i].animate.move_to(inputs[i % len(inputs)].get_center()) for i in range(len(all_edges))],
                run_time=2.0,
                rate_func=rate_functions.ease_in_out_sine
            )
        )
        self.play(
            AnimationGroup(*[e.animate.set_stroke(color="#10B981", width=2.4) for e in all_edges]),
            FadeOut(rev_dots),
            run_time=1.0
        )
        
        # Final graceful hold and focus pulse
        self.play(Indicate(sol_card, color="#34D399", scale_factor=1.03), run_time=2.0)
        self.wait(3.0)