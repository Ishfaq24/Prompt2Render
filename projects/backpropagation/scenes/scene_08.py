from manim import *
import numpy as np

class Scene08(Scene):
    def construct(self):
        config.background_color = "#0B0F19"

        # 1. Title Band
        title = Text("Why Vanishing Gradients Kill Deep Networks", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.35)
        self.play(Write(title), run_time=1.0)

        # 2. Main Stage Container
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

        # 3. Left Side: Sigmoid Derivative Function
        axes_l = Axes(
            x_range=[-4.0, 4.0, 2.0],
            y_range=[0, 0.35, 0.1],
            x_length=5.0,
            y_length=2.8,
            axis_config={"color": "#64748B", "include_numbers": True, "font_size": 11}
        ).move_to(LEFT * 3.5 + UP * 0.1)

        sig_curve = axes_l.plot(
            lambda x: np.exp(-x) / ((1 + np.exp(-x)) ** 2),
            color="#38BDF8",
            stroke_width=3.2
        )

        sig_lbl = MathTex(r"\sigma^{\prime}(z) = \sigma(z)(1 - \sigma(z))", font_size=15, color="#7DD3FC").next_to(axes_l, UP, buff=0.15)

        peak_pt = axes_l.c2p(0, 0.25)
        peak_dot = Dot(peak_pt, radius=0.09, color="#F59E0B")
        peak_badge = RoundedRectangle(corner_radius=0.1, width=2.4, height=0.46, color="#F59E0B", stroke_width=1.2, fill_color="#451A03", fill_opacity=0.9).next_to(peak_dot, UP, buff=0.16)
        peak_text = MathTex(r"\text{Max Value } = 0.25", font_size=13, color="#FDE68A").move_to(peak_badge.get_center())
        peak_callout = VGroup(peak_badge, peak_text)

        left_group = VGroup(axes_l, sig_curve, sig_lbl, peak_dot, peak_callout)

        # 4. Right Side: 8-Layer Exponential Gradient Attenuation Bar Chart
        chart_center = RIGHT * 3.4 + UP * 0.3
        chart_title = Text("Gradient Magnitude Across 8 Layers", font_size=13, color="#C7D2FE", weight=BOLD).move_to(chart_center + UP * 1.5)

        # 8 layers: Layer 8 (output) to Layer 1 (input)
        mags = [0.20 * (0.25 ** (7 - i)) for i in range(8)]
        # Normalize for display heights
        max_h = 2.2
        bar_w = 0.42
        spacing = 0.60
        start_x = chart_center[0] - (8 * spacing) / 2 + spacing / 2

        bars = []
        bar_lbls = []
        for i in range(8):
            h = max(max_h * (mags[i] / 0.20), 0.04)
            x_pos = start_x + i * spacing
            y_pos = chart_center[1] - 1.0 + h / 2
            
            # Layer color: Layer 8 green, decaying to purple/red
            col = "#10B981" if i == 7 else ("#818CF8" if i >= 4 else "#F43F5E")
            b = Rectangle(width=bar_w, height=h, color=col, fill_color=col, fill_opacity=0.85, stroke_width=1.2).move_to(np.array([x_pos, y_pos, 0]))
            lbl = Text(f"L{i+1}", font_size=10, color="#94A3B8").next_to(b, DOWN, buff=0.1)
            bars.append(b)
            bar_lbls.append(lbl)

        chart_baseline = Line(
            np.array([start_x - spacing/2, chart_center[1] - 1.0, 0]),
            np.array([start_x + 7.5 * spacing, chart_center[1] - 1.0, 0]),
            color="#475569",
            stroke_width=1.5
        )

        right_group = VGroup(chart_title, chart_baseline, *bars, *bar_lbls)

        # [0.0 - 5.2s] Intro to Vanishing Gradient
        intro_badge = RoundedRectangle(corner_radius=0.15, width=9.2, height=0.6, color="#EF4444", stroke_width=1.5, fill_color="#450A0A", fill_opacity=0.9).move_to(DOWN * 1.8)
        intro_text = Text("The Vanishing Gradient Problem: Fundamental Bottleneck of Deep Networks", font_size=12, color="#FCA5A5", weight=BOLD).move_to(intro_badge.get_center())
        intro_group = VGroup(intro_badge, intro_text)

        self.play(FadeIn(intro_group, shift=UP * 0.15), run_time=1.5)
        self.wait(3.7)

        # [5.5 - 10.8s] Derivative recurrence left plot
        self.play(
            FadeOut(intro_group),
            Create(axes_l), Create(sig_curve), Write(sig_lbl),
            run_time=2.2
        )
        self.wait(3.1)

        # [11.1 - 18.3s] Peak value = 0.25 highlight
        self.play(
            Create(peak_dot),
            FadeIn(peak_callout, shift=UP * 0.15),
            run_time=1.5
        )
        self.wait(5.7)

        # [18.7 - 28.5s] 8-Layer Multiplicative Shrinkage: (0.25)^8 ~ 0.000015
        decay_card = RoundedRectangle(corner_radius=0.12, width=9.4, height=0.8, color="#F59E0B", stroke_width=1.5, fill_color="#451A03", fill_opacity=0.92).move_to(DOWN * 1.8)
        decay_text = MathTex(
            r"\text{8-Layer Chain: } \nabla_{\text{Layer 1}} \le (0.25)^8 \approx 0.000015 \quad (\text{Shrinkage Factor } 65{,}000\times)",
            font_size=17,
            color="#FDE68A"
        ).move_to(decay_card.get_center())
        decay_group = VGroup(decay_card, decay_text)

        self.play(
            FadeIn(right_group),
            FadeIn(decay_group, shift=UP * 0.2),
            run_time=2.0
        )
        self.wait(7.8)

        # [28.9 - 34.4s] Layer 8 has signal, Layer 1 has virtually none
        self.play(
            Indicate(bars[7], color="#34D399", scale_factor=1.15),
            run_time=1.8
        )
        self.play(
            Indicate(bars[0], color="#EF4444", scale_factor=1.4),
            run_time=1.8
        )
        self.wait(1.9)

        # [34.7 - 41.3s] Error signal fading out before reaching earliest layers
        wave_dot = Dot(bars[7].get_top(), radius=0.1, color="#10B981")
        self.play(FadeIn(wave_dot), run_time=0.3)
        # Animate traveling backwards across bars, shrinking and fading
        self.play(
            wave_dot.animate.move_to(bars[4].get_top()).set_color("#818CF8").scale(0.7),
            run_time=1.8
        )
        self.play(
            wave_dot.animate.move_to(bars[0].get_top()).set_color("#EF4444").scale(0.3).set_opacity(0),
            run_time=2.0
        )
        self.wait(2.5)

        # [41.7 - 44.1s] First layers stop learning entirely (Non-overlapping pill safely placed!)
        stopped_pill = RoundedRectangle(corner_radius=0.1, width=2.6, height=0.45, color="#EF4444", stroke_width=1.2, fill_color="#2A0812", fill_opacity=0.95).move_to(bars[0].get_center() + UP * 1.1 + RIGHT * 0.4)
        stopped_text = Text("STOPPED LEARNING", font_size=9, color="#FDA4AF", weight=BOLD).move_to(stopped_pill.get_center())
        stopped_group = VGroup(stopped_pill, stopped_text)

        self.play(FadeIn(stopped_group, shift=UP * 0.1), run_time=1.0)
        self.wait(1.4)

        # [44.5 - 57.4s] Historical bottleneck (1986-2012) and solution preview
        self.play(FadeOut(decay_group), run_time=0.8)

        hist_card = RoundedRectangle(corner_radius=0.15, width=9.6, height=0.85, color="#EF4444", stroke_width=1.5, fill_color="#2A0812", fill_opacity=0.95).move_to(DOWN * 1.8)
        hist_title = Text("Deep Learning Bottleneck (Pre-2012): Deep Networks Performed No Better Than Shallow Models", font_size=11, color="#FDA4AF", weight=BOLD).move_to(hist_card.get_center())
        hist_group = VGroup(hist_card, hist_title)

        self.play(FadeIn(hist_group, shift=UP * 0.15), run_time=1.5)

        # Keep scene active with sequential layer highlights until end
        for k in range(8):
            self.play(bars[k].animate.set_opacity(0.5), run_time=0.25)
            self.play(bars[k].animate.set_opacity(0.85), run_time=0.25)
        self.wait(6.6)