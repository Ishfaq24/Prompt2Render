"""AI-suggested title, topic and section structure for a fresh script.md.

`prompt2render new` normally scales a fixed, generic arc (hook, a handful of
body-beat archetypes, recap) to a requested length, and sets both `title:`
and `topic:` in the front matter to whatever plain string you gave it.

`prompt2render new --ai` calls this module instead: it asks Gemini to propose
section count, titles and ANIM briefs tailored to the actual topic, plus a
sharper title and a distinct topic summary.

Narration is deliberately left out of scope here. Every section comes back
with a "Narration." placeholder. Structure and words are two different
judgement calls.
"""

from __future__ import annotations

import json
import re
import sys
import textwrap

from . import cfg, llm


def build_prompt(
    title: str,
    topic: str,
    audience: str,
    minutes: float | None,
    sections: int | None,
    fixed_title: bool = False,
) -> str:
    """Build the structured outline prompt."""

    if fixed_title:
        title_instr = (
            f'Keep the title exactly as given: "{title}".'
        )
    else:
        title_instr = (
            f'The working title is "{title}" -- propose a better, specific '
            "video title if you have one (under 70 characters, no clickbait, "
            "no colon-then-generic-subtitle padding), or keep it if it's "
            "already good."
        )

    if sections is not None:
        count_instr = f"Use EXACTLY {sections} sections."

        if minutes is not None:
            count_instr += (
                f" Distribute a total of about {minutes:g} "
                "minutes of narration across them however the "
                "content naturally needs."
            )

    elif minutes is not None:
        words = round(minutes * 140)

        count_instr = (
            f"Target about {minutes:g} minutes of narration total "
            f"(~{words} words at 140 words/minute). Pick however many "
            "sections that content naturally needs -- typically one "
            "section per 60-120 seconds of screen time. Use your judgement "
            "on the topic's complexity: a simple topic needs fewer, denser "
            "sections; a topic with several distinct sub-ideas needs more."
        )

    else:
        count_instr = (
            "Target about 8-12 minutes of narration total (roughly "
            "1100-1700 words at 140 words/minute). Pick however many "
            "sections that content naturally needs -- typically one "
            "section per 60-120 seconds of screen time. Use your judgement "
            "on the topic's complexity."
        )

    return textwrap.dedent(
        f"""
        You are outlining an educational explainer video. Working title:

        "{title}" (topic: {topic}) for an audience of {audience}.

        {title_instr}

        Also propose a one-line TOPIC summary distinct from the title: the key
        concepts this video actually covers, comma-separated, the way a course
        syllabus entry would read (e.g. "merge sort - divide and conquer, the
        merge step, O(n log n) complexity, stability"). This is metadata for
        the script file, never spoken -- it can be denser and more technical
        than the title.

        Then propose the SECTION STRUCTURE -- not narration, not code. Each
        section needs a short title (under 60 characters) and one ANIM line:
        a one-sentence brief for what the viewer is looking at on screen
        during that section, specific to this topic, which another process
        will later storyboard against a small drawing API (titles, labels,
        arrows, a sorted-array view, a code block, tables, etc. -- describe
        the
        idea, not exact drawing calls).

        {count_instr}

        The first section must open on the question the viewer actually has,
        not a topic definition and not "in this video we will...". The last
        section must recap the key idea(s) and end on the question the next
        video would answer. Every section in between should carry exactly one
        idea -- split a crowded section into two rather than cramming it.

        CHOOSE A TEACHING STRUCTURE based on the topic. Do not use a generic
        template:

        1. If the topic is a process, algorithm, or data structure operation
           (e.g. Quick Sort, Binary Search, Hash Collisions): commit to ONE
           concrete running example (specific numbers or values, chosen once)
           and give it enough sections to walk through every step of what
           actually happens to that example. Name the concrete example and
           its values directly in the ANIM line of every section that traces
           it (e.g. "trace partitioning on [2,6,1,8,4]: pivot 4, i and j scan
           left to right").

        2. If the topic is an architecture, system, or abstract concept
           (e.g. Cache Mapping, Pipelining, Virtual Memory): build a
           block/datapath diagram. Show the "naive approach" failing first,
           then introduce the actual solution. Trace a specific data payload
           through the blocks to show how it flows.

        3. If the topic is a comparison or trade-off
           (e.g. TCP vs UDP, Lomuto vs Hoare): use side-by-side execution
           or a table. Run the same input through both sides to make the
           difference self-explanatory.

        Whatever structure you choose, make it self-explanatory.
        Show, don't just tell.

        Output ONLY this JSON, no prose, no markdown fences, no trailing
        commas:

        {{
          "title": "...",
          "topic": "...",
          "sections": [
            {{"title": "...", "anim": "..."}},
            ...
          ]
        }}
        """
    ).strip()


def _parse(text: str) -> dict:
    """Parse and validate Gemini's outline response."""

    text = text.strip()

    # Accept a JSON response optionally wrapped in a markdown code fence.
    fenced = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if fenced:
        text = fenced.group(1).strip()

    try:
        data = json.loads(text)

    except json.JSONDecodeError as exc:
        sys.exit(
            "[prompt2render] outline: model reply was not valid JSON "
            f"({exc})"
        )

    if not isinstance(data, dict):
        sys.exit(
            "[prompt2render] outline: model reply was not a JSON object"
        )

    title_value = data.get("title")
    topic_value = data.get("topic")
    sections_value = data.get("sections")

    if not isinstance(title_value, str) or not title_value.strip():
        sys.exit(
            "[prompt2render] outline: model reply was missing title"
        )

    if not isinstance(topic_value, str) or not topic_value.strip():
        sys.exit(
            "[prompt2render] outline: model reply was missing topic"
        )

    if not isinstance(sections_value, list) or not sections_value:
        sys.exit(
            "[prompt2render] outline: model reply had no 'sections' list"
        )

    for index, section in enumerate(sections_value, start=1):
        if not isinstance(section, dict):
            sys.exit(
                "[prompt2render] outline: "
                f"section {index} was not an object"
            )

        section_title = section.get("title")
        section_anim = section.get("anim")

        if not isinstance(section_title, str) or not section_title.strip():
            sys.exit(
                "[prompt2render] outline: "
                f"section {index} was missing title"
            )

        if not isinstance(section_anim, str) or not section_anim.strip():
            sys.exit(
                "[prompt2render] outline: "
                f"section {index} was missing anim"
            )

    return data


def generate(
    title: str,
    topic: str,
    audience: str,
    minutes: float | None = None,
    sections: int | None = None,
    fixed_title: bool = False,
) -> dict:
    """Generate an AI-assisted outline.

    Returns:

        {
            "title": "...",
            "topic": "...",
            "sections": [
                {"title": "...", "anim": "..."},
                ...
            ],
        }
    """

    prompt = build_prompt(
        title,
        topic,
        audience,
        minutes,
        sections,
        fixed_title,
    )

    cfg.say(
        f'asking Gemini to outline "{title}"'
    )

    text = llm.complete(
        prompt,
        max_tokens=4000,
    )

    data = _parse(text)

    secs = data["sections"]

    if sections is not None and len(secs) != sections:
        cfg.warn(
            f"asked for {sections} sections, "
            f"model returned {len(secs)} -- using its count"
        )

    cfg.say(
        f'outline: "{data["title"]}" - '
        f'{len(secs)} section(s) - '
        + "; ".join(
            section["title"]
            for section in secs
        )
    )

    return data