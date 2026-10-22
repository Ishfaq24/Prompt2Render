CYAN = "#00FFFF"
from manim import *
from prompt2render.assets.mobjects import (
    FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
    ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
    ArrayGrid, FormulaCard, KeyBadge, MemoryBankMobject, BinaryTreeMobject
)
import math
import numpy as np


class Scene08(Scene):
    def construct(self):
        # Set dark obsidian background theme matching scenes 01-07 and 09
        config.background_color = "#0B0F19"

        # -----------------------------------------------------------------
        # 1. HEADER BAND (y = 3.3)
        # -----------------------------------------------------------------
        title = Text(
            "REAL-WORLD APPLICATIONS: VISION TO DECISION",
            font_size=22,
            weight=BOLD,
            color=WHITE,
        )
        subtitle = Text(
            "Section 8: Autonomous Systems, Medical Diagnostics & Robotics",
            font_size=14,
            color="#00F0FF",
        ).scale_to_fit_width(12.0)
        header = (
            VGroup(title, subtitle)
            .arrange(DOWN, buff=0.10)
            .to_edge(UP, buff=0.30)
        )

        # -----------------------------------------------------------------
        # 2. LEFT PANEL: AUTONOMOUS VEHICLE PERCEPTION VIEWPORT
        # -----------------------------------------------------------------
        # Viewfinder container (x in [-6.4, -0.6], y in [-2.5, 1.8])
        vf_bg = RoundedRectangle(
            width=5.8,
            height=4.3,
            corner_radius=0.15,
            color="#388BFD",
            fill_color="#0F172A",
            fill_opacity=0.85,
            stroke_width=1.8,
        ).move_to(LEFT * 3.5 + DOWN * 0.4)

        vf_header = Text(
            "AUTONOMOUS VISION & SENSOR FEED",
            font_size=12,
            weight=BOLD,
            color="#388BFD",
        ).next_to(vf_bg.get_top(), DOWN, buff=0.18)

        # HUD Corner Reticles
        reticle_size = 0.25
        def make_reticles(rect):
            reticles = VGroup()
            corners = [
                (rect.get_corner(UL), [RIGHT, DOWN]),
                (rect.get_corner(UR), [LEFT, DOWN]),
                (rect.get_corner(DL), [RIGHT, UP]),
                (rect.get_corner(DR), [LEFT, UP]),
            ]
            for pt, (dx, dy) in corners:
                h = Line(pt, pt + dx * reticle_size, color="#00F0FF", stroke_width=2.5)
                v = Line(pt, pt + dy * reticle_size, color="#00F0FF", stroke_width=2.5)
                reticles.add(h, v)
            return reticles

        reticles = make_reticles(vf_bg)

        # Simulated road horizon and perspective lanes
        horizon_y = vf_bg.get_center()[1] + 0.35
        horizon_line = Line(
            vf_bg.get_left() + RIGHT * 0.2 + UP * 0.35,
            vf_bg.get_right() + LEFT * 0.2 + UP * 0.35,
            color="#334155",
            stroke_width=1.5,
        )
        vanishing_pt = np.array([vf_bg.get_center()[0], horizon_y, 0])

        left_lane = Line(
            vanishing_pt,
            vf_bg.get_corner(DL) + RIGHT * 0.8 + UP * 0.2,
            color="#475569",
            stroke_width=2,
        )
        right_lane = Line(
            vanishing_pt,
            vf_bg.get_corner(DR) + LEFT * 0.8 + UP * 0.2,
            color="#475569",
            stroke_width=2,
        )
        center_dashes = VGroup()
        for alpha in np.linspace(0.15, 0.95, 5):
            p1 = interpolate(vanishing_pt, np.array([vf_bg.get_center()[0], vf_bg.get_bottom()[1] + 0.2, 0]), alpha)
            p2 = interpolate(vanishing_pt, np.array([vf_bg.get_center()[0], vf_bg.get_bottom()[1] + 0.2, 0]), min(alpha + 0.08, 1.0))
            center_dashes.add(Line(p1, p2, color=YELLOW_C, stroke_width=2))

        road_group = VGroup(horizon_line, left_lane, right_lane, center_dashes)

        # Obstacle 1: Leading Vehicle Bounding Box
        box1_center = vf_bg.get_center() + UP * 0.2 + RIGHT * 0.5
        box1_rect = Rectangle(width=1.4, height=1.1, color="#10B981", stroke_width=2)
        box1_rect.move_to(box1_center)
        box1_label = Text("[ CAR: 0.98 | 18.2m ]", font_size=9, weight=BOLD, color="#10B981")
        box1_label.next_to(box1_rect, UP, buff=0.06)
        car_icon = RoundedRectangle(width=1.1, height=0.7, corner_radius=0.1, color="#059669", fill_color="#064E3B", fill_opacity=0.6).move_to(box1_center)
        box1_group = VGroup(box1_rect, box1_label, car_icon)

        # Obstacle 2: Pedestrian Bounding Box
        box2_center = vf_bg.get_center() + DOWN * 0.5 + LEFT * 1.6
        box2_rect = Rectangle(width=0.8, height=1.5, color="#FFB703", stroke_width=2)
        box2_rect.move_to(box2_center)
        box2_label = Text("[ PED: 0.95 | 7.4m ]", font_size=9, weight=BOLD, color="#FFB703")
        box2_label.next_to(box2_rect, UP, buff=0.06)
        ped_head = Circle(radius=0.14, color="#D97706", fill_color="#78350F", fill_opacity=0.6).move_to(box2_center + UP * 0.45)
        ped_body = RoundedRectangle(width=0.45, height=0.75, corner_radius=0.08, color="#D97706", fill_color="#78350F", fill_opacity=0.6).move_to(box2_center + DOWN * 0.1)
        box2_group = VGroup(box2_rect, box2_label, ped_head, ped_body)

        # Obstacle 3: Cyclist / Side Obstacle Bounding Box
        box3_center = vf_bg.get_center() + DOWN * 0.8 + RIGHT * 1.8
        box3_rect = Rectangle(width=0.9, height=1.2, color="#00F0FF", stroke_width=2)
        box3_rect.move_to(box3_center)
        box3_label = Text("[ CYCLIST: 0.91 ]", font_size=9, weight=BOLD, color="#00F0FF")
        box3_label.next_to(box3_rect, UP, buff=0.06)
        box3_group = VGroup(box3_rect, box3_label)

        # LiDAR Radar Scanning Arc
        lidar_center = np.array([vf_bg.get_center()[0], vf_bg.get_bottom()[1] + 0.15, 0])
        lidar_arc = Arc(radius=3.2, start_angle=40 * DEGREES, angle=100 * DEGREES, arc_center=lidar_center, color="#388BFD", stroke_width=1.5)
        lidar_ray = Line(lidar_center, lidar_center + UP * 2.8 + LEFT * 1.8, color="#00F0FF", stroke_width=1.8)

        # Bottom telemetry pill
        telemetry_txt = Text("Raw Sensor Stream: Camera + LiDAR  →  x(t) ∈ ℝᴺ", font_size=10, color=LIGHT_GRAY)
        telemetry_txt.next_to(vf_bg.get_bottom(), UP, buff=0.12)

        viewfinder_mobjects = VGroup(vf_bg, vf_header, reticles, road_group, telemetry_txt)

        # -----------------------------------------------------------------
        # 3. RIGHT PANEL: MEDICAL DIAGNOSTICS & ROBOTIC DECISION LOOP
        # -----------------------------------------------------------------

        # CARD 1: MEDICAL DIAGNOSTICS & MRI ATTENTION HEATMAP (Top Right)
        med_bg = RoundedRectangle(
            width=5.8,
            height=2.0,
            corner_radius=0.12,
            color="#A855F7",
            fill_color="#1E1035",
            fill_opacity=0.9,
            stroke_width=1.5,
        ).move_to(RIGHT * 3.4 + UP * 0.8)

        med_title = Text("1. MEDICAL IMAGING & DIAGNOSTICS", font_size=12, weight=BOLD, color="#C084FC")
        med_title.next_to(med_bg.get_top(), DOWN, buff=0.14).to_edge(LEFT, buff=0.35)
        med_title.move_to(np.array([med_bg.get_center()[0] - 0.5, med_bg.get_top()[1] - 0.22, 0]))

        # Heatmap / Cross-section Scan Grid Simulation (4x4 matrix)
        scan_cells = VGroup()
        grid_start = med_bg.get_left() + RIGHT * 1.0 + DOWN * 0.1
        cell_dim = 0.28
        heat_vals = [
            [0.1, 0.2, 0.3, 0.1],
            [0.2, 0.85, 0.95, 0.4],
            [0.3, 0.90, 0.80, 0.2],
            [0.1, 0.3, 0.2, 0.1],
        ]
        for r in range(4):
            for c in range(4):
                val = heat_vals[r][c]
                col = interpolate_color(ManimColor(DARK_GRAY), ManimColor("#EF4444"), val) if val > 0.5 else interpolate_color(ManimColor(BLACK), ManimColor("#388BFD"), val * 2)
                sq = Square(side_length=cell_dim, fill_color=col, fill_opacity=0.9, stroke_color="#334155", stroke_width=0.6)
                sq.move_to(grid_start + RIGHT * (c * cell_dim) + DOWN * (r * cell_dim))
                scan_cells.add(sq)

        scan_border = SurroundingRectangle(scan_cells, color="#C084FC", buff=0.04, stroke_width=1.2)
        anomaly_circle = Ellipse(width=0.75, height=0.65, color="#F43F5E", stroke_width=2.5).move_to(scan_cells.get_center() + UP * 0.05 + RIGHT * 0.05)
        anomaly_tag = Text("Attention Anomaly: 99.2%", font_size=9, color="#F43F5E").next_to(scan_border, DOWN, buff=0.08)

        med_badge = MetricBadge(label="DIAGNOSTIC ACCURACY", value="99.4%", status="good", font_size=12)
        med_badge.scale(0.85).move_to(med_bg.get_right() + LEFT * 1.5 + DOWN * 0.1)

        med_group = VGroup(med_bg, med_title, scan_cells, scan_border, anomaly_circle, anomaly_tag, med_badge)

        # CARD 2: ROBOTIC AUTOMATION & REAL-TIME DECISION (Bottom Right)
        rob_bg = RoundedRectangle(
            width=5.8,
            height=2.0,
            corner_radius=0.12,
            color="#10B981",
            fill_color="#064E3B",
            fill_opacity=0.9,
            stroke_width=1.5,
        ).move_to(RIGHT * 3.4 + DOWN * 1.55)

        rob_title = Text("2. ROBOTIC AUTOMATION & DECISION PIPELINE", font_size=12, weight=BOLD, color="#34D399")
        rob_title.move_to(np.array([rob_bg.get_center()[0] - 0.2, rob_bg.get_top()[1] - 0.22, 0]))

        # Cascade Flow: Sensory Tensor -> Multi-Layer Net -> Decision
        sens_box = RoundedRectangle(width=1.2, height=0.6, corner_radius=0.08, color="#388BFD", fill_color="#1E293B", fill_opacity=0.9, stroke_width=1.2)
        sens_txt = Text("Sensors x", font_size=9, color=WHITE).move_to(sens_box.get_center())
        sens_grp = VGroup(sens_box, sens_txt).move_to(rob_bg.get_left() + RIGHT * 1.0 + DOWN * 0.12)

        net_box = RoundedRectangle(width=1.4, height=0.6, corner_radius=0.08, color="#A855F7", fill_color="#1E1035", fill_opacity=0.9, stroke_width=1.2)
        net_txt = Text("Deep Net f(x)", font_size=9, color=WHITE).move_to(net_box.get_center())
        net_grp = VGroup(net_box, net_txt).move_to(rob_bg.get_center() + DOWN * 0.12 + LEFT * 0.1)

        act_box = RoundedRectangle(width=1.3, height=0.6, corner_radius=0.08, color="#10B981", fill_color="#064E3B", fill_opacity=0.9, stroke_width=1.2)
        act_txt = Text("Action u(t)", font_size=9, color=WHITE).move_to(act_box.get_center())
        act_grp = VGroup(act_box, act_txt).move_to(rob_bg.get_right() + LEFT * 1.0 + DOWN * 0.12)

        flow_arr1 = Arrow(sens_box.get_right(), net_box.get_left(), buff=0.06, color=GRAY_A, stroke_width=2, max_tip_length_to_length_ratio=0.25)
        flow_arr2 = Arrow(net_box.get_right(), act_box.get_left(), buff=0.06, color=GRAY_A, stroke_width=2, max_tip_length_to_length_ratio=0.25)

        dec_badge = Text("Decision: STEER -1.4° | BRAKE 0.0", font_size=10, weight=BOLD, color=YELLOW_C).next_to(act_box, DOWN, buff=0.08)
        lat_badge = MetricBadge(label="INFERENCE LATENCY", value="12 ms", status="good", font_size=11).scale(0.72)
        lat_badge.next_to(sens_box, DOWN, buff=0.06)

        rob_group = VGroup(rob_bg, rob_title, sens_grp, net_grp, act_grp, flow_arr1, flow_arr2, dec_badge, lat_badge)

        # -----------------------------------------------------------------
        # 4. ANIMATION TIMELINE CHOREOGRAPHY (Duration: 18.33s)
        # -----------------------------------------------------------------

        # --- Sentence 0 [0.0s -> 4.67s]: Core architecture powers AI across globe ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(vf_bg),
            Create(reticles),
            run_time=1.3
        )
        self.play(
            FadeIn(vf_header),
            Create(road_group),
            FadeIn(telemetry_txt),
            run_time=1.4
        )
        # Radar scan sweep
        self.play(
            Create(lidar_arc),
            Rotate(lidar_ray, angle=75 * DEGREES, about_point=lidar_center),
            run_time=1.6
        )
        self.wait(0.37)  # Reaches t = 4.67s

        # --- Sentence 1 [4.67s -> 17.69s]: Real-time obstacle detection, medical, robotics ---
        # Reveal Obstacle Bounding Boxes sequentially
        self.play(
            FadeIn(box1_group, shift=UP * 0.1),
            Indicate(box1_rect, color="#10B981"),
            run_time=1.1
        )
        self.play(
            FadeIn(box2_group, shift=RIGHT * 0.1),
            Indicate(box2_rect, color="#FFB703"),
            run_time=1.1
        )
        self.play(
            FadeIn(box3_group, shift=LEFT * 0.1),
            run_time=0.9
        )  # Reaches t = 7.77s

        # Transition to Medical Diagnostics Panel
        self.play(
            FadeIn(med_bg, shift=LEFT * 0.2),
            FadeIn(med_title),
            run_time=1.0
        )
        self.play(
            Create(scan_cells),
            Create(scan_border),
            Create(anomaly_circle),
            FadeIn(anomaly_tag),
            FadeIn(med_badge, shift=UP * 0.1),
            run_time=1.4
        )
        self.play(
            Circumscribe(anomaly_circle, color="#F43F5E", buff=0.06),
            run_time=1.1
        )  # Reaches t = 11.27s

        # Transition to Robotic Automation & Real-Time Decision Loop
        self.play(
            FadeIn(rob_bg, shift=LEFT * 0.2),
            FadeIn(rob_title),
            FadeIn(sens_grp),
            GrowArrow(flow_arr1),
            FadeIn(net_grp),
            GrowArrow(flow_arr2),
            FadeIn(act_grp),
            run_time=1.6
        )

        # Pulse signal across decision network
        pulse = Dot(color="#00F0FF", radius=0.09).move_to(sens_box.get_center())
        self.play(FadeIn(pulse, scale=0.5), run_time=0.2)
        self.play(pulse.animate.move_to(net_box.get_center()), run_time=0.6)
        self.play(pulse.animate.move_to(act_box.get_center()), run_time=0.6)
        self.play(FadeOut(pulse), run_time=0.2)

        self.play(
            FadeIn(dec_badge, shift=UP * 0.08),
            FadeIn(lat_badge, shift=UP * 0.08),
            Indicate(dec_badge, color="#10B981"),
            run_time=1.2
        )  # Reaches t = 15.47s

        # Final showcase hold and convergence
        self.play(
            Circumscribe(lat_badge, color="#00F0FF", buff=0.06),
            run_time=1.2
        )  # Reaches t = 16.67s

        self.wait(1.02)  # Reaches total timeline 17.69s (safe hold until section boundary)
