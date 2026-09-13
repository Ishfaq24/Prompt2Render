"""Tests for the semantic renderer routing logic."""
from prompt2render.topic_router import brief_suggests_motion


def test_bubble_sort_routes_to_manim():
    assert brief_suggests_motion("Animate bubble sort on an array of integers") is True


def test_merge_sort_routes_to_manim():
    assert brief_suggests_motion("Show merge sort splitting and merging sub-arrays") is True


def test_neural_network_routes_to_manim():
    assert brief_suggests_motion("Forward propagation through a neural network") is True


def test_bfs_routes_to_manim():
    assert brief_suggests_motion("Breadth-first search traversal on a graph") is True


def test_static_bit_ops_stays_matplotlib():
    assert brief_suggests_motion("Show bit manipulation and register layout") is False


def test_static_flowchart_stays_matplotlib():
    assert brief_suggests_motion("Flowchart of the TCP handshake") is False


def test_memory_layout_stays_matplotlib():
    assert brief_suggests_motion("Memory layout diagram for cache mapping") is False


def test_generic_explanation_stays_matplotlib():
    assert brief_suggests_motion("Explain the concept of recursion") is False


def test_dijkstra_routes_to_manim():
    assert brief_suggests_motion("Dijkstra shortest path algorithm step by step") is True


def test_gradient_descent_routes_to_manim():
    assert brief_suggests_motion("Gradient descent loss minimisation with weight update") is True
