"""Demonstration scene highlighting Cinematic Direction, Neuro-Symbolic Traces, and Visual Polish."""

from manim import *
from prompt2render.assets.mobjects import AutoHStack, SafeCaptionZone
from prompt2render.cinematic import GlowAura, HeroMetricBadge, focus_on, reset_frame
from prompt2render.symbolic_engine import trace_sorting


class BubbleSortCinematicScene(MovingCameraScene):
    def construct(self):
        self.camera.background_color = "#0B0F19"

        # 1. Title & Metric Badge
        title = Text("Bubble Sort: The Adjacent Swap", font_size=32, color=WHITE).to_edge(UP, buff=0.35)
        complexity_badge = HeroMetricBadge("COMPLEXITY", "O(n²)", color=RED, width=2.6, height=1.1).to_corner(UR, buff=0.4).scale(0.8)
        self.play(FadeIn(title), FadeIn(complexity_badge), run_time=0.8)

        # 2. Deterministic Symbolic Trace
        initial_vals = [5, 1, 4, 2, 8]
        steps = trace_sorting(initial_vals, "bubble")

        # 3. Create visual boxes for numbers
        boxes = VGroup(*[
            VGroup(
                RoundedRectangle(
                    width=1.2,
                    height=1.2,
                    corner_radius=0.15,
                    fill_color="#1E293B",
                    fill_opacity=0.9,
                    stroke_color="#38BDF8",
                    stroke_width=2.5,
                ),
                Text(str(val), font_size=28, color=WHITE),
            ) for val in initial_vals
        ]).arrange(RIGHT, buff=0.35).move_to(UP * 0.3)

        self.play(Create(boxes), run_time=1.0)

        # 4. Cinematic Zoom-In on the first comparison
        self.play(focus_on(self.camera.frame, boxes[0:2], scale=0.7), run_time=1.0)
        glow = GlowAura(boxes[0], color=YELLOW, num_layers=3)
        self.play(FadeIn(glow), run_time=0.4)
        self.play(Indicate(boxes[0][1]), Indicate(boxes[1][1]), run_time=0.6)

        # 5. Swap 5 and 1
        pos0 = boxes[0].get_center()
        pos1 = boxes[1].get_center()
        self.play(
            boxes[0].animate.move_to(pos1),
            boxes[1].animate.move_to(pos0),
            FadeOut(glow),
            run_time=0.8,
        )

        # 6. Reset camera frame to full view
        self.play(reset_frame(self.camera.frame), run_time=0.8)

        # 7. Safe caption zone
        caption = SafeCaptionZone("Compare adjacent items: 5 > 1, so swap them into position.")
        self.play(FadeIn(caption), run_time=0.5)
        self.wait(1.0)
