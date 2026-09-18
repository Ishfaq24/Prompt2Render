"""Tier 5 (F15): seed/temperature control in llm.py.

llm.py had zero prior test coverage (a pre-existing gap, not introduced
here) -- this file covers only what this change touches: the resolution
order (explicit arg > env var > unset), invalid-env-var handling, and that
_completion/complete actually thread the resolved values through as real
OpenAI-compatible kwargs. The pre-existing model/key rotation loop itself
is out of scope, matching this migration's established "test what you
touch" discipline.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import prompt2render.llm as llm


# --------------------------------------------------- _resolved_temperature

def test_resolved_temperature_explicit_wins(monkeypatch):
    monkeypatch.setenv("P2R_LLM_TEMPERATURE", "0.9")
    assert llm._resolved_temperature(0.2) == 0.2


def test_resolved_temperature_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("P2R_LLM_TEMPERATURE", "0.7")
    assert llm._resolved_temperature(None) == 0.7


def test_resolved_temperature_unset_is_none(monkeypatch):
    monkeypatch.delenv("P2R_LLM_TEMPERATURE", raising=False)
    assert llm._resolved_temperature(None) is None


def test_resolved_temperature_invalid_env_warns_and_returns_none(monkeypatch):
    monkeypatch.setenv("P2R_LLM_TEMPERATURE", "not-a-float")
    warnings = []
    monkeypatch.setattr(llm.cfg, "warn", lambda msg: warnings.append(msg))

    assert llm._resolved_temperature(None) is None
    assert any("P2R_LLM_TEMPERATURE" in w for w in warnings)


# ----------------------------------------------------------- _resolved_seed

def test_resolved_seed_explicit_wins(monkeypatch):
    monkeypatch.setenv("P2R_LLM_SEED", "7")
    assert llm._resolved_seed(42) == 42


def test_resolved_seed_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("P2R_LLM_SEED", "13")
    assert llm._resolved_seed(None) == 13


def test_resolved_seed_unset_is_none(monkeypatch):
    monkeypatch.delenv("P2R_LLM_SEED", raising=False)
    assert llm._resolved_seed(None) is None


def test_resolved_seed_invalid_env_warns_and_returns_none(monkeypatch):
    monkeypatch.setenv("P2R_LLM_SEED", "not-an-int")
    warnings = []
    monkeypatch.setattr(llm.cfg, "warn", lambda msg: warnings.append(msg))

    assert llm._resolved_seed(None) is None
    assert any("P2R_LLM_SEED" in w for w in warnings)


# ------------------------------------------------------------- _completion

def _fake_client(captured: dict) -> MagicMock:
    client_obj = MagicMock()

    def _create(**kwargs):
        captured.update(kwargs)
        response = MagicMock()
        choice = MagicMock()
        choice.message.content = "ok"
        response.choices = [choice]
        return response

    client_obj.chat.completions.create.side_effect = _create
    return client_obj


def test_completion_includes_temperature_and_seed_when_set():
    captured: dict = {}
    llm._completion(
        _fake_client(captured),
        "gemini-3.7-flash",
        "hello",
        100,
        temperature=0.3,
        seed=42,
    )
    assert captured["temperature"] == 0.3
    assert captured["seed"] == 42


def test_completion_omits_temperature_and_seed_when_none():
    captured: dict = {}
    llm._completion(
        _fake_client(captured),
        "gemini-3.7-flash",
        "hello",
        100,
    )
    assert "temperature" not in captured
    assert "seed" not in captured


# ------------------------------------------------------------------ complete

def test_complete_resolves_and_threads_temperature_and_seed(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(llm, "client", lambda key: MagicMock())

    captured: dict = {}

    def _fake_completion(client_obj, model, prompt, max_tokens, **kwargs):
        captured.update(kwargs)
        response = MagicMock()
        choice = MagicMock()
        choice.message.content = "ok"
        response.choices = [choice]
        return response

    monkeypatch.setattr(llm, "_completion", _fake_completion)
    llm.reset_rotation_state()

    llm.complete("hello", max_tokens=10, temperature=0.1, seed=99)

    assert captured["temperature"] == 0.1
    assert captured["seed"] == 99


def test_complete_seed_stays_fixed_across_rotation_attempts(monkeypatch):
    """A retry after a rate-limit switch must not silently change the
    determinism intent for the same logical request."""

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-1")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP1", "fake-key-2")
    monkeypatch.setattr(llm, "client", lambda key: MagicMock())
    llm.reset_rotation_state()

    seeds_seen = []
    calls = {"n": 0}

    class _RateLimitError(Exception):
        status_code = 429

    def _fake_completion(client_obj, model, prompt, max_tokens, **kwargs):
        seeds_seen.append(kwargs.get("seed"))
        calls["n"] += 1
        if calls["n"] == 1:
            raise _RateLimitError("rate limited")
        response = MagicMock()
        choice = MagicMock()
        choice.message.content = "ok"
        response.choices = [choice]
        return response

    monkeypatch.setattr(llm, "_completion", _fake_completion)

    llm.complete("hello", max_tokens=10, seed=7)

    assert seeds_seen == [7, 7]


def test_backup_key_sort_supports_underscore():
    assert llm._backup_key_sort(("GEMINI_API_KEY_BACKUP1", "k1")) == (1, "GEMINI_API_KEY_BACKUP1")
    assert llm._backup_key_sort(("GEMINI_API_KEY_BACKUP_1", "k1")) == (1, "GEMINI_API_KEY_BACKUP_1")
    assert llm._backup_key_sort(("GEMINI_API_KEY_BACKUP_10", "k10")) == (10, "GEMINI_API_KEY_BACKUP_10")
    assert llm._backup_key_sort(("OTHER_KEY", "val")) == (10**9, "OTHER_KEY")


def test_keys_ordering_with_underscore(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "primary")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP_2", "backup-2")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP_1", "backup-1")
    monkeypatch.setenv("GEMINI_API_KEY_BACKUP3", "backup-3")

    ordered = llm.keys()
    assert ordered == ["primary", "backup-1", "backup-2", "backup-3"]


def test_endpoint_resolution(monkeypatch):
    monkeypatch.delenv("P2R_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert llm.endpoint() == llm.ENDPOINT

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    assert llm.endpoint() == "https://api.openai.com/v1"

    monkeypatch.setenv("P2R_LLM_BASE_URL", "http://localhost:11434/v1")
    assert llm.endpoint() == "http://localhost:11434/v1"


def test_keys_multi_provider_and_local(monkeypatch):
    import os
    for k in list(os.environ.keys()):
        if "API_KEY" in k:
            monkeypatch.delenv(k, raising=False)

    # Localhost fallback when no keys are provided
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    assert llm.keys() == ["local-token"]

    # Provider key recognized
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test1234")
    monkeypatch.setenv("OPENAI_API_KEY_BACKUP_1", "sk-proj-backup1")
    assert llm.keys() == ["sk-proj-test1234", "sk-proj-backup1"]


def test_model_chain_custom_endpoint(monkeypatch):
    monkeypatch.delenv("P2R_LLM_MODELS", raising=False)
    monkeypatch.delenv("P2R_GEMINI_MODELS", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("P2R_SCENE_MODEL", "qwen2.5-coder:14b")

    chain = llm.model_chain("P2R_SCENE_MODEL", "gemini-3.7-flash")
    assert chain == ["qwen2.5-coder:14b"]


def test_completion_reasoning_effort_retry_on_unsupported_model(monkeypatch):
    monkeypatch.setenv("P2R_REASONING", "medium")
    attempts = []

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    attempts.append(dict(kwargs))
                    if "extra_body" in kwargs:
                        raise Exception("400 Unrecognized request argument: reasoning_effort")
                    res = MagicMock()
                    choice = MagicMock()
                    choice.message.content = "recovered"
                    res.choices = [choice]
                    return res

    res = llm._completion(_FakeClient(), "gpt-4o", "hi", 100)
    assert res.choices[0].message.content == "recovered"
    assert len(attempts) == 2
    assert "extra_body" in attempts[0]
    assert "extra_body" not in attempts[1]


