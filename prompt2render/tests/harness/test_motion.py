"""Phase 3: the 5 motion ops added to close the "sparse-scene" vocabulary
gap (docs/ARCHITECTURE_AUDIT.md SS17) -- NextTo, Circumscribe, GrowArrow,
Uncreate, Rotate. The original 7 ops are already covered indirectly by
test_planner_llm_motion.py/test_verifier_storyboard_motion.py; this file is
motion.py's own dedicated test, since it has none today despite being the
vocabulary's single source of truth.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.motion import MOTION_OPS, validate_motion_ops


def test_next_to_requires_target_and_anchor():
    assert validate_motion_ops([{"op": "NextTo", "target": "b", "anchor": "a"}]) == []
    errors = validate_motion_ops([{"op": "NextTo", "target": "b"}])
    assert any("missing required key" in e for e in errors)


def test_circumscribe_requires_target():
    assert validate_motion_ops([{"op": "Circumscribe", "target": "circle"}]) == []
    errors = validate_motion_ops([{"op": "Circumscribe"}])
    assert any("missing required key" in e for e in errors)


def test_grow_arrow_requires_target():
    assert validate_motion_ops([{"op": "GrowArrow", "target": "vector"}]) == []
    errors = validate_motion_ops([{"op": "GrowArrow"}])
    assert any("missing required key" in e for e in errors)


def test_uncreate_requires_target():
    assert validate_motion_ops([{"op": "Uncreate", "target": "old_node"}]) == []
    errors = validate_motion_ops([{"op": "Uncreate"}])
    assert any("missing required key" in e for e in errors)


def test_rotate_requires_target():
    assert validate_motion_ops([{"op": "Rotate", "target": "square"}]) == []
    errors = validate_motion_ops([{"op": "Rotate"}])
    assert any("missing required key" in e for e in errors)


def test_new_ops_still_enforce_identifier_safety():
    errors = validate_motion_ops(
        [{"op": "NextTo", "target": "not an identifier", "anchor": "a"}]
    )
    assert any("must be a valid Python identifier" in e for e in errors)


def test_vocabulary_has_exactly_twelve_ops():
    assert len(MOTION_OPS) == 12
