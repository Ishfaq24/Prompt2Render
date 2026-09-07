"""Scene 03: Ischemia, Necrosis, and STEMI.

Features:
- SplitStage presentation: Myocardial tissue block on Left, Electrocardiogram (ECG) on Right
- Tissue color transition from vital oxygenated crimson to necrotic ischemic purple
- Dynamic ECG wave morphing from normal P-QRS-T to severe ST-segment elevation (STEMI)
- Mayer-Sweller cognitive signaling on cellular ATP depletion and ECG injury currents
- Safe bottom caption zone and medical golden-hour reperfusion summary
"""

from manim import *
from prompt2render.assets.mobjects import SafeCaptionZone
from prompt2render.cinematic import GlowAura, HeroMetricBadge, focus_on, reset_frame


class Scene03(MovingCameraScene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # ------------------------------------------------------------------
        # 1. Title Band & Initial Metric Badges
        # ------------------------------------------------------------------
        title = Text("Ischemia, Necrosis, and STEMI", font_size=32, color=WHITE).to_edge(UP, buff=0.35)
        atp_badge = HeroMetricBadge("ATP LEVEL", "DEPLETING", color="#F59E0B", width=2.6, height=1.1).to_corner(UL, buff=0.35).scale(0.8)
        ecg_badge = HeroMetricBadge("EKG RHYTHM", "NORMAL SINUS", color="#10B981", width=2.6, height=1.1).to_corner(UR, buff=0.35).scale(0.8)
        self.play(FadeIn(title), FadeIn(atp_badge), FadeIn(ecg_badge), run_time=0.9)

        # ------------------------------------------------------------------
        # 2. Left Side: Myocardial Tissue Block
        # ------------------------------------------------------------------
        myo_block = RoundedRectangle(
            width=4.5,
            height=3.4,
            corner_radius=0.2,
            fill_color="#991B1B",
            fill_opacity=0.95,
            stroke_color="#DC2626",
            stroke_width=2.5,
        ).move_to(LEFT * 3.3 + DOWN * 0.1)
        myo_title = Text("Myocardial Tissue Block", font_size=15, color="#FCA5A5").next_to(myo_block, UP, buff=0.15)
        self.play(FadeIn(myo_block), Write(myo_title), run_time=1.2)

        # ------------------------------------------------------------------
        # 3. Right Side: Real-Time Electrocardiogram (ECG) Monitor
        # ------------------------------------------------------------------
        ecg_grid = Rectangle(
            width=5.5,
            height=3.4,
            fill_color="#0F172A",
            fill_opacity=0.95,
            stroke_color="#334155",
            stroke_width=2.0,
        ).move_to(RIGHT * 3.3 + DOWN * 0.1)
        ecg_title = Text("Lead II Rhythm Monitor (ECG)", font_size=15, color="#38BDF8").next_to(ecg_grid, UP, buff=0.15)

        # Normal P-QRS-T waveform
        normal_ecg = VMobject(color="#10B981", stroke_width=3.5)
        normal_ecg.set_points_as_corners([
            RIGHT * 0.7 + DOWN * 0.1,
            RIGHT * 1.3 + DOWN * 0.1,
            RIGHT * 1.6 + UP * 0.3,    # P wave
            RIGHT * 1.9 + DOWN * 0.1,
            RIGHT * 2.2 + DOWN * 0.1,
            RIGHT * 2.4 + DOWN * 0.3,  # Q wave
            RIGHT * 2.7 + UP * 1.3,    # R peak
            RIGHT * 3.0 + DOWN * 0.5,  # S wave
            RIGHT * 3.3 + DOWN * 0.1,  # ST baseline
            RIGHT * 4.0 + UP * 0.4,    # T wave
            RIGHT * 4.5 + DOWN * 0.1,
            RIGHT * 5.8 + DOWN * 0.1,
        ])

        self.play(FadeIn(ecg_grid), Write(ecg_title), Create(normal_ecg), run_time=1.6)

        # ------------------------------------------------------------------
        # 4. Sentence 0 (0.0s - 7.5s): Anaerobic Metabolism & ATP Depletion
        # ------------------------------------------------------------------
        caption0 = SafeCaptionZone("Deprived of perfusion, myocytes switch to anaerobic glycolysis, exhausting ATP.")
        self.play(FadeIn(caption0), run_time=0.5)

        depleted_badge = HeroMetricBadge("ATP LEVEL", "CRITICAL 0%", color="#EF4444", width=2.6, height=1.1).to_corner(UL, buff=0.35).scale(0.8)

        # Ischemic core expanding inside the myocardium
        ischemic_core = Circle(radius=1.2, fill_color="#3B0764", fill_opacity=0.9, stroke_color="#7E22CE", stroke_width=2).move_to(myo_block.get_center())
        ischemia_label = Text("Ischemic Zone", font_size=14, color="#D8B4FE").move_to(ischemic_core.get_center())

        self.play(
            Transform(atp_badge, depleted_badge),
            FadeIn(ischemic_core),
            Write(ischemia_label),
            run_time=2.2,
        )
        self.play(Indicate(ischemic_core), run_time=1.2)
        self.wait(1.5)

        # ------------------------------------------------------------------
        # 5. Sentence 1 (7.5s - 16.5s): Transmembrane Collapse & ST Elevation
        # ------------------------------------------------------------------
        caption1 = SafeCaptionZone("Transmembrane ion gradients collapse, producing ST-segment elevation (STEMI).")
        self.play(Transform(caption0, caption1), run_time=0.6)

        # Classic Tombstone ST-Elevation (STEMI) wave
        stemi_ecg = VMobject(color="#EF4444", stroke_width=4.0)
        stemi_ecg.set_points_as_corners([
            RIGHT * 0.7 + DOWN * 0.1,
            RIGHT * 1.3 + DOWN * 0.1,
            RIGHT * 1.6 + UP * 0.3,    # P wave
            RIGHT * 1.9 + DOWN * 0.1,
            RIGHT * 2.2 + DOWN * 0.1,
            RIGHT * 2.4 + DOWN * 0.3,  # Q wave
            RIGHT * 2.7 + UP * 1.3,    # R peak
            RIGHT * 3.0 + UP * 0.85,   # ST ELEVATION (high plateau!)
            RIGHT * 3.6 + UP * 0.95,   # Merged elevated T wave
            RIGHT * 4.3 + UP * 0.8,
            RIGHT * 4.8 + DOWN * 0.1,
            RIGHT * 5.8 + DOWN * 0.1,
        ])

        stemi_badge = HeroMetricBadge("EKG RHYTHM", "STEMI (ELEVATED)", color="#EF4444", width=2.6, height=1.1).to_corner(UR, buff=0.35).scale(0.8)
        st_label = Text("ST Elevation (Injury Current)", font_size=13, color="#FCA5A5").move_to(RIGHT * 3.5 + UP * 1.25)

        self.play(
            Transform(normal_ecg, stemi_ecg),
            Transform(ecg_badge, stemi_badge),
            Write(st_label),
            run_time=2.5,
        )
        self.play(Circumscribe(st_label, color=RED), run_time=1.4)
        self.wait(2.2)

        # ------------------------------------------------------------------
        # 6. Sentence 2 (16.5s - 27.15s): Coagulative Necrosis & Infarction
        # ------------------------------------------------------------------
        caption2 = SafeCaptionZone("Without reperfusion within 20 minutes, irreversible coagulative necrosis occurs.")
        self.play(Transform(caption0, caption2), run_time=0.6)

        # Necrotic tissue darkening to dark obsidian/purple
        necrotic_block = RoundedRectangle(
            width=4.5,
            height=3.4,
            corner_radius=0.2,
            fill_color="#1E1B4B",
            fill_opacity=0.98,
            stroke_color="#475569",
            stroke_width=3.0,
        ).move_to(myo_block.get_center())
        infarction_stamp = Text("PERMANENT INFARCTION", font_size=18, color="#EF4444", weight="BOLD").move_to(necrotic_block.get_center() + DOWN * 0.2)
        warning_halo = GlowAura(necrotic_block, color="#EF4444", num_layers=3)

        self.play(
            Transform(myo_block, necrotic_block),
            FadeIn(warning_halo),
            Write(infarction_stamp),
            run_time=2.8,
        )
        self.play(Indicate(infarction_stamp, color="#FFFFFF"), run_time=1.5)
        self.wait(4.0)
