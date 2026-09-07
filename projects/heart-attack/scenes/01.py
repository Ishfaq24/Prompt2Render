"""Scene 01: Coronary Anatomy & Plaque Formation.

Features:
- Dark obsidian aesthetic (#0B0F19)
- Macro heart silhouette with Left Anterior Descending (LAD) coronary artery
- Micro cross-sectional arterial view showing progressive plaque stenosis
- Mayer-Sweller cognitive signaling on key anatomical entities
- Safe bottom caption zone
"""

from manim import *
from prompt2render.assets.mobjects import SafeCaptionZone
from prompt2render.cinematic import GlowAura, HeroMetricBadge, focus_on, reset_frame


class Scene01(MovingCameraScene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # ------------------------------------------------------------------
        # 1. Title Band & Hero Metric Badge
        # ------------------------------------------------------------------
        title = Text("Coronary Anatomy & Plaque Formation", font_size=32, color=WHITE).to_edge(UP, buff=0.35)
        vessel_badge = HeroMetricBadge("VESSEL", "LAD ARTERY", color="#38BDF8", width=2.8, height=1.1).to_corner(UR, buff=0.35).scale(0.8)
        self.play(FadeIn(title), FadeIn(vessel_badge), run_time=0.9)

        # ------------------------------------------------------------------
        # 2. Sentence 0 (0.0s - 7.25s): The Human Heart & Coronary Arteries
        # ------------------------------------------------------------------
        caption0 = SafeCaptionZone("The heart beats >100,000 times daily, nourished by coronary arteries.")
        self.play(FadeIn(caption0), run_time=0.5)

        # Stylized anatomical heart myocardium silhouette
        heart_shape = RoundedRectangle(
            width=3.6,
            height=4.2,
            corner_radius=0.9,
            fill_color="#991B1B",
            fill_opacity=0.92,
            stroke_color="#B91C1C",
            stroke_width=3.0,
        ).move_to(LEFT * 2.8 + DOWN * 0.1)
        heart_label = Text("Myocardium (Heart Muscle)", font_size=14, color="#FCA5A5").next_to(heart_shape, DOWN, buff=0.15)

        # Coronary Arterial Tree (LAD branch highlighted)
        lad_artery = CubicBezier(
            LEFT * 3.0 + UP * 1.5,
            LEFT * 2.4 + UP * 0.5,
            LEFT * 2.8 + DOWN * 0.5,
            LEFT * 2.2 + DOWN * 1.6,
            color="#EF4444",
            stroke_width=6.0,
        )
        circumflex_branch = CubicBezier(
            LEFT * 3.0 + UP * 1.5,
            LEFT * 3.6 + UP * 0.8,
            LEFT * 4.2 + DOWN * 0.2,
            LEFT * 4.0 + DOWN * 1.2,
            color="#DC2626",
            stroke_width=4.0,
        )

        artery_label = Text("Left Anterior Descending (LAD)", font_size=16, color="#FCA5A5").next_to(lad_artery, RIGHT, buff=0.25)

        self.play(DrawBorderThenFill(heart_shape), Write(heart_label), run_time=1.8)
        self.play(Create(lad_artery), Create(circumflex_branch), Write(artery_label), run_time=1.8)
        self.play(Indicate(lad_artery, color="#FDE047"), run_time=1.2)
        self.wait(1.0)

        # ------------------------------------------------------------------
        # 3. Sentence 1 (7.25s - 13.5s): Left Anterior Descending Artery
        # ------------------------------------------------------------------
        caption1 = SafeCaptionZone("The LAD wraps around the myocardium, supplying oxygenated blood.")
        self.play(Transform(caption0, caption1), run_time=0.6)

        # Blood flow particles traveling down the LAD
        dots = VGroup(*[
            Dot(radius=0.08, color="#38BDF8").move_to(lad_artery.point_from_proportion(i / 8))
            for i in range(8)
        ])
        self.play(Create(dots), run_time=1.0)
        self.play(
            AnimationGroup(*[
                d.animate.move_to(lad_artery.point_from_proportion(min(1.0, (i + 3) / 8)))
                for i, d in enumerate(dots)
            ]),
            run_time=2.2,
        )
        self.wait(2.4)

        # ------------------------------------------------------------------
        # 4. Sentence 2 (13.5s - 21.0s): LDL Oxidation & Chronic Inflammation
        # ------------------------------------------------------------------
        caption2 = SafeCaptionZone("Low-density lipoproteins penetrate the endothelial wall, oxidizing into inflammation.")
        self.play(Transform(caption0, caption2), run_time=0.6)

        # Transition to Microscopic Artery Cross-Section on the Right
        lumen_outer = Circle(radius=2.1, color="#334155", stroke_width=7, fill_color="#0F172A", fill_opacity=0.9).move_to(RIGHT * 3.2 + DOWN * 0.1)
        lumen_inner = Circle(radius=1.8, color="#DC2626", stroke_width=3).move_to(RIGHT * 3.2 + DOWN * 0.1)
        cross_title = Text("Arterial Lumen Cross-Section", font_size=16, color="#94A3B8").next_to(lumen_outer, UP, buff=0.2)

        # Plaque crescent along bottom-right lumen wall
        plaque_lipid = AnnularSector(
            inner_radius=0.9,
            outer_radius=1.8,
            angle=PI * 0.85,
            start_angle=-PI * 0.45,
            fill_color="#F59E0B",
            fill_opacity=0.92,
            stroke_color="#D97706",
            stroke_width=2,
        ).move_to(lumen_outer.get_center() + DOWN * 0.45 + RIGHT * 0.1)

        self.play(
            FadeIn(lumen_outer),
            FadeIn(lumen_inner),
            Write(cross_title),
            run_time=1.5,
        )
        self.play(Create(plaque_lipid), run_time=2.0)
        self.play(Indicate(plaque_lipid, color="#FEF08A"), run_time=1.2)
        self.wait(1.8)

        # ------------------------------------------------------------------
        # 5. Sentence 3 (21.0s - 30.15s): Foam Cells, Lipid Core & Fibrous Cap
        # ------------------------------------------------------------------
        caption3 = SafeCaptionZone("Macrophages become foam cells, forming an atherosclerotic plaque under a fibrous cap.")
        self.play(Transform(caption0, caption3), run_time=0.6)

        # Fibrous cap lining the luminal surface of the plaque
        fibrous_cap = Arc(
            radius=0.95,
            start_angle=-PI * 0.45,
            angle=PI * 0.85,
            color="#E2E8F0",
            stroke_width=5.0,
        ).move_to(plaque_lipid.get_center() + UP * 0.35 + LEFT * 0.1)

        cap_label = Text("Fibrous Cap (Collagen)", font_size=14, color="#E2E8F0").next_to(fibrous_cap, UP, buff=0.15)
        core_label = Text("Lipid Core", font_size=14, color="#FEF08A").move_to(plaque_lipid.get_center() + DOWN * 0.1)

        stenosis_badge = HeroMetricBadge("STENOSIS", "50% OCCLUDED", color="#F59E0B", width=2.8, height=1.1).to_corner(UL, buff=0.35).scale(0.8)

        self.play(Create(fibrous_cap), Write(cap_label), Write(core_label), FadeIn(stenosis_badge), run_time=2.0)
        self.play(Indicate(fibrous_cap), Indicate(plaque_lipid), run_time=1.5)
        self.wait(4.0)
