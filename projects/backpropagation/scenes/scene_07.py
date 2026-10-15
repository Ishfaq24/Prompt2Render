from manim import *
import numpy as np

class Scene07(Scene):
    def construct(self):
        self.camera.background_color = "#080B14"

        # -------------------------------------------------------------
        # 1. Clean Title Banner [0.0 - 1.0s]
        # -------------------------------------------------------------
        title = Text("The Full Weight Update Loop & Loss Convergence", font_size=23, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        title_line = Line(LEFT * 5.2, RIGHT * 5.2, stroke_width=1.5, stroke_color="#10B981").next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN * 0.2), Create(title_line), run_time=1.0)

        # -------------------------------------------------------------
        # 2. Universal Parameter Update Law (Top Stage) [1.0 - 9.5s]
        # -------------------------------------------------------------
        update_law = MathTex(
            r"W_{\mathrm{new}} = W_{\mathrm{old}} - \eta\,\nabla_W L \quad \iff \quad W_{ij}^{(l)} \leftarrow W_{ij}^{(l)} - \eta\,\frac{\partial L}{\partial W_{ij}^{(l)}}",
            font_size=16,
            color=WHITE
        ).shift(UP * 2.1)
        update_law.set_color_by_tex(r"\eta", "#34D399")
        update_law.set_color_by_tex(r"\nabla_W L", "#FCD34D")
        update_law.set_color_by_tex(r"\frac{\partial L}{\partial W_{ij}^{(l)}}", "#FCD34D")

        self.play(Write(update_law), run_time=2.0)
        self.play(
            Indicate(update_law, color="#34D399", scale_factor=1.06),
            run_time=2.2
        )
        self.wait(4.3)

        # -------------------------------------------------------------
        # 3. 4-Stage Cyclical Engine (Left Stage)
        # -------------------------------------------------------------
        engine_center = np.array([-4.0, -0.7, 0])
        r_orb = 1.45

        angles = [PI / 2, 0, -PI / 2, PI]
        stations_info = [
            ("1. Sample Mini-batch", engine_center + np.array([0, r_orb, 0]), "#38BDF8"),
            ("2. Forward Cache", engine_center + np.array([r_orb, 0, 0]), "#F59E0B"),
            ("3. Backward Sweep", engine_center + np.array([0, -r_orb, 0]), "#C084FC"),
            ("4. Gradient Update", engine_center + np.array([-r_orb, 0, 0]), "#10B981")
        ]

        st_nodes = VGroup()
        for idx, (name, pos, col) in enumerate(stations_info):
            c = Circle(radius=0.12, color=col, fill_color=col, fill_opacity=0.6, stroke_width=2.0).move_to(pos)
            g = Circle(radius=0.22, stroke_opacity=0, fill_color=col, fill_opacity=0.15).move_to(pos)
            lbl = Text(name, font_size=10, color=col, weight=BOLD)
            if idx == 0:
                lbl.next_to(c, UP, buff=0.14)
            elif idx == 1:
                lbl.next_to(c, RIGHT, buff=0.14)
            elif idx == 2:
                lbl.next_to(c, DOWN, buff=0.14)
            else:
                lbl.next_to(c, LEFT, buff=0.14)
            st_nodes.add(VGroup(g, c, lbl))

        orbit_ring = Circle(radius=r_orb, stroke_color="#334155", stroke_width=1.5).move_to(engine_center)
        engine_title = Text("TRAINING\nLOOP", font_size=10, weight=BOLD, color="#64748B", line_spacing=0.8).move_to(engine_center)
        cycle_engine = VGroup(orbit_ring, engine_title, st_nodes)

        # -------------------------------------------------------------
        # 4. Loss Convergence Axes (Right Stage) [9.5 - 21.0s]
        # -------------------------------------------------------------
        axes = Axes(
            x_range=[0, 200, 50],
            y_range=[0, 0.75, 0.25],
            x_length=5.6,
            y_length=3.2,
            axis_config={"color": "#475569", "stroke_width": 1.8, "include_numbers": True, "font_size": 11}
        ).move_to(RIGHT * 3.4 + DOWN * 0.7)

        x_lbl = Text("Iterations (t)", font_size=11, color="#94A3B8").next_to(axes.x_axis, DOWN, buff=0.22)
        y_lbl = Text("Loss L(t)", font_size=11, color="#94A3B8").next_to(axes.y_axis, UP, buff=0.15)

        np.random.seed(42)
        xs = np.linspace(0, 200, 80)
        ys = 0.67 * np.exp(-xs / 38.0) + 0.02 + 0.012 * np.sin(xs / 3.5) * np.exp(-xs / 60.0)

        self.play(
            FadeIn(cycle_engine, lag_ratio=0.1),
            Create(axes), Write(x_lbl), Write(y_lbl),
            run_time=2.2
        )

        orbit_photon = Dot(radius=0.1, color="#FBBF24").move_to(stations_info[0][1])
        self.play(FadeIn(orbit_photon), run_time=0.4)

        for step in range(3):
            next_idx = (step + 1) % 4
            arc = Arc(
                radius=r_orb,
                start_angle=angles[step],
                angle=-PI / 2,
                arc_center=engine_center
            )
            self.play(
                MoveAlongPath(orbit_photon, arc),
                Indicate(st_nodes[step][1], color="#FBBF24"),
                run_time=1.8,
                rate_func=rate_functions.ease_in_out_sine
            )
        self.wait(3.5)

        # -------------------------------------------------------------
        # 5. Iterative Parameter Sculpting [21.0 - 34.0s]
        # -------------------------------------------------------------
        sculpt_badge = RoundedRectangle(
            corner_radius=0.1,
            width=5.8,
            height=0.55,
            stroke_color="#818CF8",
            stroke_width=1.2,
            fill_color="#1E1B4B",
            fill_opacity=0.9
        ).move_to(RIGHT * 3.4 + UP * 1.35)
        sculpt_text = Text("Thousands of passes sculpt weights from noise to precision", font_size=10, color="#C7D2FE").move_to(sculpt_badge.get_center())
        sculpt_group = VGroup(sculpt_badge, sculpt_text)

        arc_to_update = Arc(
            radius=r_orb,
            start_angle=angles[2],
            angle=-PI / 2,
            arc_center=engine_center
        )

        self.play(
            FadeIn(sculpt_group, shift=UP * 0.1),
            MoveAlongPath(orbit_photon, arc_to_update),
            Indicate(st_nodes[3][1], color="#10B981"),
            run_time=2.0
        )

        for step in range(2):
            idx = step % 4
            next_idx = (step + 1) % 4
            arc_step = Arc(
                radius=r_orb,
                start_angle=angles[(step + 3) % 4],
                angle=-PI / 2,
                arc_center=engine_center
            )
            self.play(
                MoveAlongPath(orbit_photon, arc_step),
                Indicate(st_nodes[idx][1], color="#38BDF8"),
                run_time=1.8,
                rate_func=rate_functions.ease_in_out_sine
            )
        self.wait(7.4)

        # -------------------------------------------------------------
        # 6. Loss Convergence Animation [34.0 - 43.0s]
        # -------------------------------------------------------------
        loss_path = axes.plot_line_graph(
            x_values=xs,
            y_values=ys,
            line_color="#FBBF24",
            stroke_width=3.0,
            add_vertex_dots=False
        )["line_graph"]

        tracker_dot = Dot(axes.c2p(xs[0], ys[0]), radius=0.09, color="#F59E0B")
        loss_val_label = MathTex(r"L = 0.67 \rightarrow 0.02", font_size=13, color="#FCD34D").next_to(tracker_dot, UP + RIGHT, buff=0.15)

        self.play(
            Create(loss_path),
            FadeIn(tracker_dot),
            Write(loss_val_label),
            run_time=3.5,
            rate_func=rate_functions.ease_in_out_sine
        )
        self.play(
            tracker_dot.animate.move_to(axes.c2p(xs[-1], ys[-1])),
            loss_val_label.animate.next_to(axes.c2p(xs[-1], ys[-1]), UP + RIGHT, buff=0.12),
            run_time=2.5,
            rate_func=rate_functions.ease_out_sine
        )
        self.wait(3.0)

        # -------------------------------------------------------------
        # 7. Final Sweep Conclusion [43.0 - 49.33s]
        # -------------------------------------------------------------
        conv_badge = RoundedRectangle(
            corner_radius=0.1,
            width=5.8,
            height=0.55,
            stroke_color="#10B981",
            stroke_width=1.5,
            fill_color="#064E3B",
            fill_opacity=0.92
        ).move_to(RIGHT * 3.4 + UP * 1.35)
        conv_text = Text("All Gradients Computed in One Single Backward Sweep", font_size=10, color="#A7F3D0", weight=BOLD).move_to(conv_badge.get_center())
        conv_group = VGroup(conv_badge, conv_text)

        self.play(
            FadeOut(sculpt_group),
            FadeIn(conv_group, shift=UP * 0.1),
            Flash(tracker_dot, color="#10B981", flash_radius=0.6),
            run_time=1.8
        )
        self.wait(4.53)