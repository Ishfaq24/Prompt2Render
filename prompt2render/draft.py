"""Draft narration for a fresh script.md.

``prompt2render new`` intentionally leaves narration unwritten. This module
provides an optional AI-generated starting draft while preserving the rule that
the resulting script remains human-reviewable before a build.

The implementation is deliberately conservative:
* authored narration is never overwritten unless ``force=True``;
* only placeholder sections are drafted by default;
* model output is parsed strictly by section index;
* existing ANIM directives and section structure are preserved;
* the file is written atomically so a failed write cannot corrupt script.md.
"""

from __future__ import annotations

import re
import sys
import textwrap
from pathlib import Path

from . import cfg, llm
from .project import _HOOK, _RECAP, Script, parse_script


_HEAD_LINE = re.compile(
    r"^##\s+(\d+)\s*[-–—.:]?\s*(.*)$"
)

_REPLY_HEAD = re.compile(
    r"^\s*##\s*(\d+)\s*$",
    re.M,
)


def _norm(text: str) -> str:
    """Normalize text only for placeholder comparison."""
    return " ".join(
        str(text).split()
    ).strip().lower()


def _template_text(value) -> str:
    """Safely extract a template string when the project constant is tuple-like."""
    if isinstance(value, str):
        return value

    try:
        return str(value[2])
    except (IndexError, KeyError, TypeError):
        return ""


# Exact placeholder strings emitted by project.render_template().
#
# The hook/recap constants are indexed defensively because they are internal
# project template structures rather than part of draft.py's public API.
_PLACEHOLDER_TEXTS = {
    "narration.",
    _norm(_template_text(_RECAP)),
    _norm(_template_text(_HOOK)),
}

# Empty strings are intentionally handled separately by _is_placeholder().
_PLACEHOLDER_TEXTS.discard("")


def _is_placeholder(narration: str) -> bool:
    """Return True only for genuinely unwritten narration."""
    normalized = _norm(narration)
    return (
        not normalized
        or normalized in _PLACEHOLDER_TEXTS
    )


def _word_target(script: Script, todo: list) -> tuple[int, int]:
    """Calculate a bounded total word target from section count.

    The previous implementation hard-coded 700–1400 words even for a single
    section or a very long multi-section script. A bounded per-section target
    gives the model a useful scale without pretending to know exact narration
    timing before synthesis.
    """
    minimum = max(
        80,
        120 * len(todo),
    )
    maximum = max(
        minimum,
        220 * len(todo),
    )

    # Keep the original project's overall ceiling for large batches.
    return (
        min(minimum, 1400),
        min(maximum, 1800),
    )


def build_prompt(
    script: Script,
    todo: list,
) -> str:
    """Build the single video-level narration drafting prompt."""
    if not todo:
        raise ValueError(
            "build_prompt requires at least one section"
        )

    outline = "\n".join(
        (
            f"  {section.index}. {section.title}\n"
            f"     ANIM: {section.anim}"
        )
        for section in todo
    )

    minimum, maximum = _word_target(
        script,
        todo,
    )

    first_index = todo[0].index

    return textwrap.dedent(
        f"""
        You are drafting the narration script for an educational explainer
        video titled "{script.title}" (topic:
        {script.meta.get("topic", script.title)})
        for an audience of
        {script.meta.get("audience", "undergraduates")}.

        Write spoken narration — plain prose meant to be read aloud, not slide
        text — for these sections, in order. Each section's ANIM line describes
        the visual state while the narration plays; write to that visual, but
        never describe the visual directly (avoid phrases such as "as you can
        see here").

        SECTIONS:
        {outline}

        Rules:
          * Target approximately 140 spoken words per minute.
          * Aim for approximately {minimum}-{maximum} words across these
            section(s), weighted by the amount of material each section must
            explain.
          * Open on the question the viewer actually has. Do not use
            "hello everyone", "welcome back", or channel-introduction filler.
          * One main idea per section. Use plain declarative sentences.
          * This narration will be force-aligned word-for-word to synthesized
            audio, so avoid parentheticals, unusual punctuation, abbreviations,
            and constructions that a text-to-speech voice may read awkwardly.
          * Preserve technical terminology exactly when it is necessary for
            correctness.
          * Do not invent numerical results, algorithm steps, examples, or
            claims that are absent from the section's brief or established
            context.
          * When an ANIM line names a concrete running example (specific
            numbers or values), narrate those exact values and their changes
            at each relevant step. Reuse the same values whenever the trace
            continues across sections; never silently switch examples.
          * If a section contains an explicit illegal-rule demonstration,
            explain the rule and the demonstrated violation accurately rather
            than pretending the illegal state is valid.
          * The final section should close naturally toward the question that
            the next video or concept answers. Do not append a generic
            "thanks for watching".
          * Write ONLY narration prose inside each numbered block.
          * Do not include stage directions, ANIM text, markdown bullets, code,
            citations, or extra commentary.

        OUTPUT FORMAT:
        Return exactly one block for every requested section.
        Use a bare "## <number>" heading and nothing else on that heading line.

        ## {first_index}
        <narration for that section>
        """
    ).strip()


def _strip_code_fence(text: str) -> str:
    """Remove an accidental outer markdown fence from an LLM response."""
    value = text.strip()

    if not value.startswith("```"):
        return value

    lines = value.splitlines()

    if lines:
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _parse_reply(
    text: str,
    expect: list[int],
) -> dict[int, str]:
    """Parse and validate section-numbered model output."""
    cleaned = _strip_code_fence(text)

    heads = list(
        _REPLY_HEAD.finditer(cleaned)
    )

    if not heads:
        sys.exit(
            "[prompt2render] draft: model returned no "
            "numbered sections; refusing to modify script.md"
        )

    expected = set(expect)
    output: dict[int, str] = {}
    duplicates: set[int] = set()
    unexpected: set[int] = set()

    for position, heading in enumerate(heads):
        index = int(
            heading.group(1)
        )

        end = (
            heads[position + 1].start()
            if position + 1 < len(heads)
            else len(cleaned)
        )

        body = cleaned[
            heading.end():end
        ].strip()

        if index in output:
            duplicates.add(index)
            continue

        if index not in expected:
            unexpected.add(index)
            continue

        if not body:
            sys.exit(
                f"[prompt2render] draft: section "
                f"{index} has empty narration"
            )

        output[index] = body

    missing = [
        index
        for index in expect
        if index not in output
    ]

    problems = []

    if missing:
        problems.append(
            f"missing section(s) {missing}"
        )

    if duplicates:
        problems.append(
            f"duplicate section(s) "
            f"{sorted(duplicates)}"
        )

    if unexpected:
        problems.append(
            f"unexpected section(s) "
            f"{sorted(unexpected)}"
        )

    if problems:
        sys.exit(
            "[prompt2render] draft: model reply invalid — "
            + "; ".join(problems)
        )

    return output


def _replace_section_body(
    raw: str,
    index: int,
    narration: str,
) -> str:
    """Replace only the prose body of one section.

    Existing blockquote directives such as ``> ANIM:`` are retained. Other
    markdown content inside the section is intentionally replaced because the
    narration draft owns the prose region between this section heading and the
    next section heading.
    """
    if not narration.strip():
        raise ValueError(
            f"empty narration for section {index}"
        )

    lines = raw.splitlines(
        keepends=True
    )

    start: int | None = None
    end: int | None = None

    for position, line in enumerate(lines):
        match = _HEAD_LINE.match(
            line.rstrip("\r\n")
        )

        if not match:
            continue

        current_index = int(
            match.group(1)
        )

        if current_index == index:
            start = position
            continue

        if (
            start is not None
            and current_index != index
        ):
            end = position
            break

    if start is None:
        raise SystemExit(
            f"[prompt2render] draft: section "
            f"{index} not found in script.md"
        )

    if end is None:
        end = len(lines)

    # Preserve all directive lines. This is deliberately broader than just
    # "> ANIM:" because future script templates may contain other directives.
    directives = [
        line.rstrip("\r\n")
        for line in lines[start + 1:end]
        if line.lstrip().startswith(">")
    ]

    new_body: list[str] = []

    for directive in directives:
        new_body.append(
            directive + "\n"
        )

    if directives:
        new_body.append("\n")

    new_body.append(
        narration.strip() + "\n"
    )

    # Keep one blank line before the next section for stable formatting.
    new_body.append("\n")

    return "".join(
        lines[:start + 1]
        + new_body
        + lines[end:]
    )


def _atomic_write(
    path: Path,
    content: str,
) -> None:
    """Write script.md atomically."""
    temporary = path.with_name(
        path.name + ".draft.tmp"
    )

    try:
        temporary.write_text(
            content,
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(
            missing_ok=True
        )


def draft(
    proj: Path,
    force: bool = False,
) -> Path:
    """Draft narration for placeholder sections in ``proj/script.md``."""
    path = proj / "script.md"

    if not path.exists():
        sys.exit(
            f"[prompt2render] draft: missing "
            f"{path}"
        )

    script = parse_script(path)

    todo = [
        section
        for section in script.sections
        if (
            force
            or _is_placeholder(
                section.narration
            )
        )
    ]

    if not todo:
        cfg.say(
            "every section already has narration — "
            "nothing to draft "
            "(use --force to overwrite)"
        )
        return path

    indices = [
        section.index
        for section in todo
    ]

    cfg.say(
        "drafting narration for section(s) "
        + ", ".join(
            str(index)
            for index in indices
        )
    )

    prompt = build_prompt(
        script,
        todo,
    )

    try:
        text = llm.complete(
            prompt,
            max_tokens=8000,
            label="narration-draft",
        )
    except TypeError:
        # Compatibility with older llm.complete() signatures.
        text = llm.complete(
            prompt,
            max_tokens=8000,
        )

    if not isinstance(text, str) or not text.strip():
        sys.exit(
            "[prompt2render] draft: LLM returned "
            "an empty response; script.md was not changed"
        )

    by_index = _parse_reply(
        text,
        indices,
    )

    raw = path.read_text(
        encoding="utf-8"
    )

    # Construct the entire replacement before touching disk. If any section
    # cannot be found, the original script remains untouched.
    updated = raw

    for section in todo:
        updated = _replace_section_body(
            updated,
            section.index,
            by_index[section.index],
        )

    _atomic_write(
        path,
        updated,
    )

    cfg.say(
        "wrote narration for section(s) "
        + ", ".join(
            str(index)
            for index in indices
        )
        + f" into {path}"
    )

    cfg.warn(
        "AI-drafted narration is a starting point, "
        "not a finished script — read it in your own "
        "voice and verify every technical claim before "
        "you `build`. If you ship it close to as-is, "
        "set the synthetic-content disclosure in "
        "YouTube Studio (see out/upload.md's checklist)."
    )

    return path


__all__ = [
    "build_prompt",
    "draft",
]