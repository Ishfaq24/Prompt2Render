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
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
]

# Keep explicit legacy aliases that should map to canonical without being
# treated as "unknown" (e.g. gemini-2.5-flash-preview).
_MODEL_ALIASES = {
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-3.6-flash":"gemini-3.6-flash",
        "gemini-3.5-flash":"gemini-3.5-flash"
}

MODEL_FALLBACKS = CANONICAL_MODELS.copy()


def _parse_gemini_models_env() -> list[str] | None:
    """Parse P2R_GEMINI_MODELS if set (JSON array or comma-separated)."""
    raw = os.environ.get("P2R_GEMINI_MODELS", "").strip()
    if not raw:
        return None
    # Try JSON
    try:
        import json
        val = json.loads(raw)
        if isinstance(val, list):
            cleaned = [str(x).strip() for x in val if str(x).strip()]
            if cleaned:
                return cleaned
    except Exception:
        pass
    # Fallback: comma-separated
    parts = [p.strip().strip('"').strip("'") for p in raw.strip("[]").split(",")]
    cleaned = [p for p in parts if p]
    return cleaned or None


def model_chain(
    model_env: str,
    default_model: str,
) -> list[str]:
    """Return a monotonic model fallback chain.

    Known canonical model:
        start -> progressively lower models

    P2R_GEMINI_MODELS env (JSON array) overrides canonical when set:
        explicit ordered list from env

    Unknown/custom model:
        primary + full canonical fallback (so a NOT_FOUND primary still
        recovers to a known good model instead of exhausting immediately).

    This preserves the old "no silent jump to stronger" for truly custom
    models only when the env override is not set, while ensuring a typo or
    deprecated model like gemini-2.5-flash does not brick the whole harness.
    """
    # Env override takes precedence (user explicitly configured ordered list)
    env_chain = _parse_gemini_models_env()
    if env_chain is not None:
        explicit_primary = os.environ.get(model_env, "").strip()
        if explicit_primary and explicit_primary not in env_chain:
            explicit_primary = _MODEL_ALIASES.get(explicit_primary, explicit_primary)
            return [explicit_primary] + [m for m in env_chain if m != explicit_primary]
        return env_chain

    primary_raw = os.environ.get(model_env, "").strip() or default_model
    primary = _MODEL_ALIASES.get(primary_raw, primary_raw)

    if primary in CANONICAL_MODELS:
        index = CANONICAL_MODELS.index(primary)
        return CANONICAL_MODELS[index:]

    # Unknown: try primary first, then fallback to canonical (so NOT_FOUND
    # does not exhaust immediately). Keep order deterministic.
    return [primary] + CANONICAL_MODELS


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
    """Recognize provider quota/rate-limit *and* transient-unavailable errors.

    Both cases are "this key/model can't serve this request right now, but
    another key or model probably can" -- the retry loop treats them
    identically (rotate to the next key/model rather than raising). Without
    this, a plain 503 "model is currently experiencing high demand, try
    again later" -- textbook transient, and literally telling the caller to
    retry -- fell through to the "genuine request/programming error" branch
    below and was raised on the very first attempt, with none of the other
    11 key/model combinations ever tried. Upstream that surfaced as e.g.
    verifier_semantic turning one momentary overload into a hard BLOCKING
    finding that failed the whole harness gate.
    """
    if type(error).__name__ == "RateLimitError":
        return True

    status = getattr(
        error,
        "status_code",
        None,
    )

    if status in (429, 500, 502, 503, 504):
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
    ) in (429, 500, 502, 503, 504):
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
            "503",
            "500",
            "502",
            "504",
            "unavailable",
            "high demand",
            "overloaded",
            "server error",
            "try again later",
            "internal error",
        )
    )


def _resolved_temperature(
    explicit: float | None,
) -> float | None:
    """Explicit argument wins; otherwise ``P2R_LLM_TEMPERATURE``; otherwise
    unset (the provider's own default -- current behavior, unchanged).

    An unmanaged nondeterminism source (F15/docs/ARCHITECTURE_AUDIT.md
    SS13): ``llm.py`` previously exposed no way to control this at all.
    Default stays unset rather than pinning a value -- ordinary generation
    wants the provider's normal creative variation; a fixed value is
    something a reproducibility-focused caller (an ablation run, a golden
    baseline) opts into explicitly, not something imposed on every build.
    """

    if explicit is not None:
        return explicit

    raw = os.environ.get(
        "P2R_LLM_TEMPERATURE",
        "",
    ).strip()

    if not raw:
        return None

    try:
        return float(raw)
    except ValueError:
        cfg.warn(
            f"invalid P2R_LLM_TEMPERATURE={raw!r}; ignoring"
        )
        return None


def _resolved_seed(
    explicit: int | None,
) -> int | None:
    """Same resolution order as :func:`_resolved_temperature`, for
    ``P2R_LLM_SEED``. The provider's ``seed`` parameter is best-effort
    determinism, not a guarantee -- this only wires the plumbing through;
    it does not itself promise bit-identical completions.
    """

    if explicit is not None:
        return explicit

    raw = os.environ.get(
        "P2R_LLM_SEED",
        "",
    ).strip()

    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        cfg.warn(
            f"invalid P2R_LLM_SEED={raw!r}; ignoring"
        )
        return None


def _completion(
    client_obj: Any,
    model: str,
    prompt: str,
    max_tokens: int,
    image_base64: str | None = None,
    json_object: bool = False,
    temperature: float | None = None,
    seed: int | None = None,
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

    if temperature is not None:
        kwargs["temperature"] = temperature

    if seed is not None:
        kwargs["seed"] = seed

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

#: Every model fallback this process performed (Phase 17 telemetry). A
#: fallback is never silent: each NOT_FOUND skip and each rate-limit-driven
#: model switch appends one record here, and the harness's metrics/journal
#: layers read them. Records are small, JSON-native, and append-only.
_FALLBACK_RECORDS: list[dict[str, str]] = []


def _record_fallback(
    *,
    label: str,
    model: str,
    reason: str,
    next_model: str | None = None,
) -> None:
    import time as _time

    _FALLBACK_RECORDS.append(
        {
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "label": str(label),
            "model": str(model),
            "reason": str(reason),
            "next_model": str(next_model or ""),
        }
    )


def fallback_records() -> list[dict[str, str]]:
    """A copy of every fallback recorded since process start / reset."""

    return list(_FALLBACK_RECORDS)


def clear_fallback_records() -> None:
    _FALLBACK_RECORDS.clear()


def reset_rotation_state() -> None:
    """Reset model/key exhaustion.

    Useful for tests, interactive sessions, and long-running processes.
    """
    _EXHAUSTED_QUOTA.clear()
    _UNSUPPORTED_MODELS.clear()
    _FALLBACK_RECORDS.clear()


def complete(
    prompt: str,
    *,
    max_tokens: int,
    model_env: str = "P2R_SCENE_MODEL",
    default_model: str = "gemini-3.7-flash",
    label: str = "request",
    image_base64: str | None = None,
    json_object: bool = False,
    temperature: float | None = None,
    seed: int | None = None,
) -> str:
    """Perform one completion using deterministic model/key rotation.

    ``temperature``/``seed`` resolve through ``P2R_LLM_TEMPERATURE``/
    ``P2R_LLM_SEED`` when not passed explicitly (see
    :func:`_resolved_temperature`/:func:`_resolved_seed`) and stay fixed
    across every model/key rotation attempt within this one call, so a
    retry after a quota/rate-limit switch doesn't silently change the
    request's determinism intent.
    """

    configured_keys = keys()

    models = model_chain(
        model_env,
        default_model,
    )

    resolved_temperature = _resolved_temperature(temperature)
    resolved_seed = _resolved_seed(seed)

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
                    temperature=resolved_temperature,
                    seed=resolved_seed,
                )

            except Exception as error:
                last_error = error

                # ---------------------------------------------------------
                # Unsupported model
                # ---------------------------------------------------------
                if is_not_found(error):
                    _UNSUPPORTED_MODELS.add(model)

                    _record_fallback(
                        label=label,
                        model=model,
                        reason="not_found",
                        next_model=next(
                            (
                                candidate
                                for candidate in models[model_index + 1:]
                                if candidate not in _UNSUPPORTED_MODELS
                            ),
                            None,
                        ),
                    )

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
                            _record_fallback(
                                label=label,
                                model=model,
                                reason="rate_limited",
                                next_model=next_model,
                            )

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