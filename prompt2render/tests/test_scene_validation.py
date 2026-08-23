from __future__ import annotations

import json

import pytest

from prompt2render import scenekit as k
from prompt2render.scenes import trace_scene_source, validate_scene_source


def test_hanoi_rejects_four_pegs_before_rendering():
    source = '''
def states():
    def s01(ax):
        k.hanoi(ax, [[3, 2, 1], [], [], []])
    return [("s01", 0, s01)]
'''
    errors = validate_scene_source(source, max_cue=0)
    assert any("exactly three pegs" in error for error in errors)


def test_hanoi_illegal_state_requires_explicit_marker():
    unlabeled = '''
def states():
    def s01(ax):
        k.hanoi(ax, [[1, 2], [], []])
    return [("s01", 0, s01)]
'''
    labeled = '''
def states():
    def s01(ax):
        k.title(ax, "ILLEGAL MOVE", color=k.BAD)
        k.hanoi(ax, [[1, 2], [], []])
    return [("s01", 0, s01)]
'''
    assert any("larger disk" in error for error in validate_scene_source(unlabeled, 0))
    assert not any("larger disk" in error for error in validate_scene_source(labeled, 0))


def test_generic_data_contracts_are_checked():
    source = '''
def states():
    def s01(ax):
        k.grid(ax, [[1, 2], [3]])
        k.table(ax, [("a",), ("b", "c")])
        k.array(ax, [1, 2], lo=9)
    return [("s01", 0, s01)]
'''
    errors = validate_scene_source(source, 0)
    assert any("grid rows" in error for error in errors)
    assert any("table rows" in error for error in errors)
    assert any("array lo index" in error for error in errors)


def test_trace_is_json_serializable_and_records_all_primitives():
    source = '''
def states():
    def s01(ax):
        k.title(ax, "Example")
        k.array(ax, [1, 2, 3], y=5, lo=0, hi=2)
    return [("s01", 0, s01)]
'''
    trace = trace_scene_source(source)
    json.dumps(trace)
    assert trace["primitive_counts"] == {"title": 1, "array": 1}
    assert [call["primitive"] for call in trace["calls"]] == ["title", "array"]
    assert trace["calls"][1]["keywords"]["lo"] == 0


def test_hanoi_rejects_invalid_input_without_adding_artists():
    fig, ax = k.canvas()
    before = (len(ax.lines), len(ax.patches), len(ax.texts))
    with pytest.raises(ValueError, match="exactly three pegs"):
        k.hanoi(ax, [[3, 2, 1], [], [], []])
    after = (len(ax.lines), len(ax.patches), len(ax.texts))
    k.close(fig)
    assert after == before
