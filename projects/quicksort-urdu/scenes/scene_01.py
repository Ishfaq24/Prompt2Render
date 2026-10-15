from manim import *
from prompt2render.assets.mobjects import (
    ArrayGrid, HeroFocusStage, MetricBadge
)

class Scene01(Scene):
    def construct(self):
        # Title Band (English text in video)
        title = Text("Quick Sort: Divide & Conquer", font="Segoe UI", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # Unsorted array representation with Pivot element highlighted
        arr = ArrayGrid(values=[29, 10, 14, 37, 13], active_index=4)
        arr.shift(UP * 0.4)
        
        pivot_badge = MetricBadge(label="Pivot Element", value="13", status="good")
        pivot_badge.next_to(arr, DOWN, buff=0.8)

        self.play(FadeIn(arr), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(pivot_badge), run_time=0.8)
        self.wait(11.4)
