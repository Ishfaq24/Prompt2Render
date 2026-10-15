from manim import *
from prompt2render.assets.mobjects import (
    SplitStage, ConfigCodeCard, MetricBadge
)

class Scene02(Scene):
    def construct(self):
        # Title Band
        title = Text("Partitioning Around the Pivot", font="Segoe UI", font_size=26, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # Split comparison: Elements < Pivot vs Elements >= Pivot
        left_card = ConfigCodeCard(
            code_lines=["[10]", "# Elements < Pivot (13)"],
            title="Left Partition",
            width=5.0
        )
        right_card = ConfigCodeCard(
            code_lines=["[29, 14, 37]", "# Elements > Pivot (13)"],
            title="Right Partition",
            width=5.0
        )
        
        split = SplitStage(left=left_card, right=right_card, left_title="< 13", right_title="> 13", divider=True)
        split.shift(UP * 0.1)

        pivot_badge = MetricBadge(label="Pivot Position Fixed", value="Index 1", status="good")
        pivot_badge.to_edge(DOWN, buff=0.6)

        self.play(FadeIn(split), run_time=1.2)
        self.wait(1.5)
        self.play(FadeIn(pivot_badge), run_time=0.8)
        self.wait(10.7)
