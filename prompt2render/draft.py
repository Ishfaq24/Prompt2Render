"""Draft narration for a fresh script.md.

`prompt2render new` scaffolds section headers and an ANIM brief per section,
then leaves the narration itself as a "Narration." placeholder -- on purpose,
per the project's inauthentic-content stance (see README: "The script is
written by you"). This stage exists for people who want a starting draft to
rewrite rather than a blank page, not a way to skip that rewrite: it asks
Gemini for narration text and writes it into script.md, but `build` still
runs on whatever is in that file when you call it -- reading and fixing the
draft before then is on you.
"""
from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

from . import cfg, llm
from .project import _HOOK, _RECAP, Script, parse_script

_HEAD_LINE = re.compile(r"^##\s+(\d+)\s*[-–—.:]?\s*(.*)$")
_REPLY_HEAD = re.compile(r"^##\s*(\d+)\s*$", re.M)


def _norm(text: str) -> str:
    return " ".join(text.split()).strip().lower()


#: The exact strings project.render_template() leaves in a fresh script.md.
#: The hook's is generic writing advice, not "Narration." like the rest --
#: it still counts as unwritten, or `draft` would silently skip section 1
#: forever and leave every video opening on the same boilerplate. Match
#: verbatim, so real narration that happens to start with the word
#: "narration" is never mistaken for an unwritten section.
_PLACEHOLDER_TEXTS = {
    "narration.",
    _norm(_RECAP[2]),
    _norm(_HOOK[2]),
}


def _is_placeholder(narration: str) -> bool:
    return _norm(narration) in _PLACEHOLDER_TEXTS or not _norm(narration)


def build_prompt(script: Script, todo: list) -> str:
    outline = "\n".join(
        f"  {sec.index}. {sec.title}\n     ANIM: {sec.anim}" for sec in todo)
    return textwrap.dedent(f"""
    You are drafting the narration script for an educational explainer video
    titled "{script.title}" (topic: {script.meta.get('topic', script.title)})
    for an audience of {script.meta.get('audience', 'undergraduates')}.

    Write spoken narration -- plain prose meant to be read aloud, not slide
    text -- for these sections, in order. Each section's ANIM line describes
    what the viewer is looking at while this narration plays; write to that
    visual, but never describe it directly (no "as you can see here").

{outline}

    Rules:
      * ~140 spoken words per minute. Aim for a total of 700-1400 words
        across all {len(todo)} section(s), weighted by how much each
        section's ANIM brief has to cover.
      * Open on the question the viewer actually has. No "hello everyone,
        welcome back to the channel".
      * One idea per section, plain declarative sentences. This gets
        force-aligned word for word to synthesised audio, so avoid
        parentheticals or anything a text-to-speech voice would stumble
        reading aloud.
      * The last section should end on the question the next video answers.
      * Write ONLY the narration prose. No stage directions, no headers
        restating the ANIM brief, no markdown formatting, no bullet points.
      * When an ANIM line names a concrete running example (specific
        numbers or values), actually narrate what happens to those exact
        values at each step -- state the comparison, the swap, the move,
        whatever the step is -- not just the general rule it demonstrates.
        Reuse the same values in every section that continues the same
        trace; never switch to a different example partway through.

    Output format -- exactly this, one block per section, nothing else
    (bare "## <number>", no title, no dash):

    ## {todo[0].index}
    <narration for that section>
    """).strip()


def _parse_reply(text: str, expect: list[int]) -> dict[int, str]:
    heads = list(_REPLY_HEAD.finditer(text))
    out: dict[int, str] = {}
    for i, h in enumerate(heads):
        idx = int(h.group(1))
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[idx] = text[h.end():end].strip()
    missing = [i for i in expect if i not in out]
    if missing:
        sys.exit(f"[prompt2render] draft: model reply missing section(s) {missing}")
    return out


def _replace_section_body(raw: str, index: int, narration: str) -> str:
    lines = raw.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        m = _HEAD_LINE.match(line.rstrip("\n"))
        if not m:
            continue
        if int(m.group(1)) == index:
            start = i
        elif start is not None:
            end = i
            break
    if start is None:
        sys.exit(f"[prompt2render] draft: section {index} not found in script.md")
    if end is None:
        end = len(lines)

    anim_lines = [l for l in lines[start + 1:end] if l.strip().startswith(">")]
    new_body = anim_lines + ["\n", narration.strip() + "\n", "\n"]
    return "".join(lines[:start + 1] + new_body + lines[end:])


def draft(proj: Path, force: bool = False) -> Path:
    path = proj / "script.md"
    script = parse_script(path)

    todo = [s for s in script.sections if force or _is_placeholder(s.narration)]
    if not todo:
        cfg.say("every section already has narration -- nothing to draft "
                "(use --force to overwrite)")
        return path

    cfg.say(f"drafting narration for section(s) "
            f"{', '.join(str(s.index) for s in todo)}")
    prompt = build_prompt(script, todo)
    text = llm.complete(prompt, max_tokens=8000)
    by_index = _parse_reply(text, [s.index for s in todo])

    raw = path.read_text(encoding="utf-8")
    for sec in todo:
        raw = _replace_section_body(raw, sec.index, by_index[sec.index])
    path.write_text(raw, encoding="utf-8")

    cfg.say(f"wrote narration for section(s) "
            f"{', '.join(str(s.index) for s in todo)} into {path}")
    cfg.warn("AI-drafted narration is a starting point, not a finished script -- "
             "read it in your own voice and fix anything wrong before you "
             "`build`. If you ship it close to as-is, set the synthetic-content "
             "disclosure in YouTube Studio (see out/upload.md's checklist).")
    return path
