"""Shared Gemini/OpenAI-compatible LLM client with deterministic quota rotation.

Rotation policy:

    * Start at the configured model.
    * For canonical models, only move toward cheaper/lower fallbacks.
    * For each model, try every configured API key exactly once.
    * A rate-limited key is exhausted for this process/session.
    * A NOT_FOUND model is skipped permanently for this process.
    * Non-quota failures are raised immediately.

The module remains compatible with older Prompt2Render callers that expect:
keys(), model_chain(), client(), and complete().
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from . import cfg


ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/openai/"
)


# Strongest -> cheapest fallback. Every full model (and all of its keys) must
# be exhausted before a "-lite" model is tried at all — lite models trade
# quality for cost/quota and are a last resort, not an early fallback.
CANONICAL_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.7-flash-lite",
    "gemini-3.5-flash-lite",
]

MODEL_FALLBACKS = CANONICAL_MODELS.copy()


def model_chain(
    model_env: str,
    default_model: str,
) -> list[str]:
    """Return a monotonic model fallback chain.

    Known canonical model:
        start -> progressively lower models

    Unknown/custom model:
        custom model only

    This prevents an unknown or older model from silently jumping to a
    stronger canonical model.
    """
    primary = (
        os.environ.get(model_env, "").strip()
        or default_model
    )

    if primary in CANONICAL_MODELS:
        index = CANONICAL_MODELS.index(primary)
        return CANONICAL_MODELS[index:]

    return [primary]


def _backup_key_sort(item: tuple[str, str]) -> tuple[int, str]:
    """Numerically sort GEMINI_API_KEY_BACKUP<N>."""
    name, _ = item

    match = re.fullmatch(
        r"GEMINI_API_KEY_BACKUP(\d+)",
        name,
    )

    if match:
        return (
            int(match.group(1)),
            name,
        )

    return (
        10**9,
        name,
    )


def keys() -> list[str]:
    """Return unique API keys in deterministic priority order."""
    values: list[str] = []
    seen: set[str] = set()

    primary = os.environ.get(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if primary:
        values.append(primary)
        seen.add(primary)

    backups = sorted(
        (
            (name, value.strip())
            for name, value in os.environ.items()
            if name.startswith("GEMINI_API_KEY_BACKUP")
            and value
            and value.strip()
        ),
        key=_backup_key_sort,
    )

    for _, value in backups:
        if value not in seen:
            values.append(value)
            seen.add(value)

    if not values:
        sys.exit(
            "[prompt2render] GEMINI_API_KEY not set "
            "(it lives in .env)"
        )

    return values


def client(key: str):
    """Create an OpenAI-compatible Gemini client.

    max_retries=0 is intentional.

    Retry policy belongs to this module because quota rotation depends on
    knowing exactly which (model, key) pair failed.
    """
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit(
            "[prompt2render] openai not installed — "
            "pip install -r requirements.txt"
        )

    return OpenAI(
        api_key=key,
        base_url=ENDPOINT,
        timeout=300.0,
        max_retries=0,
    )


def is_not_found(
    error: BaseException,
) -> bool:
    """Recognize provider model-not-found errors."""
    if type(error).__name__ == "NotFoundError":
        return True

    status = getattr(
        error,
        "status_code",
        None,
    )

    if status == 404:
        return True

    response = getattr(
        error,
        "response",
        None,
    )

    if getattr(
        response,
        "status_code",
        None,
    ) == 404:
        return True

    text = str(error).lower()

    return any(
        token in text
        for token in (
            "404",
            "not found",
            "not_found",
            "is not found",
            "model_not_found",
        )
    )


def is_rate_limited(
    error: BaseException,
) -> bool:
    """Recognize provider quota/rate-limit errors."""
    if type(error).__name__ == "RateLimitError":
        return True

    status = getattr(
        error,
        "status_code",
        None,
    )

    if status == 429:
        return True

    response = getattr(
        error,
        "response",
        None,
    )

    if getattr(
        response,
        "status_code",
        None,
    ) == 429:
        return True

    text = str(error).lower()

    return any(
        token in text
        for token in (
            "429",
            "rate limit",
            "rate-limit",
            "resource_exhausted",
            "quota exceeded",
            "quota_exceeded",
            "too many requests",
        )
    )


def _completion(
    client_obj: Any,
    model: str,
    prompt: str,
    max_tokens: int,
    image_base64: str | None = None,
    json_object: bool = False,
):
    content: str | list[dict[str, Any]] = prompt

    if image_base64:
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}"
                },
            },
        ]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "max_tokens": max_tokens,
    }

    if json_object:
        kwargs["response_format"] = {"type": "json_object"}

    reasoning = os.environ.get(
        "P2R_REASONING",
        "low",
    ).strip()

    if reasoning:
        kwargs["extra_body"] = {
            "reasoning_effort": reasoning
        }

    return client_obj.chat.completions.create(
        **kwargs
    )


# Process-level state.
#
# These sets deliberately survive across sections during one build so that
# a quota-exhausted key/model pair isn't repeatedly hammered by later scenes.
_EXHAUSTED_QUOTA: set[tuple[str, str]] = set()
_UNSUPPORTED_MODELS: set[str] = set()


def reset_rotation_state() -> None:
    """Reset model/key exhaustion.

    Useful for tests, interactive sessions, and long-running processes.
    """
    _EXHAUSTED_QUOTA.clear()
    _UNSUPPORTED_MODELS.clear()


def complete(
    prompt: str,
    *,
    max_tokens: int,
    model_env: str = "P2R_SCENE_MODEL",
    default_model: str = "gemini-3.7-flash",
    label: str = "request",
    image_base64: str | None = None,
    json_object: bool = False,
) -> str:
    """Perform one completion using deterministic model/key rotation."""

    configured_keys = keys()

    models = model_chain(
        model_env,
        default_model,
    )

    last_error: BaseException | None = None

    for model_index, model in enumerate(models):

        if model in _UNSUPPORTED_MODELS:
            continue

        available_keys = [
            key
            for key in configured_keys
            if (
                model,
                key,
            ) not in _EXHAUSTED_QUOTA
        ]

        if not available_keys:
            continue

        for key_index, key in enumerate(
            configured_keys
        ):
            pair = (
                model,
                key,
            )

            if pair in _EXHAUSTED_QUOTA:
                continue

            cfg.say(
                f"{label}: trying {model} "
                f"(model {model_index + 1}/"
                f"{len(models)}, "
                f"key {key_index + 1}/"
                f"{len(configured_keys)})"
            )

            try:
                response = _completion(
                    client(key),
                    model,
                    prompt,
                    max_tokens,
                    image_base64=image_base64,
                    json_object=json_object,
                )

            except Exception as error:
                last_error = error

                # ---------------------------------------------------------
                # Unsupported model
                # ---------------------------------------------------------
                if is_not_found(error):
                    _UNSUPPORTED_MODELS.add(model)

                    cfg.warn(
                        f"{label}: model {model} is "
                        "NOT_FOUND or unsupported; "
                        "skipping permanently"
                    )

                    break

                # ---------------------------------------------------------
                # Quota/rate limit
                # ---------------------------------------------------------
                if is_rate_limited(error):
                    _EXHAUSTED_QUOTA.add(pair)

                    remaining = sum(
                        1
                        for candidate in configured_keys
                        if (
                            model,
                            candidate,
                        ) not in _EXHAUSTED_QUOTA
                    )

                    if remaining:
                        cfg.warn(
                            f"{label}: key "
                            f"{key_index + 1}/"
                            f"{len(configured_keys)} "
                            f"rate-limited on {model}; "
                            "trying next key"
                        )
                    else:
                        next_model = next(
                            (
                                candidate
                                for candidate in models[
                                    model_index + 1:
                                ]
                                if candidate
                                not in _UNSUPPORTED_MODELS
                            ),
                            None,
                        )

                        if next_model:
                            cfg.warn(
                                f"{label}: all "
                                f"{len(configured_keys)} "
                                f"key(s) rate-limited "
                                f"on {model}; switching "
                                f"to {next_model}"
                            )

                    continue

                # ---------------------------------------------------------
                # Everything else is a genuine request/programming error.
                # Do not burn backup quota trying to recover it.
                # ---------------------------------------------------------
                raise

            # -------------------------------------------------------------
            # Successful response
            # -------------------------------------------------------------
            choice = (
                response.choices[0]
                if response.choices
                else None
            )

            text = (
                choice.message.content
                if choice
                else ""
            ) or ""

            if not text.strip():
                finish_reason = (
                    choice.finish_reason
                    if choice
                    else "?"
                )

                raise RuntimeError(
                    "[prompt2render] empty completion "
                    f"(model={model}, "
                    f"finish_reason={finish_reason})"
                )

            return text

    if last_error is not None:
        raise RuntimeError(
            f"{label}: all configured model/key "
            "combinations were exhausted"
        ) from last_error

    raise RuntimeError(
        f"{label}: no usable model/key combination "
        "remains"
    )