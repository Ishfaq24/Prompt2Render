# [Prompt2Render Multilingual] Lang: hi, Script: default, Direction: ltr, Font: Nirmala UI
from manim import *
from prompt2render.assets.mobjects import (
    FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
    ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
    ArrayGrid, FormulaCard, KeyBadge, CaptionDock, P2RText
)

class Scene02(Scene):
    def construct(self):
        # 1. Title Band
        title = Text("कोर मैकेनिक्स", font="Nirmala UI", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.45)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)

        # 2. Main Hero Stage Visualization

        # Flow stage for process sequence
        node1 = ServerNode(name="Step 1", subtext="Input Data", status="active")
        node2 = ServerNode(name="Step 2", subtext="Processing", status="active")
        node3 = ServerNode(name="Step 3", subtext="Result", status="good")
        stage = FlowStage(nodes=[node1, node2, node3], buff=0.8)
        stage.shift(UP * 0.2)
        self.play(FadeIn(stage))
        dot, target = stage.pulse_signal(0, 1)
        self.play(dot.animate.move_to(target), run_time=1.0)
        self.wait(1.0)

        # 3. Caption Dock in Lower Safe Zone
        caption = CaptionDock("आइए समझते हैं कि रैखिक प्रतिगमन (Linear\nRegression) और ग्रेडिएंट डिसेंट (Gradient\nDescent) चरण-दर-चरण कैसे काम करते हैं।")
        self.play(FadeIn(caption), run_time=0.6)
        self.wait(2.0)
