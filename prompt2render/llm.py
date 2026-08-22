"""Shared Gemini chat-completion plumbing for the AI-assisted stages.

`scenes.py` talks to the same OpenAI-compatible Gemini endpoint with the same
key-rotation-on-429 behaviour, but wraps it in a render-and-audit retry loop
specific to storyboarding. `draft.py` and `outline.py` are both a single 
one-shot call with nothing else going on, so that part is factored out here.
"""
from __future__ import annotations

import os
import sys
import time
import random
import threading
from typing import Iterator

from . import cfg

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Thread-safe cooldown cache to prevent concurrent jobs from hammering 
# a route that just reported quota exhaustion.
_cooldown_lock = threading.Lock()
_cooldowns: dict[str, float] = {}


def configured_models(model_env: str = "P2R_SCENE_MODEL", default_model: str = "gemini-3.7-flash") -> list[str]:
    """The primary model (env override or default), then the fallback chain."""
    primary = os.environ.get(model_env, default_model)
    fallback_str = os.environ.get("P2R_GEMINI_MODELS", "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite")
    
    chain = [primary]
    for m in [m.strip() for m in fallback_str.split(",") if m.strip()]:
        if m not in chain:
            chain.append(m)
    return chain


def configured_keys() -> list[str]:
    """GEMINI_API_KEY, plus any GEMINI_API_KEY_BACKUP* for failover.
    Also supports comma-separated keys in P2R_GEMINI_KEYS.
    """
    ks = []
    
    # 1. Primary key
    if k := os.environ.get("GEMINI_API_KEY", "").strip():
        ks.append(k)
        
    # 2. P2R_GEMINI_KEYS comma-separated list
    if p2r_keys := os.environ.get("P2R_GEMINI_KEYS", ""):
        for k in p2r_keys.split(","):
            if k.strip() and k.strip() not in ks:
                ks.append(k.strip())
                
    # 3. Legacy BACKUP_* variables
    for name, val in sorted(os.environ.items()):
        if name.startswith("GEMINI_API_KEY_BACKUP") and val.strip():
            if val.strip() not in ks:
                ks.append(val.strip())
                
    if not ks:
        sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
    return ks


def client(key: str):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[prompt2render] openai not installed — pip install -r requirements.txt")
    # max_retries=0 because we handle routing/retries explicitly in our own loop
    return OpenAI(api_key=key, base_url=ENDPOINT, timeout=120.0, max_retries=0)


def is_quota_error(e: Exception) -> bool:
    """True if this is a hard quota exhaustion or rate limit."""
    name = type(e).__name__
    if name == "RateLimitError":
        return True
    
    msg = str(e).lower()
    # OpenAI SDK wraps 429s as RateLimitError, but sometimes 403s are quota errors too
    if "resource_exhausted" in msg or "quota" in msg or "rate limit" in msg:
        return True
    return False


def is_invalid_model_error(e: Exception) -> bool:
    """True if the provider outright rejects the model name."""
    name = type(e).__name__
    msg = str(e).lower()
    return name == "NotFoundError" or "models/" in msg and "not found" in msg


def is_retryable_error(e: Exception) -> bool:
    """True if this is a temporary network or server error (5xx)."""
    name = type(e).__name__
    return name in ("APIConnectionError", "APITimeoutError", "InternalServerError", "ConflictError")


def mark_cooldown(model: str, key_idx: int) -> None:
    cooldown_sec = int(os.environ.get("P2R_MODEL_COOLDOWN_SECONDS", "60"))
    route_id = f"{model}:{key_idx}"
    with _cooldown_lock:
        _cooldowns[route_id] = time.time() + cooldown_sec


def is_cooled_down(model: str, key_idx: int) -> bool:
    route_id = f"{model}:{key_idx}"
    with _cooldown_lock:
        if route_id not in _cooldowns:
            return False
        if time.time() > _cooldowns[route_id]:
            del _cooldowns[route_id]
            return False
        return True


def iter_routes(models: list[str], keys: list[str]) -> Iterator[tuple[int, str, int, str]]:
    """Yields (model_idx, model, key_idx, key)."""
    for m_idx, model in enumerate(models):
        for k_idx, key in enumerate(keys):
            yield m_idx, model, k_idx, key


def complete(prompt: str, *, max_tokens: int, model_env: str = "P2R_SCENE_MODEL",
            default_model: str = "gemini-3.7-flash") -> str:
    """One-shot completion, intelligently rotating keys and models."""
    keys = configured_keys()
    models = configured_models(model_env, default_model)
    
    max_model_attempts = int(os.environ.get("P2R_MAX_MODEL_ATTEMPTS", "4"))
    
    last_error = None
    
    for m_idx, model, k_idx, key in iter_routes(models, keys):
        if is_cooled_down(model, k_idx):
            continue
            
        c = client(key)
        attempts = 0
        
        while attempts < max_model_attempts:
            attempts += 1
            try:
                resp = c.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    extra_body={"reasoning_effort": os.environ.get("P2R_REASONING", "low")},
                )
                
                choice = resp.choices[0] if resp.choices else None
                text = (choice.message.content if choice else "") or ""
                if not text.strip():
                    fin = choice.finish_reason if choice else "?"
                    sys.exit(f"[prompt2render] empty completion (finish_reason={fin})")
                return text
                
            except Exception as e:
                last_error = e
                if is_invalid_model_error(e):
                    cfg.warn(f"model {model} is invalid/not found, skipping to next model.")
                    break # Break out of attempts AND key loop for this model
                    
                if is_quota_error(e):
                    cfg.warn(f"key {k_idx + 1}/{len(keys)} rate-limited on {model}, rotating...")
                    mark_cooldown(model, k_idx)
                    break # Break out of attempts loop, move to next key/model route
                    
                if is_retryable_error(e):
                    delay = min(2 ** attempts + random.random(), 10.0)
                    cfg.warn(f"temporary error on {model} (key {k_idx + 1}): {type(e).__name__}. Retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue
                    
                # Unhandled error (e.g. bad request, safety filter)
                raise
                
    sys.exit(f"[prompt2render] All {len(keys)} key(s) and {len(models)} model(s) exhausted. Last error: {type(last_error).__name__}: {last_error}\n"
             "Note: Backup keys must belong to separate Google Cloud projects with independent quota.")
