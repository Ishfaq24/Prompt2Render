"""AI-suggested section structure for a fresh script.md.

`prompt2render new` normally scales a fixed, generic arc (hook, a handful of
body-beat archetypes, recap) to a requested length -- see
`project.render_template`. `prompt2render new --ai` calls this module
instead: it asks Gemini to propose section count, titles and ANIM briefs
tailored to the actual topic, rather than reusing "The naive approach and
why it breaks" for every video regardless of subject.

Narration is deliberately left out of scope here, same as the deterministic
path: every section comes back with a "Narration." placeholder. Structure
and words are two different judgement calls -- this one is "how should this
topic be broken into beats", not "what should be said". `prompt2render draft`
(or your own hand) fills the words in afterwards.
"""
from __future__ import annotations

import json
import re
import sys
import textwrap

from . import cfg, llm


def build_prompt(title: str, topic: str, audience: str,
                 minutes: float | None, sections: int | None) -> str:
    if sections is not None:
        count_instr = f"Use EXACTLY {sections} sections."
        if minutes is not None:
            count_instr += (f" Distribute a total of about {minutes:g} "
                            "minutes of narration across them however the "
                            "content naturally needs.")
    elif minutes is not None:
        words = round(minutes * 140)
        count_instr = (
            f"Target about {minutes:g} minutes of narration total (~{words} "
            "words at 140 words/minute). Pick however many sections that "
            "content naturally needs -- typically one section per 60-120 "
            "seconds of screen time. Use your judgement on the topic's "
            "complexity: a simple topic needs fewer, denser sections; a "
            "topic with several distinct sub-ideas needs more.")
    else:
        count_instr = (
            "Target about 8-12 minutes of narration total (roughly "
            "1100-1700 words at 140 words/minute). Pick however many "
            "sections that content naturally needs -- typically one "
            "section per 60-120 seconds of screen time. Use your judgement "
            "on the topic's complexity.")

    return textwrap.dedent(f"""
    You are outlining an educational explainer video titled "{title}"
    (topic: {topic}) for an audience of {audience}.

    Propose the SECTION STRUCTURE only -- not narration, not code. Each
    section needs a short title (under 60 characters) and one ANIM line: a
    one-sentence brief for what the viewer is looking at on screen during
    that section, specific to this topic, which another process will later
    storyboard against a small drawing API (titles, labels, arrows, a
    sorted-array view, a code block, tables, etc. -- describe the idea, not
    exact drawing calls).

    {count_instr}

    The first section must open on the question the viewer actually has,
    not a topic definition and not "in this video we will...". The last
    section must recap the key idea(s) and end on the question the next
    video would answer. Every section in between should carry exactly one
    idea -- split a crowded section into two rather than cramming it.

    Output ONLY this JSON, no prose, no markdown fences, no trailing commas:

    {{"sections": [{{"title": "...", "anim": "..."}}, ...]}}
    """).strip()


def _parse(text: str) -> list[dict]:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*\n(.*?)\n```\s*$", text, re.S)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"[prompt2render] outline: model reply was not valid JSON ({e})")
    sections = data.get("sections") if isinstance(data, dict) else None
    if not sections or not isinstance(sections, list):
        sys.exit("[prompt2render] outline: model reply had no 'sections' list")
    for s in sections:
        if not isinstance(s, dict) or not s.get("title") or not s.get("anim"):
            sys.exit("[prompt2render] outline: a section was missing title/anim")
    return sections


def generate(title: str, topic: str, audience: str, minutes: float | None = None,
            sections: int | None = None) -> list[dict]:
    prompt = build_prompt(title, topic, audience, minutes, sections)
    cfg.say(f'asking Gemini to outline "{title}"')
    text = llm.complete(prompt, max_tokens=4000)
    secs = _parse(text)
    if sections is not None and len(secs) != sections:
        cfg.warn(f"asked for {sections} sections, model returned {len(secs)} "
                 "-- using its count")
    cfg.say(f"outline: {len(secs)} section(s) - "
            + "; ".join(s["title"] for s in secs))
    return secs
