"""Create a project folder and parse its script.md.

script.md is the single source of truth: narration, section titles, and the
animation brief handed to ``prompt2render scenes`` for storyboarding.

Everything downstream (audio, sync, captions, chapters) is derived from it.

The module deliberately keeps the script contract strict. AI-generated outlines,
human-edited scripts, and pedagogy revisions all pass through the same parser
and section structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cfg


# ---------------------------------------------------------------------------
# Default deterministic outline
# ---------------------------------------------------------------------------

#: Fixed hook and recap beats. Every video opens on a question and closes
#: toward the next question, regardless of length.
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


#: Body beats in priority order. These are only deterministic starting points.
#: ``new --ai`` uses outline.py instead and therefore does not depend on these
#: generic archetypes.
_BODY_ARCHETYPES = [
    (
        "The naive approach and why it breaks",
        "walk the obvious method, then show it failing on a concrete case",
    ),
    (
        "The key idea",
        "the central visual - this is the frame people screenshot",
    ),
    (
        "Worked example",
        "step through one full concrete example, values visible on screen",
    ),
    (
        "Where this shows up in practice",
        "real system diagram or benchmark",
    ),
    (
        "Trade-offs and where it breaks down",
        "the case where this approach fails, side by side with one where it works",
    ),
    (
        "How it compares to the alternative",
        "put this approach next to the other common one, same input",
    ),
    (
        "Complexity and cost",
        "the growth curve, plotted, not just claimed",
    ),
]

_MIN_SECTIONS = 2
_MAX_SECTIONS = 40


def _body_sections(n: int) -> list[tuple[str, str]]:
    """Return ``n`` deterministic body beats."""
    if n <= 0:
        return []

    if n <= len(_BODY_ARCHETYPES):
        return _BODY_ARCHETYPES[:n]

    extra = [
        (f"Body beat {i}", "one visual for this idea")
        for i in range(len(_BODY_ARCHETYPES) + 1, n + 1)
    ]

    return _BODY_ARCHETYPES + extra


def _resolve_outline(
    minutes: float | None,
    sections: int | None,
) -> tuple[int, float]:
    """Return ``(section_count, nominal_minutes)``.

    ``--sections`` takes precedence over the section count derived from
    ``--minutes``.
    """
    if sections is not None:
        try:
            requested = int(sections)
        except (TypeError, ValueError):
            raise SystemExit(
                "[prompt2render] sections must be an integer"
            ) from None

        n = max(_MIN_SECTIONS, min(_MAX_SECTIONS, requested))

        if minutes is None:
            minutes = max(3.0, 2 * (n - 2) + 1)

        return n, float(minutes)

    minutes = 10.0 if minutes is None else float(minutes)

    if minutes <= 0:
        raise SystemExit(
            "[prompt2render] minutes must be greater than zero"
        )

    body = max(0, round(minutes / 2) - 1)
    n = max(
        _MIN_SECTIONS,
        min(_MAX_SECTIONS, body + 2),
    )

    return n, minutes


# ---------------------------------------------------------------------------
# Script rendering
# ---------------------------------------------------------------------------

def _front_matter(
    title: str,
    minutes: float,
    n: int,
    *,
    ai: bool = False,
    topic: str | None = None,
) -> str:
    """Render the canonical script front matter."""
    title = str(title).strip()
    topic = str(topic or title).strip()

    words = round(minutes * 140)

    note = (
        "This outline was AI-suggested"
        if ai
        else
        "This is a starting outline"
    )

    return f"""---
title: {title}
topic: {topic}
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~{minutes:g} min total = ~{words} words
     across {n} section(s). {note} -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->
"""


def render_template(
    title: str,
    minutes: float | None = None,
    sections: int | None = None,
) -> str:
    """Render the deterministic starter script."""
    n, minutes = _resolve_outline(minutes, sections)

    title = str(title).strip()

    if not title:
        raise SystemExit("[prompt2render] project title cannot be empty")

    parts = [
        _front_matter(
            title,
            minutes,
            n,
            ai=False,
            topic=title,
        )
    ]

    def block(
        index: int,
        section_title: str,
        anim: str,
        narration: str,
    ) -> None:
        parts.append(
            f"\n## {index} - {section_title}\n"
            f"> ANIM: {anim}\n\n"
            f"{narration}\n"
        )

    block(1, *_HOOK)

    for index, (section_title, anim) in enumerate(
        _body_sections(n - 2),
        start=2,
    ):
        block(
            index,
            section_title,
            anim,
            "Narration.",
        )

    block(n, *_RECAP)

    return "".join(parts)


def _validate_outline_sections(
    sections: list[dict],
) -> list[dict]:
    """Validate and normalize an AI-generated section list.

    The outline is rejected before it reaches disk if it contains malformed,
    duplicate, empty, or structurally unsafe entries.
    """
    if not isinstance(sections, list):
        raise SystemExit(
            "[prompt2render] outline: sections must be a list"
        )

    if not sections:
        raise SystemExit(
            "[prompt2render] outline: sections list is empty"
        )

    if len(sections) < _MIN_SECTIONS:
        raise SystemExit(
            f"[prompt2render] outline: at least {_MIN_SECTIONS} "
            "sections are required"
        )

    if len(sections) > _MAX_SECTIONS:
        raise SystemExit(
            f"[prompt2render] outline: maximum {_MAX_SECTIONS} "
            "sections allowed"
        )

    normalized: list[dict] = []

    for position, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise SystemExit(
                f"[prompt2render] outline: section {position} "
                "is not an object"
            )

        title = str(section.get("title", "")).strip()
        anim = str(section.get("anim", "")).strip()

        if not title:
            raise SystemExit(
                f"[prompt2render] outline: section {position} "
                "has no title"
            )

        if not anim:
            raise SystemExit(
                f"[prompt2render] outline: section {position} "
                "has no ANIM brief"
            )

        if len(title) > 120:
            raise SystemExit(
                f"[prompt2render] outline: section {position} "
                "title is excessively long"
            )

        normalized.append(
            {
                "title": title,
                "anim": anim,
            }
        )

    return normalized


def render_from_sections(
    title: str,
    sections: list[dict],
    minutes: float | None = None,
    topic: str | None = None,
) -> str:
    """Render script.md from an explicit ``[{"title", "anim"}, ...]`` list.

    Used by ``new --ai``. The AI decides the section structure and optionally
    the topic summary; narration remains a placeholder and is filled by
    ``prompt2render draft`` or manually.
    """
    title = str(title).strip()

    if not title:
        raise SystemExit(
            "[prompt2render] project title cannot be empty"
        )

    sections = _validate_outline_sections(sections)

    n = len(sections)

    if minutes is None:
        minutes = (
            max(3.0, 2 * (n - 2) + 1)
            if n > 2
            else 3.0
        )
    else:
        minutes = float(minutes)
        if minutes <= 0:
            raise SystemExit(
                "[prompt2render] minutes must be greater than zero"
            )

    parts = [
        _front_matter(
            title,
            minutes,
            n,
            ai=True,
            topic=topic or title,
        )
    ]

    for index, section in enumerate(sections, start=1):
        parts.append(
            f"\n## {index} - {section['title']}\n"
            f"> ANIM: {section['anim']}\n\n"
            "Narration.\n"
        )

    return "".join(parts)


# ---------------------------------------------------------------------------
# Parsed script model
# ---------------------------------------------------------------------------

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
    renderer: str | None = None
    media_type: str = "auto"
    source_media: Path | None = None

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
        return sum(
            len(section.narration.split())
            for section in self.sections
        )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FRONT = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.S,
)

_HEAD = re.compile(
    r"^##\s+(\d+)\s*[-–—.:]?\s*(.*?)\s*$",
    re.M,
)


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    """Parse the intentionally small YAML-like front matter.

    This is not intended to be a general YAML parser. The script contract uses
    simple scalar ``key: value`` fields.
    """
    meta: dict[str, str] = {}

    match = _FRONT.match(raw)

    if not match:
        return meta, raw

    for line in match.group(1).splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        key = key.strip()
        value = value.strip()

        if not key:
            continue

        # Remove matching surrounding quotes while preserving internal content.
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]

        meta[key] = value

    return meta, raw[match.end():]


def _clean_narration(lines: list[str]) -> str:
    """Normalize narration whitespace without altering its wording."""
    text = "\n".join(lines)

    text = re.sub(
        r"\n{2,}",
        "\n\n",
        text,
    )

    return text.strip()


def _validate_sections(sections: list[Section]) -> None:
    """Validate the canonical parsed script structure."""
    if not sections:
        raise SystemExit(
            "[prompt2render] script.md has no sections"
        )

    seen: set[int] = set()

    for section in sections:
        if section.index in seen:
            raise SystemExit(
                f"[prompt2render] script.md has duplicate section "
                f"number {section.index}"
            )

        seen.add(section.index)

        if section.index <= 0:
            raise SystemExit(
                f"[prompt2render] script.md has invalid section "
                f"number {section.index}"
            )

        if not section.title.strip():
            raise SystemExit(
                f"[prompt2render] section {section.index} has no title"
            )

        if not section.anim.strip():
            raise SystemExit(
                f"[prompt2render] section {section.index} has no ANIM brief"
            )

    expected = set(range(1, len(sections) + 1))

    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)

        detail = []

        if missing:
            detail.append(
                "missing " + ", ".join(map(str, missing))
            )

        if extra:
            detail.append(
                "unexpected " + ", ".join(map(str, extra))
            )

        raise SystemExit(
            "[prompt2render] script.md section numbering must be "
            f"contiguous starting at 1 ({'; '.join(detail)})"
        )


def parse_script(path: Path) -> Script:
    """Parse ``script.md`` into the canonical Script representation."""
    if not path.exists():
        raise SystemExit(
            f"[prompt2render] missing script: {path}"
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"[prompt2render] cannot read {path}: {exc}"
        ) from exc

    meta, raw = _parse_front_matter(raw)

    # Remove instructional comments before parsing sections.
    raw = re.sub(
        r"<!--.*?-->",
        "",
        raw,
        flags=re.S,
    )

    heads = list(_HEAD.finditer(raw))

    if not heads:
        raise SystemExit(
            "[prompt2render] script.md has no "
            "'## 1 - Title' section headers"
        )

    sections: list[Section] = []

    for i, head in enumerate(heads):
        end = (
            heads[i + 1].start()
            if i + 1 < len(heads)
            else len(raw)
        )

        body = raw[head.end():end]

        anim_lines: list[str] = []
        narration_lines: list[str] = []
        media_type = "auto"
        source_media: Path | None = None

        for line in body.splitlines():
            stripped = line.strip()

            if stripped.upper().startswith("> ANIM:"):
                value = stripped.split(":", 1)[1].strip()
                if value:
                    anim_lines.append(value)

            elif stripped.upper().startswith("> VIDEO:"):
                value = stripped.split(":", 1)[1].strip()
                media_type = "video"
                if value:
                    source_media = Path(value)
                    anim_lines.append(f"[video] {value}")

            elif stripped.upper().startswith("> 3D:"):
                value = stripped.split(":", 1)[1].strip()
                media_type = "manim_3d"
                if value:
                    anim_lines.append(f"[3d] {value}")

            elif stripped.upper().startswith("> SPLIT:"):
                value = stripped.split(":", 1)[1].strip()
                media_type = "split"
                if value:
                    anim_lines.append(f"[split] {value}")

            elif stripped.startswith(">"):
                # Other blockquote lines are treated as editorial metadata,
                # not spoken narration.
                continue

            else:
                narration_lines.append(line)

        anim_text = " ".join(anim_lines).strip()
        lower_anim = anim_text.lower()
        if media_type == "auto":
            if "[3d]" in lower_anim or "[manim_3d]" in lower_anim:
                media_type = "manim_3d"
            elif "[split]" in lower_anim:
                media_type = "split"
            elif "[video" in lower_anim or "[broll" in lower_anim:
                media_type = "video"
                m = re.search(r"\[(?:video|broll)[:=]([^\]]+)\]", anim_text, re.IGNORECASE)
                if m:
                    source_media = Path(m.group(1).strip())

        section = Section(
            index=int(head.group(1)),
            title=head.group(2).strip()
            or f"Section {head.group(1)}",
            anim=anim_text,
            narration=_clean_narration(narration_lines),
            renderer=meta.get("renderer"),
            media_type=media_type,
            source_media=source_media,
        )

        sections.append(section)

    # The parser deliberately does not reorder the user's script. Ordering is
    # part of the source document and therefore must be correct in the file.
    _validate_sections(sections)

    return Script(
        meta=meta,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# Project creation
# ---------------------------------------------------------------------------

def _scaffold_dirs(slug: str) -> Path:
    """Create the standard project directory structure."""
    clean_slug = cfg.validate_slug(slug)

    d = cfg.PROJECTS / clean_slug

    if d.exists():
        raise SystemExit(
            f"[prompt2render] project '{clean_slug}' already exists at {d}"
        )

    for sub in (
        "sections",
        "audio",
        "build",
        "out",
    ):
        (d / sub).mkdir(
            parents=True,
            exist_ok=False,
        )

    return d


def new_project(
    slug: str,
    title: str | None = None,
    minutes: float | None = None,
    sections: int | None = None,
) -> Path:
    """Create a deterministic Prompt2Render project."""
    if any(sep in str(slug) for sep in ('/', '\\', '..', ':', '\0')):
        slug = cfg.validate_slug(slug)
    else:
        slug = cfg.slugify(slug)
    d = _scaffold_dirs(slug)

    title = (
        title.strip()
        if title and title.strip()
        else slug.replace("-", " ").title()
    )

    script = render_template(
        title,
        minutes=minutes,
        sections=sections,
    )

    script_path = d / "script.md"

    script_path.write_text(
        script,
        encoding="utf-8",
    )

    return d


def new_project_from_sections(
    slug: str,
    title: str,
    sections: list[dict],
    minutes: float | None = None,
    topic: str | None = None,
) -> Path:
    """Create a project whose section structure is already decided.

    Used by ``new --ai`` with ``outline.generate()``.
    """
    if any(sep in str(slug) for sep in ('/', '\\', '..', ':', '\0')):
        slug = cfg.validate_slug(slug)
    else:
        slug = cfg.slugify(slug)
    d = _scaffold_dirs(slug)

    script = render_from_sections(
        title,
        sections,
        minutes=minutes,
        topic=topic,
    )

    script_path = d / "script.md"

    script_path.write_text(
        script,
        encoding="utf-8",
    )

    return d