"""Shared Gemini chat-completion plumbing for the AI-assisted stages.

`scenes.py` talks to the same OpenAI-compatible Gemini endpoint with the same
key-rotation-on-429 behaviour, but wraps it in a render-and-audit retry loop
specific to storyboarding -- different enough to leave alone. `draft.py` and
`outline.py` are both a single one-shot call with nothing else going on, so
that part is factored out here once a second caller needed it.
"""
from __future__ import annotations

import os
import sys

from . import cfg

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"

#: Tried in order, once the primary model is rate-limited on every key.
#: Gemini's free tier meters quota per (key, model) pair, so a model that's
#: exhausted for every key is a wall a different key can't move -- the same
#: reasoning `keys()` applies across keys, applied across models instead.
MODEL_FALLBACKS = ["gemini-3.7-flash", "gemini-3.5-flash"]


def model_chain(model_env: str, default_model: str) -> list[str]:
    """The primary model (env override or default), then the fallback chain.

    Deduplicated in order, so a primary that already names a fallback model
    doesn't get tried twice.
    """
    primary = os.environ.get(model_env, default_model)
    chain = [primary]
    for m in MODEL_FALLBACKS:
        if m not in chain:
            chain.append(m)
    return chain


def keys() -> list[str]:
    """GEMINI_API_KEY, plus any GEMINI_API_KEY_BACKUP* for failover.

    Gemini's free tier caps requests *per day per model*, and the 429 it
    returns names a retry-after of tens of seconds -- misleading for a quota
    that will not clear until tomorrow. A second key on a separate quota is
    the only thing that actually unblocks a run in progress.
    """
    ks = [os.environ.get("GEMINI_API_KEY", "")]
    for name, val in sorted(os.environ.items()):
        if name.startswith("GEMINI_API_KEY_BACKUP") and val:
            ks.append(val)
    ks = [k for k in ks if k]
    if not ks:
        sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
    return ks


def client(key: str):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[prompt2render] openai not installed — pip install -r requirements.txt")
    return OpenAI(api_key=key, base_url=ENDPOINT, timeout=300.0, max_retries=2)


def complete(prompt: str, *, max_tokens: int, model_env: str = "P2R_SCENE_MODEL",
            default_model: str = "gemini-3.6-flash") -> str:
    """One-shot completion, rotating keys then models on a rate limit.

    Every key is tried against the current model before falling through to
    the next model in MODEL_FALLBACKS and starting over from the first key --
    a model exhausted on every key is a wall no key can move past.
    """
    ks = keys()
    models = model_chain(model_env, default_model)
    key_i = model_i = 0
    c = client(ks[key_i])
    while True:
        model = models[model_i]
        try:
            resp = c.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                # Gemini 3.x spends completion budget thinking before it
                # answers; these calls don't need much reasoning, so cap it.
                extra_body={"reasoning_effort": os.environ.get("P2R_REASONING", "low")},
            )
        except Exception as e:                    # noqa: BLE001
            if type(e).__name__ != "RateLimitError":
                raise
            if key_i + 1 < len(ks):
                key_i += 1
                cfg.warn(f"key {key_i}/{len(ks)} rate-limited on {model}, "
                         "switching to the next key")
                c = client(ks[key_i])
                continue
            if model_i + 1 < len(models):
                key_i, model_i = 0, model_i + 1
                cfg.warn(f"all {len(ks)} key(s) rate-limited on {model}, "
                         f"switching to {models[model_i]}")
                c = client(ks[key_i])
                continue
            raise
        break
    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content if choice else "") or ""
    if not text.strip():
        fin = choice.finish_reason if choice else "?"
        sys.exit(f"[prompt2render] empty completion (finish_reason={fin})")
    return text
