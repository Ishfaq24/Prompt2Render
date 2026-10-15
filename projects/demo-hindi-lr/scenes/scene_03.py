# [Prompt2Render Multilingual] Lang: hi, Script: default, Direction: ltr, Font: Nirmala UI
from manim import *
from prompt2render.assets.mobjects import (
    FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
    ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
    ArrayGrid, FormulaCard, KeyBadge, CaptionDock, P2RText
)

class Scene03(Scene):
    def construct(self):
        # 1. Title Band
        title = Text("सारांश और मुख्य बातें", font="Nirmala UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # 2. Main Hero Stage Visualization

        b1 = MetricBadge(label="Time", value="O(log n)", status="good")
        b2 = MetricBadge(label="Space", value="O(1)", status="good")
        b3 = MetricBadge(label="Status", value="Optimal", status="good")
        stage = BenchmarkStage(cards=[b1, b2, b3], title="Performance Analysis")
        self.play(FadeIn(stage))
        self.wait(1.0)

        # 3. Caption Dock in Lower Safe Zone
        caption = CaptionDock("लीनियर रिग्रेशन और ग्रेडिएंट डिसेंट के मूलभूत\nगुणों का संक्षेप में पुनरावलोकन करना।")
        self.play(FadeIn(caption), run_time=0.6)
        self.wait(2.0)
