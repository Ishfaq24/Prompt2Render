from manim import *
import numpy as np

class Scene03(Scene):
    def construct(self):
        config.background_color = "#080B14"

        # -------------------------------------------------------------
        # 1. Elegant Header (No bulky container cards)
        # -------------------------------------------------------------
        title = Text("Forward Pass Bookkeeping & Memory Cache", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        title_underline = Line(LEFT * 4.5, RIGHT * 4.5, stroke_width=1.5, stroke_color=BLUE_E).next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN * 0.2), Create(title_underline), run_time=1.0)

        # -------------------------------------------------------------
        # 2. Living Neural Network Layout (Left Stage)
        # -------------------------------------------------------------
        inp_pos = [np.array([-5.4, 0.85, 0]), np.array([-5.4, -0.85, 0])]
        hid_pos = [np.array([-2.7, 1.4, 0]), np.array([-2.7, 0.0, 0]), np.array([-2.7, -1.4, 0])]
        out_pos = np.array([0.0, 0.0, 0])

        # Node generator with soft glowing aura
        def make_node(pos, color, fill_c, label_tex, r=0.28):
            glow = Circle(radius=r * 1.5, stroke_opacity=0, fill_color=color, fill_opacity=0.12).move_to(pos)
            core = Circle(radius=r, color=color, stroke_width=2.2, fill_color=fill_c, fill_opacity=0.45).move_to(pos)
            lbl = MathTex(label_tex, font_size=16, color=WHITE).move_to(pos)
            return VGroup(glow, core, lbl)

        in_nodes = VGroup(*[make_node(p, "#38BDF8", "#0284C7", f"x_{i+1}") for i, p in enumerate(inp_pos)])
        hid_nodes = VGroup(*[make_node(p, "#C084FC", "#7E22CE", f"h_{i+1}") for i, p in enumerate(hid_pos)])
        out_node = make_node(out_pos, "#34D399", "#059669", r"\hat{y}", r=0.32)

        # Synaptic edges
        edges_w1 = VGroup()
        for i_n in in_nodes:
            for h_n in hid_nodes:
                edges_w1.add(Line(i_n[1].get_right(), h_n[1].get_left(), stroke_width=1.8, stroke_color="#334155"))

        edges_w2 = VGroup()
        for h_n in hid_nodes:
            edges_w2.add(Line(h_n[1].get_right(), out_node[1].get_left(), stroke_width=2.0, stroke_color="#334155"))

        # Layer Labels
        lbl_in = Text("Input x", font_size=12, color="#94A3B8").next_to(in_nodes[0], UP, buff=0.3)
        lbl_hid = Text("Hidden Layer", font_size=12, color="#94A3B8").next_to(hid_nodes[0], UP, buff=0.3)
        lbl_out = Text("Output", font_size=12, color="#94A3B8").next_to(out_node, UP, buff=1.0)

        # Input vector annotation
        x_vec_tex = MathTex(r"\mathbf{x} = \begin{bmatrix} 0.5 \\ 0.8 \end{bmatrix}", font_size=16, color="#7DD3FC").next_to(in_nodes, LEFT, buff=0.25)

        # -------------------------------------------------------------
        # 3. Activation Cache Registry Rack (Right Stage)
        # -------------------------------------------------------------
        rack_center = np.array([4.2, 0.0, 0])
        rack_box = RoundedRectangle(corner_radius=0.15, width=4.6, height=4.2, stroke_color="#6366F1", stroke_width=1.5, fill_color="#0F172A", fill_opacity=0.7).move_to(rack_center)
        rack_title = Text("ACTIVATION CACHE (RAM)", font_size=12, weight=BOLD, color="#A5B4FC").next_to(rack_box.get_top(), DOWN, buff=0.2)
        rack_sep = Line(rack_box.get_left() + RIGHT * 0.2, rack_box.get_right() + LEFT * 0.2, stroke_color="#4338CA", stroke_width=1.0).next_to(rack_title, DOWN, buff=0.12)

        # Registry slots
        slot_labels = [
            (r"\mathbf{z}^{(1)} \in \mathbb{R}^3", "Pre-activations"),
            (r"\mathbf{a}^{(1)} \in \mathbb{R}^3", "Hidden Activations"),
            (r"z^{(2)} \in \mathbb{R}", "Output Pre-act"),
            (r"\hat{y} \in \mathbb{R}", "Final Prediction")
        ]
        slots = VGroup()
        for i, (sym, desc) in enumerate(slot_labels):
            y_s = rack_center[1] + 1.0 - i * 0.72
            s_box = RoundedRectangle(corner_radius=0.08, width=4.1, height=0.55, stroke_color="#334155", stroke_width=1.0, fill_color="#1E293B", fill_opacity=0.6).move_to(np.array([rack_center[0], y_s, 0]))
            s_sym = MathTex(sym, font_size=14, color="#E2E8F0").move_to(s_box.get_left() + RIGHT * 0.8)
            s_val = Text(desc, font_size=10, color="#64748B").move_to(s_box.get_right() + LEFT * 0.9)
            slots.add(VGroup(s_box, s_sym, s_val))

        # [0.0 - 6.2s] Intro: Clean reveal of network and RAM cache
        self.play(
            AnimationGroup(
                Create(edges_w1), Create(edges_w2),
                FadeIn(in_nodes), FadeIn(hid_nodes), FadeIn(out_node),
                Write(lbl_in), Write(lbl_hid), Write(lbl_out),
                FadeIn(x_vec_tex),
                lag_ratio=0.08
            ),
            run_time=2.2
        )
        self.play(
            FadeIn(rack_box), Write(rack_title), Create(rack_sep),
            FadeIn(slots, lag_ratio=0.1),
            run_time=1.8
        )
        self.wait(2.2)

        # -------------------------------------------------------------
        # 4. Step 1: z1 = W1 * x (Matrix product) [6.2 - 14.5s]
        # -------------------------------------------------------------
        # Glowing pulses flowing down W1 synapses
        pulse_dots = VGroup(*[
            Dot(radius=0.08, color="#38BDF8").move_to(inp_pos[k % 2])
            for k in range(6)
        ])
        target_hid_pos = [hid_pos[0], hid_pos[1], hid_pos[2], hid_pos[0], hid_pos[1], hid_pos[2]]

        eq_z1 = MathTex(
            r"\mathbf{z}_1 = W_1 \mathbf{x} = [-0.14, \; 0.28, \; 0.23]^T",
            font_size=14,
            color="#FCD34D"
        ).move_to(np.array([-3.8, 2.65, 0]))

        self.play(
            FadeIn(pulse_dots),
            Write(eq_z1),
            edges_w1.animate.set_stroke(color="#38BDF8", width=2.4),
            run_time=1.4
        )
        self.play(
            AnimationGroup(*[
                pulse_dots[k].animate.move_to(target_hid_pos[k])
                for k in range(6)
            ], lag_ratio=0.05),
            run_time=1.2,
            rate_func=rate_functions.ease_in_out_sine
        )
        self.play(
            FadeOut(pulse_dots),
            edges_w1.animate.set_stroke(color="#334155", width=1.8),
            *[Indicate(h[1], color="#FCD34D") for h in hid_nodes],
            run_time=1.0
        )

        # Send z1 packet to cache slot 0
        z1_packet = MathTex(r"[-0.14, 0.28, 0.23]^T", font_size=12, color="#FCD34D").move_to(hid_pos[1])
        self.play(
            FadeOut(slots[0][2]),
            z1_packet.animate.move_to(slots[0][0].get_right() + LEFT * 0.9).scale(0.9),
            slots[0][0].animate.set_stroke(color="#FCD34D", width=1.8).set_fill(color="#451A03", opacity=0.8),
            run_time=1.6
        )
        self.wait(3.1)

        # -------------------------------------------------------------
        # 5. Step 2: a1 = sigma(z1) [14.5 - 20.8s]
        # -------------------------------------------------------------
        eq_a1 = MathTex(
            r"\mathbf{a}_1 = \sigma(\mathbf{z}_1) = [0.465, \; 0.569, \; 0.557]^T",
            font_size=14,
            color="#C084FC"
        ).move_to(np.array([-3.8, 2.25, 0]))

        self.play(
            Write(eq_a1),
            *[Flash(h[1], color="#C084FC", flash_radius=0.45) for h in hid_nodes],
            run_time=1.8
        )
        # Send a1 packet to cache slot 1
        a1_packet = MathTex(r"[0.465, 0.569, 0.557]^T", font_size=12, color="#C084FC").move_to(hid_pos[1])
        self.play(
            FadeOut(slots[1][2]),
            a1_packet.animate.move_to(slots[1][0].get_right() + LEFT * 0.9).scale(0.9),
            slots[1][0].animate.set_stroke(color="#C084FC", width=1.8).set_fill(color="#3B0764", opacity=0.8),
            run_time=1.6
        )
        self.wait(2.9)

        # -------------------------------------------------------------
        # 6. Step 3: z2 = W2 * a1 [20.8 - 27.3s]
        # -------------------------------------------------------------
        eq_z2 = MathTex(
            r"z_2 = W_2 \mathbf{a}_1 = 0.306",
            font_size=14,
            color="#38BDF8"
        ).move_to(np.array([-3.8, 1.85, 0]))

        pulse_w2 = VGroup(*[
            Dot(radius=0.08, color="#C084FC").move_to(hid_pos[k])
            for k in range(3)
        ])
        self.play(
            FadeIn(pulse_w2),
            Write(eq_z2),
            edges_w2.animate.set_stroke(color="#C084FC", width=2.6),
            run_time=1.4
        )
        self.play(
            AnimationGroup(*[
                pulse_w2[k].animate.move_to(out_pos)
                for k in range(3)
            ]),
            run_time=1.1,
            rate_func=rate_functions.ease_in_out_sine
        )
        self.play(
            FadeOut(pulse_w2),
            edges_w2.animate.set_stroke(color="#334155", width=2.0),
            Indicate(out_node[1], color="#38BDF8"),
            run_time=1.0
        )
        # Send z2 packet to cache slot 2
        z2_packet = MathTex(r"0.306", font_size=12, color="#38BDF8").move_to(out_pos)
        self.play(
            FadeOut(slots[2][2]),
            z2_packet.animate.move_to(slots[2][0].get_right() + LEFT * 0.9).scale(0.9),
            slots[2][0].animate.set_stroke(color="#38BDF8", width=1.8).set_fill(color="#082F49", opacity=0.8),
            run_time=1.4
        )
        self.wait(1.6)

        # -------------------------------------------------------------
        # 7. Step 4: y_hat = sigma(z2) [27.3 - 31.4s]
        # -------------------------------------------------------------
        eq_yhat = MathTex(
            r"\hat{y} = \sigma(z_2) = 0.576",
            font_size=14,
            color="#34D399"
        ).move_to(np.array([-3.8, 1.45, 0]))

        self.play(
            Write(eq_yhat),
            Flash(out_node[1], color="#34D399", flash_radius=0.6),
            run_time=1.2
        )
        yhat_packet = MathTex(r"0.576", font_size=12, color="#34D399").move_to(out_pos)
        self.play(
            FadeOut(slots[3][2]),
            yhat_packet.animate.move_to(slots[3][0].get_right() + LEFT * 0.9).scale(0.9),
            slots[3][0].animate.set_stroke(color="#34D399", width=1.8).set_fill(color="#064E3B", opacity=0.8),
            run_time=1.4
        )
        self.wait(1.5)

        # -------------------------------------------------------------
        # 8. Caching in Memory for the Backward Pass [31.4 - 42.5s]
        # -------------------------------------------------------------
        # RAM Lock indicator and memory efficiency callout
        lock_pill = RoundedRectangle(corner_radius=0.12, width=4.2, height=0.55, stroke_color="#10B981", stroke_width=1.5, fill_color="#064E3B", fill_opacity=0.9).next_to(rack_box, DOWN, buff=0.25)
        lock_text = Text("Preserved in RAM for Backward Sweep", font_size=11, color="#A7F3D0", weight=BOLD).move_to(lock_pill.get_center())
        lock_group = VGroup(lock_pill, lock_text)

        self.play(
            FadeIn(lock_group, shift=UP * 0.15),
            rack_box.animate.set_stroke(color="#10B981", width=2.2),
            run_time=1.5
        )

        # Glowing connection probe from Cache back towards network
        read_arrow = CurvedArrow(
            rack_box.get_left() + UP * 0.3,
            out_node.get_right() + UP * 0.3,
            angle=TAU / 7,
            color="#10B981",
            stroke_width=2.5
        )
        read_tag = Text("Read by Chain Rule", font_size=10, color="#6EE7B7", weight=BOLD).next_to(read_arrow, UP, buff=0.08)

        self.play(
            Create(read_arrow),
            Write(read_tag),
            run_time=1.6
        )
        self.wait(4.0)
        self.play(
            Indicate(lock_group, color="#34D399", scale_factor=1.05),
            run_time=1.5
        )
        self.wait(2.5)

        # -------------------------------------------------------------
        # 9. Key Efficiency Foundation [42.5 - 48.39s]
        # -------------------------------------------------------------
        eff_pill = RoundedRectangle(corner_radius=0.12, width=6.2, height=0.55, stroke_color="#F59E0B", stroke_width=1.5, fill_color="#451A03", fill_opacity=0.9).move_to(LEFT * 2.6 + DOWN * 2.3)
        eff_text = Text("O(1) Local Derivatives  |  No Expensive Recomputation", font_size=11, color="#FDE68A", weight=BOLD).move_to(eff_pill.get_center())
        eff_group = VGroup(eff_pill, eff_text)

        self.play(FadeIn(eff_group, shift=UP * 0.1), run_time=1.4)
        
        # Continuous subtle ambient node breathing to conclude
        self.play(
            AnimationGroup(
                Indicate(out_node[0], color="#34D399", scale_factor=1.1),
                *[Indicate(h[0], color="#C084FC", scale_factor=1.1) for h in hid_nodes],
                lag_ratio=0.1
            ),
            run_time=2.2
        )
        self.wait(2.29)