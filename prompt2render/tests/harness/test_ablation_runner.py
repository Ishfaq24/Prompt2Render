"""ablation_runner tests — the pure config/aggregation logic only. Running actual conditions
against a real project (LLM + matplotlib rendering) belongs to manual verification
(python tools/ablation_runner.py --slug hash-tables), not the offline test suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from ablation_runner import CONDITIONS, _by_category, _catch_rate, _condition_config


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
    """F16: findings must split by status, not just be flat-counted -- a
    category with 5 passes and one with 5 fails used to report the
    identical number, making catch rate uncomputable from the output."""
    findings = [
        {"category": "SPATIAL", "status": "fail"},
        {"category": "SPATIAL", "status": "pass"},
        {"category": "AUDIO", "status": "warn"},
        {},
    ]
    assert _by_category(findings) == {
        "SPATIAL": {"pass": 1, "warn": 0, "fail": 1, "unknown": 0},
        "AUDIO": {"pass": 0, "warn": 1, "fail": 0, "unknown": 0},
        "UNKNOWN": {"pass": 0, "warn": 0, "fail": 0, "unknown": 1},
    }


def test_by_category_unrecognized_status_counts_as_unknown():
    findings = [{"category": "SPATIAL", "status": "something_else"}]
    assert _by_category(findings)["SPATIAL"]["unknown"] == 1


def test_catch_rate_computes_fraction_caught_per_condition():
    rows = [
        {
            "condition": {"spatial": True, "lifecycle": False},
            "pre_render_findings_by_category": {
                "SPATIAL": {"pass": 1, "warn": 0, "fail": 1, "unknown": 0},
            },
        },
        {
            "condition": {"spatial": True, "lifecycle": False},
            "pre_render_findings_by_category": {
                "SPATIAL": {"pass": 2, "warn": 0, "fail": 0, "unknown": 0},
            },
        },
    ]
    rate = _catch_rate(rows)
    assert rate == {"spatial=True_lifecycle=False": 0.25}  # 1 caught of 4 total


def test_catch_rate_empty_condition_is_zero():
    rows = [
        {
            "condition": {"spatial": False, "lifecycle": False},
            "pre_render_findings_by_category": {},
        }
    ]
    assert _catch_rate(rows) == {"spatial=False_lifecycle=False": 0.0}
