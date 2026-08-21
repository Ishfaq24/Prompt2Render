"""ablation_runner tests — the pure config/aggregation logic only. Running actual conditions
against a real project (LLM + matplotlib rendering) belongs to manual verification
(python tools/ablation_runner.py --slug hash-tables), not the offline test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from ablation_runner import CONDITIONS, _by_category, _condition_config


def test_four_conditions_cover_the_matrix():
    seen = {(c["spatial"], c["lifecycle"]) for c in CONDITIONS}
    assert seen == {(False, False), (True, False), (False, True), (True, True)}


def test_condition_config_forces_gates_off_and_toggles_enabled():
    base = {"verifier_spatial": {"gate_override": None}}
    cfg = _condition_config(base, spatial_on=True, lifecycle_on=False)
    assert cfg["verifier_spatial"]["enabled"] is True
    assert cfg["verifier_spatial"]["gate_override"] is False   # Phase A invariant
    assert cfg["verifier_lifecycle"]["enabled"] is False
    assert cfg["verifier_lifecycle"]["gate_override"] is False
    assert cfg["generator_code"]["enabled"] is True
    assert cfg["renderer_stills"]["enabled"] is True
    assert cfg["verifier_audio"]["enabled"] is False


def test_condition_config_does_not_mutate_base():
    base = {"verifier_spatial": {"enabled": False}}
    _condition_config(base, spatial_on=True, lifecycle_on=True)
    assert base["verifier_spatial"]["enabled"] is False


def test_by_category_counts():
    findings = [{"category": "SPATIAL"}, {"category": "SPATIAL"}, {"category": "AUDIO"}, {}]
    assert _by_category(findings) == {"SPATIAL": 2, "AUDIO": 1, "UNKNOWN": 1}
