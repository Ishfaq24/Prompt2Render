"""'Draft with AI' -- an explicitly rough, non-final script starting point.

Reuses the same GEMINI_API_KEY / OpenAI-compatible endpoint conventions as
fdx/scenes.py, but is otherwise independent: this never touches
build/scenes/*.py or the storyboard prompt, only the script editor's own
draft-request/response shape.

This module has no write access to script.md. The response only ever
fills the browser's in-memory form fields (routes_script.py's draft
endpoint never calls the save path) -- that split is what keeps "the
script is written by you" true even with this button available.
"""
from __future__ import annotations

import json
import os
import re
import textwrap

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _client():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, base_url=ENDPOINT, timeout=120.0, max_retries=1)


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.S)
    return m.group(1) if m else text


def draft(title: str, topic: str, audience: str,
         existing_sections: list[dict]) -> dict:
    """Ask Gemini for a rough first pass. Returns the editor's own shape:
    {"title": ..., "topic": ..., "audience": ..., "sections": [...]}."""
    client = _client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not set — the same key `fdx scenes` needs")

    section_hint = "\n".join(
        f"  {s.get('index')}: {s.get('title') or '(untitled)'}"
        for s in existing_sections
    ) or "  (none yet — propose a sensible 6-section structure)"

    prompt = textwrap.dedent(f"""
    You are drafting a ROUGH FIRST-PASS starting point for a narrated
    explainer video script, NOT a finished script. A human will heavily
    rewrite every word in their own voice before this is ever recorded --
    do not aim for final quality or a polished voice; aim for a scaffold
    they can react to and correct.

    Title: {title or '(propose one)'}
    Topic: {topic or '(propose one)'}
    Audience: {audience or 'undergraduate computer science'}

    Existing section titles (keep these if given, else invent a sensible
    6-section arc: hook, naive approach, key idea, worked example, where
    it shows up in practice, recap):
    {section_hint}

    For each section return a short title, one ANIM line (the single
    central visual for that section), and a short ROUGH narration
    paragraph (3-6 sentences, plain spoken language, no jargon dump).

    Output ONLY this JSON, no prose, no markdown fences:
    {{"title": "...", "topic": "...", "audience": "...",
      "sections": [{{"index": 1, "title": "...", "anim": "...", "narration": "..."}}]}}
    """).strip()

    model = os.environ.get("FDX_SCENE_MODEL", "gemini-3.6-flash")
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        max_tokens=4000, extra_body={"reasoning_effort": "low"})
    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content if choice else "") or ""
    if not text.strip():
        raise RuntimeError("empty draft response from the model")
    return json.loads(_strip_fences(text))
