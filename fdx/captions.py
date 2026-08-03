"""Captions, timed from the alignment and nothing else.

Two defects this replaces.

The old `assemble.write_srt` shared each section's time out in proportion to
how many *characters* a chunk had, which drifts the moment the voice pauses or
speeds up — and it allowed 84 characters on one line, about double the
broadcast norm.

The newer `write_measured_srt` used real cue times but advanced its running
offset by the *video* duration of each section while the audio advanced by
AAC-encoded durations. Two clocks that diverge by a few milliseconds per
section, so captions drift steadily toward the end of a long video. Here there
is one clock: sample offsets in build/master.wav.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from . import align, cfg, textseg, voice
from .project import Script

MIN_GAP = 2 / cfg.FPS          # never let two cards touch


def _ts(t: float, sep: str = ",") -> str:
    t = max(t, 0.0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s % 1) * 1000)):03d}"


def _ass_ts(t: float) -> str:
    t = max(t, 0.0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):d}:{int(m):02d}:{s:05.2f}"


def _fits(words: list[dict], max_line: int, max_lines: int) -> bool:
    text = " ".join(w["w"] for w in words)
    return len(textseg.caption_lines(text, max_line, max_lines)) <= 1


def _cards(words: list[dict], max_line: int, max_lines: int) -> list[list[dict]]:
    """Pack a sentence's words into cards, preferring to break on a real pause.

    Word times give a much better split point than a character count: the
    place a sentence naturally divides is where the speaker took a breath.
    """
    if not words:
        return []
    gaps = [b["s"] - a["e"] for a, b in zip(words, words[1:])] + [0.0]
    typical = statistics.median([g for g in gaps if g >= 0] or [0.0])

    cards, start = [], 0
    while start < len(words):
        # Longest run that still fits on one card.
        end = start + 1
        while end < len(words) and _fits(words[start:end + 1], max_line, max_lines):
            end += 1
        if end < len(words):
            # Among the last few feasible break points, take the one followed
            # by the biggest silence.
            lo = max(start + 1, end - 4)
            best = max(range(lo, end + 1),
                       key=lambda j: gaps[j - 1] if j - 1 < len(gaps) else 0)
            if gaps[best - 1] > typical * 1.5:
                end = best
        cards.append(words[start:end])
        start = end
    return cards


def _constrain(cards: list[dict]) -> list[dict]:
    """Apply the subtitle timing rules that make captions comfortable."""
    for i, c in enumerate(cards):
        dur = c["end"] - c["start"]
        chars = len(c["text"].replace("\n", " "))
        want = max(cfg.CAPTION_MIN_S, chars / cfg.CAPTION_CPS)
        if dur < want:
            ceiling = (cards[i + 1]["start"] - MIN_GAP
                       if i + 1 < len(cards) else c["end"] + want)
            c["end"] = min(max(c["end"], c["start"] + want), max(ceiling, c["end"]))
        if c["end"] - c["start"] > cfg.CAPTION_MAX_S:
            c["end"] = c["start"] + cfg.CAPTION_MAX_S

    for a, b in zip(cards, cards[1:]):
        if a["end"] > b["start"] - MIN_GAP:
            a["end"] = max(b["start"] - MIN_GAP, a["start"] + 0.2)
    return cards


def cards_for(proj: Path, script: Script) -> list[dict]:
    """Every caption card in the video, on the master-audio clock."""
    amap = voice.audio_map(proj)
    out: list[dict] = []
    for sec in script.sections:
        offset = amap["sections"][sec.stem]["start"]
        data = align.load(proj, sec.stem)
        for sent in data["sentences"]:
            words = sent.get("words") or []
            if not words:
                # No word detail (a v1 alignment): the sentence is one card.
                for card in textseg.caption_lines(sent["text"]):
                    out.append({"start": offset + sent["start"],
                                "end": offset + sent["end"],
                                "text": "\n".join(card), "words": []})
                continue
            for group in _cards(words, cfg.CAPTION_LINE, cfg.CAPTION_LINES):
                text = " ".join(w["w"] for w in group)
                lines = textseg.caption_lines(text, cfg.CAPTION_LINE,
                                              cfg.CAPTION_LINES)
                out.append({
                    "start": offset + group[0]["s"],
                    "end": offset + group[-1]["e"],
                    "text": "\n".join(lines[0]) if lines else text,
                    "words": [{"w": w["w"], "s": offset + w["s"],
                               "e": offset + w["e"]} for w in group],
                })
    return _constrain(out)


def write_srt(proj: Path, script: Script, dst: Path) -> Path:
    lines = []
    for n, c in enumerate(cards_for(proj, script), start=1):
        lines += [str(n), f"{_ts(c['start'])} --> {_ts(c['end'])}", c["text"], ""]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines), encoding="utf-8")
    return dst


_ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: fdx,{font},54,&H00FFFFFF,&H0000C8FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,2,80,80,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(proj: Path, script: Script, dst: Path) -> Path:
    """Karaoke captions: each word lights up as it is spoken.

    Only possible because alignment gives real word times. Opt-in, and the
    SRT stays the shipped artefact — YouTube prefers a separate subtitle file
    for the main upload.
    """
    body = [_ASS_HEAD.format(w=cfg.WIDTH, h=cfg.HEIGHT, font=cfg.CAPTION_FONT)]
    for c in cards_for(proj, script):
        if c["words"]:
            parts = []
            cursor = c["start"]
            for w in c["words"]:
                lead = max(int(round((w["s"] - cursor) * 100)), 0)
                if lead:
                    parts.append(f"{{\\k{lead}}}")
                dur = max(int(round((w["e"] - w["s"]) * 100)), 1)
                parts.append(f"{{\\kf{dur}}}{w['w']} ")
                cursor = w["e"]
            text = "".join(parts).strip()
        else:
            text = c["text"].replace("\n", r"\N")
        text = text.replace("\n", r"\N")
        body.append(f"Dialogue: 0,{_ass_ts(c['start'])},{_ass_ts(c['end'])},"
                    f"fdx,,0,0,0,,{text}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(body) + "\n", encoding="utf-8")
    return dst
