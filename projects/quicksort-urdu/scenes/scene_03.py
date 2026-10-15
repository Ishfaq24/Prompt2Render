from manim import *
from prompt2render.assets.mobjects import (
    BenchmarkStage, MetricBadge
)

class Scene03(Scene):
    def construct(self):
        # Title Band
        title = Text("Recursive Sorting & Complexity Analysis", font="Segoe UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # Performance metrics
        b1 = MetricBadge(label="Best Case", value="O(n log n)", status="good")
        b2 = MetricBadge(label="Average Case", value="O(n log n)", status="good")
        b3 = MetricBadge(label="Worst Case", value="O(n^2)", status="warning")
        
        bench = BenchmarkStage(cards=[b1, b2, b3], title="Time Complexity")
        bench.shift(UP * 0.2)

        summary_note = Text("In-place recursive partitioning with logarithmic height", font="Segoe UI", font_size=18, color=GRAY_B)
        summary_note.to_edge(DOWN, buff=0.8)

        self.play(FadeIn(bench), run_time=1.2)
        self.wait(1.5)
        self.play(FadeIn(summary_note), run_time=0.8)
        self.wait(10.5)
