"""Shared Gemini/OpenAI-compatible LLM client with deterministic quota rotation.

Rotation policy:

    If P2R_*_MODEL is set to a known model, begin at that model and continue
    only through lower fallback models. For example, starting at gemini-3.5-
    flash means 3.5-flash -> 3.5-flash-lite; it never jumps back to 3.7.

    For each model, try every configured key exactly once. Only after every
    key has failed for that model do we move to the next model.

This module is deliberately compatible with older Prompt2Render callers that
expect keys(), model_chain(), client(), and complete().
"""
from __future__ import annotations

import os
import sys
from typing import Any

from . import cfg

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Ordered from strongest/full model to the progressively cheaper fallback.
# Keep this list in the exact desired fallback order.
CANONICAL_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.7-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.6-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]
MODEL_FALLBACKS = CANONICAL_MODELS.copy()


def model_chain(model_env: str, default_model: str) -> list[str]:
    """Return a monotonic fallback chain beginning at the configured model.

    When the configured model is one of the canonical models, lower fallbacks
    only are tried. This prevents the old behavior where starting at 3.5 could
    incorrectly jump back to 3.7 and 3.6 after 3.5 was exhausted.
    """
    primary = os.environ.get(model_env, "").strip() or default_model
    if primary in CANONICAL_MODELS:
        start = CANONICAL_MODELS.index(primary)
        return CANONICAL_MODELS[start:]
    return [primary] + [m for m in CANONICAL_MODELS if m != primary]


def keys() -> list[str]:
    """Return the primary key followed by GEMINI_API_KEY_BACKUP* keys."""
    values: list[str] = []
    primary = os.environ.get("GEMINI_API_KEY", "").strip()
    if primary:
        values.append(primary)
    for name, value in sorted(os.environ.items()):
        if name.startswith("GEMINI_API_KEY_BACKUP") and value and value.strip():
            values.append(value.strip())
    if not values:
        sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
    return values


def client(key: str):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[prompt2render] openai not installed — pip install -r requirements.txt")
    return OpenAI(api_key=key, base_url=ENDPOINT, timeout=300.0, max_retries=2)


def is_not_found(error: BaseException) -> bool:
    """Recognize provider model-not-found errors."""
    if type(error).__name__ == "NotFoundError":
        return True
    status = getattr(error, "status_code", None)
    if status == 404:
        return True
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 404:
        return True
    text = str(error).lower()
    return any(token in text for token in (
        "404", "not found", "not_found", "is not found",
    ))

def is_rate_limited(error: BaseException) -> bool:
    """Recognize provider quota/rate-limit errors across SDK versions."""
    if type(error).__name__ == "RateLimitError":
        return True
    status = getattr(error, "status_code", None)
    if status == 429:
        return True
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(error).lower()
    return any(token in text for token in (
        "429", "rate limit", "rate-limit", "resource_exhausted", "quota exceeded",
    ))


def _completion(client_obj: Any, model: str, prompt: str, max_tokens: int):
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # Gemini-compatible endpoints require max_tokens, not max_completion_tokens.
        "max_tokens": max_tokens,
    }
    reasoning = os.environ.get("P2R_REASONING", "low").strip()
    if reasoning:
        kwargs["extra_body"] = {"reasoning_effort": reasoning}
    return client_obj.chat.completions.create(**kwargs)


# Global state to remember which (model, key) pairs are exhausted
# and which models are NOT_FOUND, so we don't retry them across sections.
_EXHAUSTED_QUOTA: set[tuple[str, str]] = set()
_UNSUPPORTED_MODELS: set[str] = set()

def complete(
    prompt: str,
    *,
    max_tokens: int,
    model_env: str = "P2R_SCENE_MODEL",
    default_model: str = "gemini-3.7-flash",
    label: str = "request",
) -> str:
    """Perform one completion with strict model/key rotation.

    The attempt order is visible in logs and is finite: each (model, key) pair
    is tried once. A non-quota exception is raised immediately because it is a
    real programming or request error, not a reason to burn all backup keys.
    """
    configured_keys = keys()
    models = model_chain(model_env, default_model)
    last_error: BaseException | None = None

    for model_index, model in enumerate(models):
        if model in _UNSUPPORTED_MODELS:
            continue
            
        for key_index, key in enumerate(configured_keys):
            if (model, key) in _EXHAUSTED_QUOTA:
                continue
                
            cfg.say(
                f"{label}: trying {model} (model {model_index + 1}/{len(models)}, "
                f"key {key_index + 1}/{len(configured_keys)})"
            )
            try:
                response = _completion(client(key), model, prompt, max_tokens)
            except Exception as error:  # noqa: BLE001
                last_error = error
                if is_not_found(error):
                    cfg.warn(f"{label}: model {model} is NOT_FOUND or unsupported. Skipping permanently.")
                    _UNSUPPORTED_MODELS.add(model)
                    break
                
                if not is_rate_limited(error):
                    raise
                    
                _EXHAUSTED_QUOTA.add((model, key))
                
                # Check if we have more keys for this model that aren't exhausted
                remaining_keys = sum(1 for k in configured_keys if (model, k) not in _EXHAUSTED_QUOTA)
                
                if remaining_keys > 0:
                    cfg.warn(
                        f"{label}: key {key_index + 1}/{len(configured_keys)} "
                        f"rate-limited on {model}; trying next available key"
                    )
                else:
                    next_model = next((m for m in models[model_index + 1:] if m not in _UNSUPPORTED_MODELS), None)
                    if next_model:
                        cfg.warn(
                            f"{label}: all {len(configured_keys)} key(s) rate-limited on "
                            f"{model}; switching model to {next_model}"
                        )
                    continue
            else:
                choice = response.choices[0] if response.choices else None
                text = (choice.message.content if choice else "") or ""
                if not text.strip():
                    finish = choice.finish_reason if choice else "?"
                    sys.exit(f"[prompt2render] empty completion (finish_reason={finish})")
                return text

    assert last_error is not None
    raise last_error
