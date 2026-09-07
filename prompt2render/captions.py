"""Caption generation from alignment timestamps.

Captions use the master-audio clock rather than section/video durations.  Word
timestamps come from the alignment and are therefore the authoritative timing
source; character-proportional timing is not used when word alignment exists.

The module produces:
* SRT for normal subtitle delivery;
* optional ASS with word-level karaoke timing.

Caption packing is deterministic and constrained by readability and timing
limits from ``cfg``.
"""

from __future__ import annotations

import statistics
from pathlib import Path

from . import align, cfg, textseg, voice
from .project import Script


MIN_GAP = 2 / cfg.FPS


def _ts(t: float, sep: str = ",") -> str:
    """Format seconds as SRT timestamps without millisecond rollover bugs."""
    total_ms = max(0, int(round(float(t) * 1000.0)))

    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, milliseconds = divmod(rem, 1_000)

    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        f"{sep}{milliseconds:03d}"
    )


def _ass_ts(t: float) -> str:
    """Format seconds as ASS timestamps (H:MM:SS.cc)."""
    total_cs = max(0, int(round(float(t) * 100.0)))

    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    seconds, centiseconds = divmod(rem, 100)

    return (
        f"{hours:d}:{minutes:02d}:"
        f"{seconds:02d}.{centiseconds:02d}"
    )


def _caption_text(words: list[dict]) -> str:
    return " ".join(
        str(word.get("w", "")).strip()
        for word in words
        if str(word.get("w", "")).strip()
    )


def _fits(
    words: list[dict],
    max_line: int,
    max_lines: int,
) -> bool:
    """Return whether words fit within the configured caption geometry."""
    text = _caption_text(words)
    if not text:
        return True

    lines = textseg.caption_lines(
        text,
        max_line,
        max_lines,
    )
    # caption_lines() returns a list of CARDS, each already capped at
    # `max_lines` lines -- fitting in a single card means exactly one such
    # group is needed, not `<= max_lines` groups (which would let up to
    # max_lines**2 lines of text into what should be one caption card).
    return len(lines) <= 1


def _cards(
    words: list[dict],
    max_line: int,
    max_lines: int,
) -> list[list[dict]]:
    """Pack aligned words into readable caption cards.

    The longest geometrically valid card is preferred.  When several recent
    break points are possible, a genuine pause can override the longest-card
    preference because it is a more natural speech boundary.
    """
    if not words:
        return []

    gaps = [
        max(
            0.0,
            float(b.get("s", 0.0))
            - float(a.get("e", 0.0)),
        )
        for a, b in zip(words, words[1:])
    ]

    # Median over ALL gaps, not just positive ones: when a single real pause
    # dominates an otherwise back-to-back stream, filtering to positive-only
    # gaps made that one pause its own baseline (median of a 1-element list
    # equals itself), so it could never clear a "1.5x typical" threshold
    # relative to itself. Including the zeros keeps the baseline near zero
    # in that case, letting a genuine outlier pause register as one.
    typical = statistics.median(gaps) if gaps else 0.0

    cards: list[list[dict]] = []
    start = 0

    while start < len(words):
        end = start + 1

        # Find the largest group that fits.
        while (
            end < len(words)
            and _fits(
                words[start:end + 1],
                max_line,
                max_lines,
            )
        ):
            end += 1

        # ``end`` is exclusive here.  Candidate boundaries are therefore
        # start+1 .. end, with the latter meaning the full feasible run.
        if end < len(words):
            lo = max(
                start + 1,
                end - 4,
            )
            candidates = range(
                lo,
                end + 1,
            )

            best = max(
                candidates,
                key=lambda boundary: (
                    gaps[boundary - 1]
                    if 0 <= boundary - 1 < len(gaps)
                    else 0.0
                ),
            )

            pause = (
                gaps[best - 1]
                if 0 <= best - 1 < len(gaps)
                else 0.0
            )

            candidate_dur = (
                float(words[best - 1].get("e", 0.0))
                - float(words[start].get("s", 0.0))
            )

            if (
                pause > 0.0
                and pause > max(typical * 1.5, 0.12)
                and candidate_dur >= float(cfg.CAPTION_MIN_S)
            ):
                end = best

            # If remaining tail words would be a tiny orphan group (<=3 words), balance the split
            if (len(words) - end) <= 3:
                mid = start + (len(words) - start) // 2
                if mid > start and _fits(words[start:mid], max_line, max_lines) and _fits(words[mid:], max_line, max_lines):
                    end = mid

        group = words[start:end]

        # Defensive fallback: if a single word itself exceeds the configured
        # line width, still emit it rather than getting stuck.
        cards.append(group)
        start = end

    # Merge trailing orphan micro-cards if they fit into the previous card
    if len(cards) >= 2:
        last_group = cards[-1]
        prev_group = cards[-2]
        merged = prev_group + last_group
        dur = float(last_group[-1].get("e", 0.0)) - float(last_group[0].get("s", 0.0))
        if dur < float(cfg.CAPTION_MIN_S) and _fits(merged, max_line, max_lines):
            cards[-2] = merged
            cards.pop()

    return cards


def _constrain(cards: list[dict]) -> list[dict]:
    """Apply readable subtitle timing constraints without crossing cards."""
    if not cards:
        return []

    normalized: list[dict] = []

    for card in cards:
        start = max(
            0.0,
            float(card["start"]),
        )
        end = max(
            start,
            float(card["end"]),
        )

        text = str(
            card.get("text", "")
        ).replace("\n", " ")

        chars = len(text)
        desired = max(
            float(cfg.CAPTION_MIN_S),
            chars / float(cfg.CAPTION_CPS),
        )

        # Never make an individual caption longer than the configured maximum.
        desired = min(
            desired,
            float(cfg.CAPTION_MAX_S),
        )

        end = max(
            end,
            start + desired,
        )

        # `desired` only ever pulls a too-short card up to the maximum; a
        # card whose given `end` already exceeds the maximum (e.g. an
        # outlier alignment timestamp) was never actually pulled back down
        # by the max() above. Clamp explicitly.
        end = min(
            end,
            start + float(cfg.CAPTION_MAX_S),
        )

        normalized.append(
            {
                **card,
                "start": start,
                "end": end,
            }
        )

    # Resolve overlaps from left to right. Prefer preserving the natural
    # aligned start of the next card over allowing captions to overlap.
    for index in range(len(normalized) - 1):
        current = normalized[index]
        following = normalized[index + 1]

        latest_end = (
            following["start"] - MIN_GAP
        )

        if current["end"] > latest_end:
            available = latest_end - current["start"]

            if available >= 0.2:
                current["end"] = min(
                    current["end"],
                    latest_end,
                )
            else:
                # The card is too close to the next one to satisfy both the
                # readability minimum and the gap. Keep the temporal ordering
                # invariant rather than creating overlapping captions.
                current["end"] = max(
                    current["start"] + 0.01,
                    latest_end,
                )

    # Final normalization guarantees SRT/ASS never receives inverted times.
    for card in normalized:
        card["start"] = max(
            0.0,
            float(card["start"]),
        )
        card["end"] = max(
            card["start"] + 0.01,
            float(card["end"]),
        )

    return normalized


def _section_offset(
    amap: dict,
    script: Script,
    stem: str,
) -> float:
    """Calculate section start from exact master-audio sample offsets."""
    sample_rate = int(
        amap["sample_rate"]
    )

    if sample_rate <= 0:
        raise ValueError(
            f"invalid master sample rate: {sample_rate}"
        )

    sections = amap["sections"]

    total_samples = 0

    for section in script.sections:
        if section.stem == stem:
            break

        info = sections.get(section.stem)
        if info is None:
            raise KeyError(
                f"missing audio-map entry for "
                f"section {section.stem}"
            )

        total_samples += int(
            info["samples"]
        )
    else:
        raise KeyError(
            f"missing audio-map entry for section {stem}"
        )

    return total_samples / sample_rate


def cards_for(
    proj: Path,
    script: Script,
) -> list[dict]:
    """Return every caption card on the exact master-audio clock."""
    amap = voice.audio_map(proj)

    sample_rate = int(
        amap.get("sample_rate", 0)
    )

    if sample_rate <= 0:
        raise ValueError(
            "audio_map contains an invalid sample_rate"
        )

    sections = amap.get("sections", {})
    output: list[dict] = []

    for sec in script.sections:
        if sec.stem not in sections:
            raise KeyError(
                f"audio_map.json has no section "
                f"{sec.stem}"
            )

        offset = _section_offset(
            amap,
            script,
            sec.stem,
        )

        data = align.load(
            proj,
            sec.stem,
        )

        for sentence in data.get(
            "sentences",
            [],
        ):
            sentence_text = str(
                sentence.get("text", "")
            ).strip()

            words = [
                word
                for word in (
                    sentence.get("words")
                    or []
                )
                if (
                    "w" in word
                    and "s" in word
                    and "e" in word
                )
            ]

            if not words:
                if not sentence_text:
                    continue

                start = offset + max(
                    0.0,
                    float(
                        sentence.get(
                            "start",
                            0.0,
                        )
                    ),
                )

                end = offset + max(
                    float(
                        sentence.get(
                            "start",
                            0.0,
                        )
                    ),
                    float(
                        sentence.get(
                            "end",
                            sentence.get(
                                "start",
                                0.0,
                            ),
                        )
                    ),
                )

                # The old implementation attempted to call caption_lines()
                # with its default configuration and then joined each result.
                # Explicitly use the configured geometry here.
                line_groups = textseg.caption_lines(
                    sentence_text,
                    cfg.CAPTION_LINE,
                    cfg.CAPTION_LINES,
                )

                if not line_groups:
                    continue

                # Without word timestamps there is no principled way to assign
                # sub-sentence timing. Keep the sentence timing intact and use
                # multiple visual lines within one card.
                output.append(
                    {
                        "start": start,
                        "end": end,
                        "text": "\n".join(
                            textseg.caption_text(group)
                            for group in line_groups
                        ),
                        "words": [],
                    }
                )
                continue

            # Normalize word timestamps before packing.
            normalized_words: list[dict] = []
            previous_end = 0.0

            for word in words:
                start = max(
                    previous_end,
                    float(word["s"]),
                )
                end = max(
                    start,
                    float(word["e"]),
                )

                normalized_words.append(
                    {
                        "w": str(
                            word["w"]
                        ).strip(),
                        "s": start,
                        "e": end,
                    }
                )

                previous_end = end

            for group in _cards(
                normalized_words,
                cfg.CAPTION_LINE,
                cfg.CAPTION_LINES,
            ):
                if not group:
                    continue

                text = _caption_text(
                    group
                )

                if not text:
                    continue

                lines = textseg.caption_lines(
                    text,
                    cfg.CAPTION_LINE,
                    cfg.CAPTION_LINES,
                )

                output.append(
                    {
                        "start": (
                            offset
                            + float(group[0]["s"])
                        ),
                        "end": (
                            offset
                            + float(group[-1]["e"])
                        ),
                        "text": (
                            "\n".join(
                                textseg.caption_text(group)
                                for group in lines
                            )
                            if lines
                            else text
                        ),
                        "words": [
                            {
                                "w": word["w"],
                                "s": (
                                    offset
                                    + float(word["s"])
                                ),
                                "e": (
                                    offset
                                    + float(word["e"])
                                ),
                            }
                            for word in group
                        ],
                    }
                )

    output.sort(
        key=lambda card: (
            card["start"],
            card["end"],
        )
    )

    return _constrain(output)


def write_srt(
    proj: Path,
    script: Script,
    dst: Path,
) -> Path:
    """Write alignment-timed SRT captions."""
    cards = cards_for(
        proj,
        script,
    )

    lines: list[str] = []

    for number, card in enumerate(
        cards,
        start=1,
    ):
        lines.extend(
            [
                str(number),
                (
                    f"{_ts(card['start'])} --> "
                    f"{_ts(card['end'])}"
                ),
                card["text"],
                "",
            ]
        )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = dst.with_name(
        dst.name + ".tmp"
    )

    tmp.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    tmp.replace(
        dst
    )

    return dst


_ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: prompt2render,{font},54,&H00FFFFFF,&H0000C8FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,2,80,80,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_escape(text: str) -> str:
    """Escape text for ASS while preserving explicit line breaks."""
    return (
        str(text)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", r"\N")
    )


def write_ass(
    proj: Path,
    script: Script,
    dst: Path,
) -> Path:
    """Write optional word-level ASS karaoke captions."""
    body = [
        _ASS_HEAD.format(
            w=cfg.WIDTH,
            h=cfg.HEIGHT,
            font=cfg.CAPTION_FONT,
        )
    ]

    for card in cards_for(
        proj,
        script,
    ):
        if card["words"]:
            parts: list[str] = []
            cursor = float(
                card["start"]
            )

            for word in card["words"]:
                word_start = float(
                    word["s"]
                )
                word_end = float(
                    word["e"]
                )

                lead = max(
                    0,
                    int(
                        round(
                            (
                                word_start
                                - cursor
                            )
                            * 100
                        )
                    ),
                )

                if lead:
                    parts.append(
                        f"{{\\k{lead}}}"
                    )

                duration = max(
                    1,
                    int(
                        round(
                            (
                                word_end
                                - word_start
                            )
                            * 100
                        )
                    ),
                )

                # \\kf produces progressive karaoke highlighting.
                parts.append(
                    f"{{\\kf{duration}}}"
                    f"{_ass_escape(word['w'])} "
                )

                cursor = word_end

            text = "".join(parts).strip()
        else:
            text = _ass_escape(
                card["text"]
            )

        body.append(
            "Dialogue: 0,"
            f"{_ass_ts(card['start'])},"
            f"{_ass_ts(card['end'])},"
            f"prompt2render,,0,0,0,,{text}"
        )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = dst.with_name(
        dst.name + ".tmp"
    )

    tmp.write_text(
        "\n".join(body) + "\n",
        encoding="utf-8",
    )

    tmp.replace(
        dst
    )

    return dst


__all__ = [
    "MIN_GAP",
    "cards_for",
    "write_ass",
    "write_srt",
]