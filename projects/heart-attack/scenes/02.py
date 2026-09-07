"""Scene 02: Plaque Rupture & Acute Thrombosis.

Features:
- High-magnification arterial cross-section
- Dynamic camera zoom (focus_on) into the fibrous cap rupture site
- Acute platelet swarming and fibrin thrombus occlusion (99% stenosis)
- Halting of blood flow and downstream perfusion starvation
- Sound design cues: acute rupture snap, platelet swarm chimes, alarm aura
"""

from manim import *
from prompt2render.assets.mobjects import SafeCaptionZone
from prompt2render.cinematic import GlowAura, HeroMetricBadge, focus_on, reset_frame


class Scene02(MovingCameraScene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # ------------------------------------------------------------------
        # 1. Title Band & Initial Status Badge
        # ------------------------------------------------------------------
        title = Text("Plaque Rupture & Acute Thrombosis", font_size=32, color=WHITE).to_edge(UP, buff=0.35)
        stenosis_badge = HeroMetricBadge("STENOSIS", "50% BASELINE", color="#F59E0B", width=2.8, height=1.1).to_corner(UR, buff=0.35).scale(0.8)
        self.play(FadeIn(title), FadeIn(stenosis_badge), run_time=0.9)

        # ------------------------------------------------------------------
        # 2. Setup Longitudinal Coronary Artery Section
        # ------------------------------------------------------------------
        artery_top = Line(LEFT * 5.5 + UP * 1.5, RIGHT * 5.5 + UP * 1.5, color="#DC2626", stroke_width=6)
        artery_bot = Line(LEFT * 5.5 + DOWN * 1.5, RIGHT * 5.5 + DOWN * 1.5, color="#DC2626", stroke_width=6)
        tunica_bg = Rectangle(width=11.0, height=3.0, fill_color="#1E1B4B", fill_opacity=0.4, stroke_opacity=0).move_to(ORIGIN)

        # Large atherosclerotic plaque bulging from bottom wall
        plaque_body = Polygon(
            LEFT * 2.5 + DOWN * 1.5,
            LEFT * 0.8 + UP * 0.4,
            RIGHT * 0.8 + UP * 0.4,
            RIGHT * 2.5 + DOWN * 1.5,
            fill_color="#F59E0B",
            fill_opacity=0.9,
            stroke_color="#D97706",
            stroke_width=2.5,
        )
        fibrous_cap_line = Line(LEFT * 0.9 + UP * 0.42, RIGHT * 0.9 + UP * 0.42, color="#E2E8F0", stroke_width=6)
        cap_label = Text("Fibrous Cap", font_size=15, color="#E2E8F0").next_to(fibrous_cap_line, DOWN, buff=0.15)

        self.play(Create(artery_top), Create(artery_bot), FadeIn(tunica_bg), Create(plaque_body), Create(fibrous_cap_line), Write(cap_label), run_time=1.6)

        # ------------------------------------------------------------------
        # 3. Sentence 0 (0.0s - 5.18s): Hemodynamic Shear Stress & Cap Fissure
        # ------------------------------------------------------------------
        caption0 = SafeCaptionZone("Under elevated hemodynamic shear stress, the fragile fibrous cap tears open.")
        self.play(FadeIn(caption0), run_time=0.5)

        # Camera zooms straight into the fibrous cap apex
        rupture_site = Dot(UP * 0.42, radius=0.01)
        self.play(focus_on(self.camera.frame, rupture_site, scale=0.55), run_time=1.2)

        # Mechanical tear / fissure in the fibrous cap
        tear_left = Line(LEFT * 0.9 + UP * 0.42, LEFT * 0.08 + UP * 0.35, color="#E2E8F0", stroke_width=5)
        tear_right = Line(RIGHT * 0.08 + UP * 0.35, RIGHT * 0.9 + UP * 0.42, color="#E2E8F0", stroke_width=5)
        fissure_gap = Circle(radius=0.18, color="#EF4444", fill_color="#EF4444", fill_opacity=0.8).move_to(UP * 0.38)

        self.play(
            FadeOut(fibrous_cap_line),
            Create(tear_left),
            Create(tear_right),
            FadeIn(fissure_gap),
            run_time=0.8,
        )
        self.play(Circumscribe(fissure_gap, color=YELLOW), run_time=0.8)
        self.wait(0.8)

        # ------------------------------------------------------------------
        # 4. Sentence 1 (5.18s - 12.5s): Tissue Factor & Platelet Cascade
        # ------------------------------------------------------------------
        caption1 = SafeCaptionZone("Exposed tissue factor triggers explosive platelet activation and fibrin clotting.")
        self.play(Transform(caption0, caption1), run_time=0.6)

        # Platelets swarming to the fissure site
        platelets = VGroup(*[
            Dot(
                point=np.array([np.random.uniform(-1.5, 1.5), np.random.uniform(0.6, 1.3), 0]),
                radius=0.06,
                color="#FBBF24",
            ) for _ in range(12)
        ])
        self.play(FadeIn(platelets), run_time=0.8)

        # Platelets converge and aggregate at the fissure
        self.play(
            AnimationGroup(*[
                p.animate.move_to(fissure_gap.get_center() + np.random.uniform(-0.25, 0.25, 3) * np.array([1, 1, 0]))
                for p in platelets
            ]),
            run_time=2.2,
        )
        self.play(Indicate(platelets, color="#FFFFFF"), run_time=1.2)
        self.wait(2.2)

        # ------------------------------------------------------------------
        # 5. Sentence 2 (12.5s - 20.0s): Acute Thrombus & 99% Luminal Occlusion
        # ------------------------------------------------------------------
        caption2 = SafeCaptionZone("Within seconds, a dense thrombus consolidates, causing 99% luminal occlusion.")
        self.play(Transform(caption0, caption2), run_time=0.6)

        # Expanding occlusive thrombus filling the arterial channel
        thrombus = RoundedRectangle(
            width=2.6,
            height=2.4,
            corner_radius=0.3,
            fill_color="#7F1D1D",
            fill_opacity=0.96,
            stroke_color="#DC2626",
            stroke_width=3.5,
        ).move_to(UP * 0.1)
        thrombus_label = Text("OCCLUSIVE THROMBUS", font_size=15, color="#FCA5A5", weight="BOLD").move_to(thrombus.get_center())

        new_badge = HeroMetricBadge("STENOSIS", "99% OCCLUDED", color="#EF4444", width=2.8, height=1.1).to_corner(UR, buff=0.35).scale(0.8)
        warning_aura = GlowAura(thrombus, color="#EF4444", num_layers=4)

        self.play(
            GrowFromCenter(thrombus),
            FadeIn(thrombus_label),
            FadeIn(warning_aura),
            Transform(stenosis_badge, new_badge),
            run_time=2.2,
        )
        self.play(Indicate(thrombus, color="#FCA5A5"), run_time=1.4)
        self.wait(2.5)

        # ------------------------------------------------------------------
        # 6. Sentence 3 (20.0s - 28.68s): Flow Halts & Myocardial Starvation
        # ------------------------------------------------------------------
        caption3 = SafeCaptionZone("Arterial blood flow halts abruptly, starving downstream myocardial cells.")
        self.play(Transform(caption0, caption3), run_time=0.6)

        # Reset camera to view whole vessel overview
        self.play(reset_frame(self.camera.frame), run_time=1.2)

        # Blocked erythrocytes piling up on the left side
        blocked_flow = VGroup(*[
            Dot(point=LEFT * (2.8 + i * 0.4) + UP * np.random.uniform(-0.6, 0.6), radius=0.08, color="#EF4444")
            for i in range(10)
        ])
        flow_halt_label = Text("BLOOD FLOW BLOCKED (0 mL/min)", font_size=16, color="#EF4444", weight="BOLD").next_to(artery_bot, DOWN, buff=0.25)

        self.play(FadeIn(blocked_flow), Write(flow_halt_label), run_time=1.5)
        self.play(Circumscribe(flow_halt_label, color=RED), run_time=1.4)
        self.wait(3.5)
