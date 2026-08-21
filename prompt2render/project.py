"""Create a project folder and parse its script.md.

script.md is the single source of truth: your narration, your section
titles, and the animation brief handed to `prompt2render scenes` for storyboarding.
Everything downstream (audio, sync, captions, chapters) is derived from it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cfg

#: The fixed hook and recap beats -- every video opens on the question and
#: closes on the next one, regardless of length.
_HOOK = (
    "The hook",
    "title card, then the one image that frames the whole problem",
    'Open with the question the viewer actually has. No "hello everyone, welcome\n'
    'back to the channel". Thirty seconds to earn the next eight minutes.',
)
_RECAP = (
    "Recap and the next question",
    "recap card with the 3 things to remember",
    "Narration. End on the question your next video answers.",
)

#: Body beats in priority order. `_body_sections(n)` takes the first n for a
#: short video and falls back to generic slots once this list runs out --
#: this is a generic explainer arc, not a topic-aware outline, so it is only
#: ever a starting point to rename.
_BODY_ARCHETYPES = [
    ("The naive approach and why it breaks",
     "walk the obvious method, then show it failing on a concrete case"),
    ("The key idea",
     "the central visual - this is the frame people screenshot"),
    ("Worked example",
     "step through one full concrete example, values visible on screen"),
    ("Where this shows up in practice",
     "real system diagram or benchmark"),
    ("Trade-offs and where it breaks down",
     "the case where this approach fails, side by side with one where it works"),
    ("How it compares to the alternative",
     "put this approach next to the other common one, same input"),
    ("Complexity and cost",
     "the growth curve, plotted, not just claimed"),
]

_MIN_SECTIONS = 2       # hook + recap, no body -- a teaser-length floor
_MAX_SECTIONS = 40      # a sanity ceiling, not a real editorial limit


def _body_sections(n: int) -> list[tuple[str, str]]:
    if n <= len(_BODY_ARCHETYPES):
        return _BODY_ARCHETYPES[:n]
    extra = [(f"Body beat {i}", "one visual for this idea")
             for i in range(len(_BODY_ARCHETYPES) + 1, n + 1)]
    return _BODY_ARCHETYPES + extra


def _resolve_outline(minutes: float | None, sections: int | None) -> tuple[int, float]:
    """(section count, nominal minutes for the word-count guidance comment).

    `--sections` picks the count directly; `--minutes` derives it from a
    rough 2-minutes-per-body-beat pace (the ratio the original fixed
    6-section/8-12-min template implied: 4 body beats over ~10 minutes).
    Neither given reproduces the old fixed template exactly (10 min, 6
    sections).
    """
    if sections is not None:
        n = max(_MIN_SECTIONS, min(_MAX_SECTIONS, int(sections)))
        if minutes is None:
            minutes = max(3, 2 * (n - 2) + 1)
        return n, minutes
    minutes = 10.0 if minutes is None else max(1.0, float(minutes))
    body = max(0, round(minutes / 2) - 1)
    n = max(_MIN_SECTIONS, min(_MAX_SECTIONS, body + 2))
    return n, minutes


def render_template(title: str, minutes: float | None = None,
                    sections: int | None = None) -> str:
    n, minutes = _resolve_outline(minutes, sections)
    parts = [_front_matter(title, minutes, n)]

    def block(i, title_, anim, narration):
        parts.append(f"\n## {i} - {title_}\n> ANIM: {anim}\n\n{narration}\n")

    block(1, *_HOOK)
    for i, (t, anim) in enumerate(_body_sections(n - 2), start=2):
        block(i, t, anim, "Narration.")
    block(n, *_RECAP)
    return "".join(parts)


def _front_matter(title: str, minutes: float, n: int, ai: bool = False,
                  topic: str | None = None) -> str:
    words = round(minutes * 140)
    note = ("This outline was AI-suggested" if ai else "This is a starting outline")
    return f"""---
title: {title}
topic: {topic or title}
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; ~{minutes:g} min total = ~{words} words
     across {n} section(s). {note} -- add, remove or rename sections freely,
     and every section still needs real narration before you build. -->
"""


def render_from_sections(title: str, sections: list[dict],
                         minutes: float | None = None,
                         topic: str | None = None) -> str:
    """Render script.md from an explicit [{"title", "anim"}, ...] list.

    Used by `new --ai`: the section structure (count, titles, briefs), and
    optionally a distinct topic summary, come from outline.generate()
    rather than the fixed archetypes above -- but narration is still left
    as a placeholder either way -- see draft.py.
    """
    n = len(sections)
    if minutes is None:
        minutes = max(3, 2 * (n - 2) + 1) if n > 2 else 3.0
    parts = [_front_matter(title, minutes, n, ai=True, topic=topic)]
    for i, s in enumerate(sections, start=1):
        parts.append(f"\n## {i} - {s['title']}\n> ANIM: {s['anim']}\n\nNarration.\n")
    return "".join(parts)


@dataclass
class Section:
    index: int
    title: str
    anim: str = ""
    narration: str = ""
    audio: Path | None = None
    video: Path | None = None
    start: float = 0.0
    dur: float = 0.0

    @property
    def stem(self) -> str:
        return f"{self.index:02d}"


@dataclass
class Script:
    meta: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.meta.get("title", "Untitled")

    @property
    def word_count(self) -> int:
        return sum(len(s.narration.split()) for s in self.sections)


_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_HEAD = re.compile(r"^##\s+(\d+)\s*[-\u2013\u2014.:]?\s*(.*)$", re.M)


def parse_script(path: Path) -> Script:
    raw = path.read_text(encoding="utf-8")

    meta: dict = {}
    m = _FRONT.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        raw = raw[m.end():]

    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)

    heads = list(_HEAD.finditer(raw))
    if not heads:
        raise SystemExit("[prompt2render] script.md has no '## 1 - Title' section headers")

    sections: list[Section] = []
    for i, h in enumerate(heads):
        body = raw[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(raw)]
        anim_lines, narration_lines = [], []
        for line in body.splitlines():
            s = line.strip()
            if s.upper().startswith("> ANIM:"):
                anim_lines.append(s.split(":", 1)[1].strip())
            elif s.startswith(">"):
                continue
            else:
                narration_lines.append(line)
        narration = re.sub(r"\n{2,}", "\n\n", "\n".join(narration_lines)).strip()
        sections.append(Section(
            index=int(h.group(1)),
            title=h.group(2).strip() or f"Section {h.group(1)}",
            anim=" ".join(anim_lines),
            narration=narration,
        ))
    return Script(meta=meta, sections=sections)


def _scaffold_dirs(slug: str) -> Path:
    d = cfg.PROJECTS / slug
    if d.exists():
        raise SystemExit(f"[prompt2render] project '{slug}' already exists at {d}")
    for sub in ("sections", "audio", "build", "out"):
        (d / sub).mkdir(parents=True)
    return d


def new_project(slug: str, title: str | None = None, minutes: float | None = None,
                sections: int | None = None) -> Path:
    d = _scaffold_dirs(slug)
    title = title or slug.replace("-", " ").title()
    (d / "script.md").write_text(
        render_template(title, minutes=minutes, sections=sections), encoding="utf-8")
    return d


def new_project_from_sections(slug: str, title: str, sections: list[dict],
                              minutes: float | None = None,
                              topic: str | None = None) -> Path:
    """Like new_project(), but the section structure is already decided --
    used by `new --ai` with outline.generate()'s output."""
    d = _scaffold_dirs(slug)
    (d / "script.md").write_text(
        render_from_sections(title, sections, minutes=minutes, topic=topic),
        encoding="utf-8")
    return d
