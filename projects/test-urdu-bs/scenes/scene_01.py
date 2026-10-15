# [Prompt2Render Multilingual] Lang: ur, Script: Arab, Direction: rtl, Font: Arial
from manim import *
from prompt2render.assets.mobjects import (
    FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
    ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
    ArrayGrid, FormulaCard, KeyBadge, CaptionDock, P2RText
)

class Scene01(Scene):
    def construct(self):
        # 1. Title Band
        title = Text("Explain binary search in Urdu", font="Arial", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # 2. Main Hero Stage Visualization

        grid = ArrayGrid(values=[2, 4, 8, 16, 32], active_index=2)
        grid.shift(UP * 0.4)
        self.play(FadeIn(grid), run_time=1.0)
        self.wait(1.0)

        # 3. Caption Dock in Lower Safe Zone
        caption = CaptionDock("Welcome. Today we explore Explain binary search\nin Urdu.")
        self.play(FadeIn(caption), run_time=0.6)
        self.wait(2.0)
