"""Unit tests for visual_state diff and model routing/fallback telemetry."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness import model_routing, visual_state


# ------------------------------------------------------------ visual diff ---

def test_visual_diff_flags_frame_loss():
    parent = {"frame_count": 4, "state_names": ["a", "b", "c", "d"], "audit_warnings": 0}
    candidate = {"frame_count": 2, "state_names": ["a", "b"], "audit_warnings": 0}

    diff = visual_state.visual_diff(parent, candidate)

    assert diff["comparable"] is True
    assert diff["regression_suspected"] is True
    assert diff["frame_count_delta"] == -2
    assert diff["removed_states"] == ["c", "d"]


def test_visual_diff_accepts_stable_revision():
    parent = {"frame_count": 3, "state_names": ["a", "b", "c"], "audit_warnings": 1}
    candidate = {"frame_count": 3, "state_names": ["a", "b", "c"], "audit_warnings": 1}

    diff = visual_state.visual_diff(parent, candidate)

    assert diff["comparable"] is True
    assert diff["regression_suspected"] is False
    assert diff["flags"] == []


def test_visual_diff_flags_warning_growth():
    parent = {"frame_count": 2, "state_names": ["a", "b"], "audit_warnings": 0}
    candidate = {"frame_count": 2, "state_names": ["a", "b"], "audit_warnings": 3}

    diff = visual_state.visual_diff(parent, candidate)

    assert diff["regression_suspected"] is True
    assert diff["warning_delta"] == 3


def test_visual_diff_missing_inputs_not_comparable():
    diff = visual_state.visual_diff(None, {"frame_count": 1})

    assert diff["comparable"] is False
    assert diff["regression_suspected"] is False


def test_visual_diff_flags_lost_clip():
    parent = {"frame_count": 1, "state_names": [], "has_clip": True, "has_preview": True}
    candidate = {"frame_count": 1, "state_names": [], "has_clip": False, "has_preview": False}

    diff = visual_state.visual_diff(parent, candidate)

    assert diff["regression_suspected"] is True
    assert "rendered clip lost" in diff["flags"]


# ----------------------------------------------------------- model routing ---

def test_role_env_var_names():
    assert model_routing.model_env_for("planner") == "P2R_PLANNER_MODEL"
    assert model_routing.model_env_for("generator") == "P2R_GENERATOR_MODEL"
    assert model_routing.model_env_for("repair") == "P2R_REPAIR_MODEL"
    assert model_routing.model_env_for("verifier") == "P2R_VERIFIER_MODEL"
    assert model_routing.model_env_for("semantic_verifier") == "P2R_SEMANTIC_VERIFIER_MODEL"
    assert model_routing.model_env_for("visual_verifier") == "P2R_VISUAL_VERIFIER_MODEL"
    # Unknown roles fall back to the shared env var.
    assert model_routing.model_env_for("unknown") == "P2R_SCENE_MODEL"


def test_effective_model_env_prefers_role(monkeypatch):
    monkeypatch.setenv("P2R_REPAIR_MODEL", "model-repair")
    monkeypatch.setenv("P2R_SCENE_MODEL", "model-shared")

    assert model_routing.effective_model_env("repair") == "P2R_REPAIR_MODEL"


def test_effective_model_env_falls_back_to_shared(monkeypatch):
    monkeypatch.delenv("P2R_REPAIR_MODEL", raising=False)
    monkeypatch.setenv("P2R_SCENE_MODEL", "model-shared")

    assert model_routing.effective_model_env("repair") == "P2R_SCENE_MODEL"


def test_effective_model_env_unset(monkeypatch):
    monkeypatch.delenv("P2R_REPAIR_MODEL", raising=False)
    monkeypatch.delenv("P2R_SCENE_MODEL", raising=False)

    assert model_routing.effective_model_env("repair") == "P2R_REPAIR_MODEL"


def test_resolve_returns_env_and_default(monkeypatch):
    monkeypatch.delenv("P2R_SCENE_MODEL", raising=False)

    env_name, default = model_routing.resolve("planner", "base-model")

    assert env_name == "P2R_PLANNER_MODEL"
    assert default == "base-model"


def test_resolve_default_prefers_shared_env(monkeypatch):
    monkeypatch.setenv("P2R_SCENE_MODEL", "model-shared")

    _, default = model_routing.resolve("planner", "base-model")

    assert default == "model-shared"


# ---------------------------------------------------------- llm fallbacks ---

class NotFoundError(Exception):
    """Mimics the provider's 404 model error (matched by type name)."""


def test_llm_records_not_found_fallback(monkeypatch):
    from prompt2render import llm

    llm.reset_rotation_state()
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("P2R_GEMINI_MODELS", "model-bad,model-good")
    monkeypatch.setenv("P2R_SCENE_MODEL", "model-bad")

    calls = []

    class _Message:
        content = "ok"

    class _Choice:
        message = _Message()
        finish_reason = "stop"

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            calls.append(kwargs["model"])

            if kwargs["model"] == "model-bad":
                raise NotFoundError("model not found")

            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(llm, "client", lambda key: _Client())

    text = llm.complete("hi", max_tokens=10, label="test-fallback")

    assert text == "ok"
    assert calls == ["model-bad", "model-good"]

    records = llm.fallback_records()
    assert len(records) == 1
    assert records[0]["model"] == "model-bad"
    assert records[0]["reason"] == "not_found"
    assert records[0]["next_model"] == "model-good"
    assert records[0]["label"] == "test-fallback"

    llm.reset_rotation_state()
    assert llm.fallback_records() == []
