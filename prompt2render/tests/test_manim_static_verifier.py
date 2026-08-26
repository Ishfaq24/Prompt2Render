def test_manim_static_verifier_catches_invalid_imports_and_apis():
    from prompt2render.scenes import validate_manim_source
    
    code = """
from manim import *
import os
class Scene01(Scene):
    def construct(self):
        print("hello")
        ax = Axes()
        ax.get_x_label("X", font_size=20)
        c = Circle()
        c.move_to(ORIGIN, corner=DL)
        code = Code(code_string="x=1", theme="monokai", insert_line_numbers=True)
        c.set_shadow(blur=0.5)
"""
    errors = validate_manim_source(code)
    assert any("imports other than 'manim', 'math', or 'numpy' are not allowed" in e for e in errors)
    assert any("print() is not allowed" in e for e in errors)
    assert any("Axes.get_x_label() does not accept 'font_size'" in e for e in errors)
    assert any("move_to() does not accept 'corner='" in e for e in errors)
    assert any("Code() does not accept 'theme='" in e for e in errors)
    assert any("Code() expects 'add_line_numbers=', not 'insert_line_numbers='" in e for e in errors)
    assert any("set_shadow() is deprecated" in e for e in errors)

def test_manim_static_verifier_accepts_valid_code():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
import math
import numpy as np
class Scene01(Scene):
    def construct(self):
        c = Circle()
        c.move_to(UL)
        code = Code(code_string="x=1", language="python", add_line_numbers=True)
        self.play(Create(c))
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert not errors

def test_manim_static_verifier_catches_nested_scalar_endpoint():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        line = Line()
        start_point = ORIGIN
        number_line = NumberLine()
        self.play(UpdateFromAlphaFunc(line, lambda m, alpha: m.put_start_and_end_on(start_point, number_line.number_to_point(alpha * PI))))
"""
    errors = validate_manim_source(code)
    assert any("contains scalar alpha * PI" in e for e in errors)

def test_manim_static_verifier_catches_hallucinated_identifiers():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        c = Circle(color=RED_M)
        self.play(c.animate.shift(UP), rate_func=ease_out_sine)
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("'RED_M' is not defined" in e for e in errors)
    assert any("'ease_out_sine' is not defined" in e for e in errors)

def test_manim_static_verifier_catches_invalid_kwargs_via_introspection():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        code = Code(code_string="x=1", language="python", font_size=16)
        label = Text("hi")
        label.next_to(code, DOWN, align_to_left=True)
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("Code() does not accept 'font_size='" in e for e in errors)
    assert any("next_to() does not accept 'align_to_left='" in e for e in errors)


def test_manim_static_verifier_catches_pre_0_21_code_kwargs():
    """Manim 0.21 renamed Code()'s code=/style= kwargs; both must be flagged."""
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        snippet = Code(code="x = 1", style="monokai")
        self.play(Create(snippet))
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("Code() expects 'code_string=', not 'code='" in e for e in errors)
    assert any("Code() expects 'formatter_style=', not 'style='" in e for e in errors)


def test_manim_static_verifier_accepts_0_21_code_api():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        snippet = Code(
            code_string="x = 1",
            language="python",
            formatter_style="monokai",
            add_line_numbers=True,
            paragraph_config={"font_size": 18},
        )
        self.play(Create(snippet))
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert not errors


# ---------------------------------------------------------------------------
# F15 cleanup: checks merged in from the formerly-separate, duplicate
# scenes._validate_manim_source (scenes.py's own docstring at the merge site
# explains why) -- these previously had zero coverage under the public
# validate_manim_source name.
# ---------------------------------------------------------------------------

def test_manim_static_verifier_catches_scenekit_primitive_in_manim_mode():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        k.circle(self, "x", 0, 0)
        self.play(Create(Circle()))
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("Scenekit k.circle() found in Manim mode" in e for e in errors)


def test_manim_static_verifier_requires_exactly_one_scene_class():
    from prompt2render.scenes import validate_manim_source

    no_scene = """
from manim import *
class NotAScene:
    def construct(self):
        pass
"""
    assert any(
        "no class inheriting from Scene was generated" in e
        for e in validate_manim_source(no_scene)
    )

    two_scenes = """
from manim import *
class Scene01(Scene):
    def construct(self):
        self.play(Create(Circle()))
        self.wait(1)
class Scene02(Scene):
    def construct(self):
        self.play(Create(Circle()))
        self.wait(1)
"""
    assert any(
        "generate exactly one main Scene subclass" in e
        for e in validate_manim_source(two_scenes)
    )


def test_manim_static_verifier_requires_construct_method():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def setup(self):
        pass
"""
    errors = validate_manim_source(code)
    assert any("Scene01 must implement construct(self)" in e for e in errors)


def test_manim_static_verifier_requires_self_play():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        c = Circle()
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("scene contains no self.play() calls" in e for e in errors)


def test_manim_static_verifier_forbids_states_function():
    from prompt2render.scenes import validate_manim_source
    code = """
from manim import *
class Scene01(Scene):
    def construct(self):
        self.play(Create(Circle()))
        self.wait(1)

def states():
    pass
"""
    errors = validate_manim_source(code)
    assert any("states() is forbidden in Manim mode" in e for e in errors)
