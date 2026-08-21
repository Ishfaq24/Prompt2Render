"""Stage 4 - the upload packet.

Writes out/upload.md: description with chapters, tags, and the checks
worth running before anything goes public. Nothing here is automated on
purpose — the last human look is what keeps the channel on the right side
of the inauthentic-content rule.
"""
from __future__ import annotations

from pathlib import Path

from . import assemble
from .project import Script

TEMPLATE = """# Upload packet — {title}

## Title options (pick one, keep under 60 chars)
1. {title}
2. {title} — Explained Visually
3. How {short} Actually Works

## Description
{hook}

Chapters:
{chapters}

---
Timestamps and animations by me. Source notes and slides: <link>
Corrections welcome in the comments — I pin the good ones.

#computerscience #{tag1} #{tag2}

## Tags
{tags}

## Files
- video ....... out/final.mp4
- captions .... out/captions.srt   (upload as a subtitle track, don't rely on auto-CC)
- thumb base .. out/thumb_source.png

## Pre-upload checks
- [ ] Watched it end to end at 1x. Any frame where text overlaps a shape?
      That is the failure mode the Code2Video paper's own human raters
      punished hardest — fix it in the Manim source and `prompt2render rerender`.
- [ ] First 30 seconds: does it open on the question, not on a greeting?
- [ ] Audio: no clipping, consistent level between sections.
- [ ] Captions read correctly (check any symbol-heavy section).
- [ ] Thumbnail: one idea, readable at 120px wide.
- [ ] Synthetic voice or AI-generated visuals used? Set the
      "altered or synthetic content" disclosure in YouTube Studio.
      When unsure, disclose — the cost of disclosing is nil, the cost of
      not disclosing is a strike sequence.
- [ ] Is this genuinely different from your last upload in structure and
      substance, not just topic? If three uploads in a row share a template
      with no original analysis, that is the inauthentic-content pattern.
- [ ] End screen points at the specific next video, not "subscribe".

## Notes
Spoken word count: {words} (~{minutes:.1f} min at 140 wpm)
Sections: {nsections}
"""


def build_packet(proj: Path, script: Script) -> Path:
    words = script.word_count
    short = script.title.split("—")[0].split(":")[0].strip()
    hook = (script.sections[0].narration.split("\n")[0][:220]
            if script.sections else "")
    topic_words = [w.lower() for w in script.title.replace("-", " ").split()
                   if len(w) > 3]
    tags = ", ".join(dict.fromkeys(topic_words + [
        "computer architecture", "computer science", "explained",
        "visual explanation", "manim", "tutorial",
    ]))
    dst = proj / "out" / "upload.md"
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(TEMPLATE.format(
        title=script.title,
        short=short,
        hook=hook,
        chapters=assemble.chapters(script),
        tags=tags,
        tag1=(topic_words[0] if topic_words else "explained"),
        tag2=(topic_words[1] if len(topic_words) > 1 else "tutorial"),
        words=words,
        minutes=words / 140,
        nsections=len(script.sections),
    ), encoding="utf-8")
    return dst
