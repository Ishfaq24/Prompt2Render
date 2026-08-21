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

SCRIPT_TEMPLATE = """---
title: {title}
topic: {title}
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; 8-12 min total = 1100-1700 words. -->

## 1 - The hook
> ANIM: title card, then the one image that frames the whole problem

Open with the question the viewer actually has. No "hello everyone, welcome
back to the channel". Thirty seconds to earn the next eight minutes.

## 2 - The naive approach and why it breaks
> ANIM: walk the obvious method, then show it failing on a concrete case

Narration.

## 3 - The key idea
> ANIM: the central visual - this is the frame people screenshot

Narration.

## 4 - Worked example
> ANIM: step through one full concrete example, values visible on screen

Narration.

## 5 - Where this shows up in practice
> ANIM: real system diagram or benchmark

Narration.

## 6 - Recap and the next question
> ANIM: recap card with the 3 things to remember

Narration. End on the question your next video answers.
"""


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


def new_project(slug: str, title: str | None = None) -> Path:
    d = cfg.PROJECTS / slug
    if d.exists():
        raise SystemExit(f"[prompt2render] project '{slug}' already exists at {d}")
    for sub in ("sections", "audio", "build", "out"):
        (d / sub).mkdir(parents=True)
    title = title or slug.replace("-", " ").title()
    (d / "script.md").write_text(SCRIPT_TEMPLATE.format(title=title), encoding="utf-8")
    return d
