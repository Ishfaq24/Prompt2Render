"""Tests for algorithm widget Mobjects (without rendering)."""
import pytest


def test_stack_initial_values():
    try:
        from prompt2render.assets.mobjects.algorithm_widgets import StackMobject
    except ImportError as e:
        pytest.skip(f"Manim not available: {e}")
    stack = StackMobject(initial_values=[1, 2, 3])
    assert stack._values == [1, 2, 3]


def test_stack_push_appends_value():
    try:
        from prompt2render.assets.mobjects.algorithm_widgets import StackMobject
    except ImportError as e:
        pytest.skip(f"Manim not available: {e}")
    stack = StackMobject(initial_values=[1, 2])
    stack.push(3)
    assert 3 in stack._values


def test_stack_pop_removes_top():
    try:
        from prompt2render.assets.mobjects.algorithm_widgets import StackMobject
    except ImportError as e:
        pytest.skip(f"Manim not available: {e}")
    stack = StackMobject(initial_values=[1, 2, 3])
    stack.pop()
    assert 3 not in stack._values


def test_queue_initial_values():
    try:
        from prompt2render.assets.mobjects.algorithm_widgets import QueueMobject
    except ImportError as e:
        pytest.skip(f"Manim not available: {e}")
    q = QueueMobject(initial_values=[10, 20, 30])
    assert q._values == [10, 20, 30]


def test_neural_3d_layout_solver_accessible():
    from prompt2render.symbolic_engine import compute_neural_network_layout_3d
    result = compute_neural_network_layout_3d([3, 4, 2])
    assert "layers" in result
    assert "edges" in result
