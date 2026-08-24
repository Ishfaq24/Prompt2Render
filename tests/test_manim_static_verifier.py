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
        tab = MobjectTable([[Text("a")]], row_height=1, col_widths=[1], include_background=True)
        nl = NumberLine()
        box = SurroundingRectangle(nl.number_to_point(3.14))
        bad_text = Text("hello", include_background=True)
        bad_group = VGroup(corner=DL)
        bad_always = always_redraw(nl.c2p(1))
"""
    errors = validate_manim_source(code)
    assert len(errors) == 15
    assert any("imports other than 'manim', 'math', or 'numpy' are not allowed" in e for e in errors)
    assert any("print() is not allowed" in e for e in errors)
    assert any("Axes.get_x_label() does not accept 'font_size'" in e for e in errors)
    assert any("move_to() does not accept 'corner='" in e for e in errors)
    assert any("Code() does not accept 'theme='" in e for e in errors)
    assert any("Code() expects 'add_line_numbers=', not 'insert_line_numbers='" in e for e in errors)
    assert any("set_shadow() is deprecated" in e for e in errors)
    assert any("MobjectTable() does not accept 'row_height='" in e for e in errors)
    assert any("MobjectTable() does not accept 'col_widths='" in e for e in errors)
    assert any("MobjectTable() does not accept 'include_background='" in e for e in errors)
    assert any("SurroundingRectangle() requires a Mobject, but was passed coordinates from number_to_point()" in e for e in errors)
    assert any("Text() does not accept 'include_background='" in e for e in errors)
    assert any("VGroup() does not accept 'corner='" in e for e in errors)
    assert any("always_redraw() requires a Mobject, but was passed coordinates from c2p()" in e for e in errors)

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
        self.wait(1)
"""
    errors = validate_manim_source(code)
    assert any("contains scalar alpha * PI" in e for e in errors)


def test_manim_static_verifier_catches_unescaped_latex_special_chars():
    from prompt2render.scenes import validate_manim_source
    code = r'''
from manim import *
class Scene06(Scene):
    def construct(self):
        desc = MathTex(r"\text{Modular identities & } j\text{-invariant of } \mathbb{Q}")
        self.play(Write(desc))
        self.wait(1)
'''
    errors = validate_manim_source(code)
    assert any("unescaped '&'" in e for e in errors)


def test_manim_static_verifier_accepts_escaped_latex_ampersand():
    from prompt2render.scenes import validate_manim_source
    code = r'''
from manim import *
class Scene06(Scene):
    def construct(self):
        desc = MathTex(r"\text{Modular identities \& } j\text{-invariant of } \mathbb{Q}")
        self.play(Write(desc))
        self.wait(1)
'''
    errors = validate_manim_source(code)
    assert not errors


def test_manim_static_verifier_allows_ampersand_inside_align_environment():
    from prompt2render.scenes import validate_manim_source
    code = r'''
from manim import *
class Scene01(Scene):
    def construct(self):
        eq = MathTex(r"\begin{align} a &= b \\ c &= d \end{align}")
        self.play(Write(eq))
        self.wait(1)
'''
    errors = validate_manim_source(code)
    assert not errors


def test_manim_static_verifier_catches_unbalanced_braces():
    from prompt2render.scenes import validate_manim_source
    code = r'''
from manim import *
class Scene01(Scene):
    def construct(self):
        eq = MathTex(r"\frac{1}{2")
        self.play(Write(eq))
        self.wait(1)
'''
    errors = validate_manim_source(code)
    assert any("unbalanced braces" in e for e in errors)
