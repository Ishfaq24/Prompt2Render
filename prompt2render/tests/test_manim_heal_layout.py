"""Unit tests for AST Manim code healer (auto-spacing, collision prevention, caption clamping)."""

import pytest
from prompt2render.scenes import heal_manim_source


def test_heal_manim_injects_new_stage_imports():
    code = """
class Scene01(Scene):
    def construct(self):
        stack = AutoVStack()
        card = AnnotatedCard("Test")
"""
    healed = heal_manim_source(code)
    assert "from prompt2render.assets.mobjects import AutoVStack, AnnotatedCard" in healed


def test_heal_parallel_down_anchoring_collision():
    code = """
class Scene01(Scene):
    def construct(self):
        server = ServerNode("Web")
        terminal = ConfigCodeCard(code_lines=["ls"])
        badge = MetricBadge(label="OK")
        terminal.next_to(server, DOWN, buff=0.2)
        badge.next_to(server, DOWN, buff=0.4)
"""
    healed = heal_manim_source(code)
    # The second next_to should be re-anchored to terminal instead of server
    assert "badge.next_to(terminal, DOWN, buff=0.3)" in healed


def test_heal_caption_zone_trespass():
    code = """
class Scene01(Scene):
    def construct(self):
        warning_box = Rectangle()
        warning_box.move_to((0, -3.2, 0))
        caption = Text("This is subtitle")
        caption.move_to((0, -3.15, 0))
"""
    healed = heal_manim_source(code)
    # warning_box should be clamped to y = -2.2
    assert "warning_box.move_to((0, -2.2, 0))" in healed
    # caption should remain untouched at -3.15
    assert "caption.move_to((0, -3.15, 0))" in healed


def test_heal_long_text_overflow():
    code = """
class Scene01(Scene):
    def construct(self):
        t = Text("This is an extremely long single-line explanation sentence that would otherwise overflow canvas width margins")
"""
    healed = heal_manim_source(code)
    assert ".scale_to_fit_width(12.0)" in healed


def test_heal_camera_frame_promotes_to_moving_camera_scene():
    code = """
class Scene01(Scene):
    def construct(self):
        self.play(focus_on(self.camera.frame, target))
"""
    healed = heal_manim_source(code)
    assert "class Scene01(MovingCameraScene):" in healed


def test_heal_unicode_math_symbols_in_mathtex():
    code = 'formula = MathTex(r"\\min_{θ \\in ℝ^d} \\mathcal{L}(θ)")\ncomp = Tex("x × y ≤ z")'
    healed = heal_manim_source(code)
    assert r"\theta" in healed
    assert r"\mathbb{R}" in healed
    assert r"\times" in healed
    assert r"\le" in healed
    assert "θ" not in healed
    assert "ℝ" not in healed
    assert "×" not in healed
    assert "≤" not in healed


def test_generator_manim_plugin_clean_applies_healing():
    from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin
    plugin = GeneratorManimPlugin()
    raw = """
```python
class Scene02(Scene):
    def construct(self):
        self.play(reset_frame(self.camera.frame))
```
"""
    cleaned = plugin._clean_generated_code(raw)
    assert "class Scene02(MovingCameraScene):" in cleaned

