"""Sentence, word and caption segmentation — one implementation, used by all.

Before this module there were three disagreeing splitters: kokoro's phoneme
batcher (which splits on spaces at a 510-token ceiling, mid-clause, and trims
each batch), edge-tts's internal sentence logic, and assemble._split_caption.
Sync is only ever as good as its weakest segmentation, so voice, alignment and
captions now all count sentences and words the same way.

The `norm` form is the load-bearing piece. Alignment compares the script we
know was spoken against what an ASR heard, token by token; every place the two
spell a thing differently is an anchor lost. "1,000,000" must become "one
million" here because that is what whisper will emit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------- sentences --

#: Abbreviations whose trailing dot never ends a sentence. Kept lowercase and
#: matched case-insensitively.
_ABBREV = {
    "e.g", "i.e", "etc", "vs", "cf", "al", "approx", "est", "fig", "eq", "ref",
    "no", "vol", "ch", "sec", "pp", "min", "max", "avg", "std",
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "mt",
    "inc", "ltd", "co", "corp", "dept", "univ",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "mon", "tue", "wed", "thu", "fri", "sat", "sun",
}

_DOT = "\x00"          # stands in for a dot that must not end a sentence

_ABBREV_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(a) for a in _ABBREV), key=len, reverse=True))
    + r")\.", re.I)
_INITIAL_RE = re.compile(r"\b([A-Z])\.")                 # "J. von Neumann"
_DECIMAL_RE = re.compile(r"(\d)\.(?=\d)")                # 1.5, 3.11.1
_ELLIPSIS_RE = re.compile(r"\.\.\.")
_SPLIT_RE = re.compile(r"(?<=[.!?])[\"')\]]*\s+")

#: Where a too-long sentence may be broken for the synthesiser. Ordered by how
#: little the break costs: a semicolon is nearly a full stop already, a
#: coordinating conjunction is the last resort.
_CLAUSE_RE = re.compile(
    r"(?<=[;:])\s+"
    r"|\s+[—–-]{1,2}\s+"
    r"|(?<=,)\s+(?=(?:and|but|or|so|yet|which|who|that|because|while|"
    r"although|though|since|unless|whereas|then)\b)",
    re.I)


@dataclass
class Word:
    i: int
    raw: str          # exactly as written, punctuation attached
    norm: str         # ASR-comparison form; may be "" for pure punctuation


@dataclass
class Sentence:
    i: int
    text: str
    para_break_before: bool = False
    #: True when this is the tail of a sentence the synthesiser could not take
    #: whole — it gets a short clause pause instead of a full stop's.
    clause_continuation: bool = False
    words: list[Word] = field(default_factory=list)

    @property
    def ends_question(self) -> bool:
        return self.text.rstrip().endswith(("?", "!"))


def _protect(text: str) -> str:
    text = _ELLIPSIS_RE.sub(_DOT * 3, text)
    text = _ABBREV_RE.sub(lambda m: m.group(1) + _DOT, text)
    text = _INITIAL_RE.sub(lambda m: m.group(1) + _DOT, text)
    text = _DECIMAL_RE.sub(lambda m: m.group(1) + _DOT, text)
    return text


def _restore(text: str) -> str:
    return text.replace(_DOT, ".")


def sentences(narration: str) -> list[Sentence]:
    """Split narration into sentences, preserving paragraph breaks.

    Paragraph breaks survive as a flag rather than as text because the voice
    engine turns them into a longer pause — that is the only thing a blank
    line in script.md has ever meant.
    """
    out: list[Sentence] = []
    paragraphs = re.split(r"\n\s*\n", narration.strip())
    for pi, para in enumerate(paragraphs):
        body = _protect(re.sub(r"\s+", " ", para).strip())
        if not body:
            continue
        for si, piece in enumerate(_SPLIT_RE.split(body)):
            piece = _restore(piece).strip()
            if not piece:
                continue
            out.append(Sentence(
                i=len(out),
                text=piece,
                para_break_before=(pi > 0 and si == 0),
            ))
    for s in out:
        s.words = words(s.text)
    return out


def split_clauses(text: str) -> list[str]:
    """Break one sentence at its least costly seams. May return [text]."""
    parts = [p.strip() for p in _CLAUSE_RE.split(_protect(text)) if p and p.strip()]
    return [_restore(p) for p in parts] or [text]


def fit_to_synthesiser(sent: Sentence, measure, limit: int) -> list[Sentence]:
    """Break `sent` until every piece fits the synthesiser's context window.

    kokoro truncates anything past 510 phonemes with nothing but a log line,
    and its own batching splits on spaces — landing mid-clause and trimming
    the silence at each seam. That is exactly why one-shot synthesis sounds
    oddly paced. We break at clause boundaries instead, and the caller inserts
    a short pause at each seam.

    `measure` is a callable str -> int (phoneme count), injected so this
    module never imports the synthesiser.
    """
    if measure(sent.text) <= limit:
        return [sent]

    pieces, queue = [], split_clauses(sent.text)
    if len(queue) == 1:
        # Nothing to break on. Fall back to word groups rather than let the
        # synthesiser silently drop the tail.
        queue = _greedy_word_groups(sent.text, measure, limit)

    for j, piece in enumerate(queue):
        if measure(piece) > limit:
            pieces.extend(_greedy_word_groups(piece, measure, limit))
        else:
            pieces.append(piece)

    return [Sentence(i=sent.i, text=p,
                     para_break_before=(k == 0 and sent.para_break_before),
                     clause_continuation=(k > 0),
                     words=words(p))
            for k, p in enumerate(pieces)]


def _greedy_word_groups(text: str, measure, limit: int) -> list[str]:
    groups, buf = [], []
    for w in text.split():
        trial = " ".join(buf + [w])
        if buf and measure(trial) > limit:
            groups.append(" ".join(buf))
            buf = [w]
        else:
            buf.append(w)
    if buf:
        groups.append(" ".join(buf))
    return groups or [text]


# ------------------------------------------------------------------- words --

_WORD_RE = re.compile(r"[^\s]+")


def words(text: str) -> list[Word]:
    return [Word(i=i, raw=m.group(0), norm=normalise_token(m.group(0)))
            for i, m in enumerate(_WORD_RE.finditer(text))]


def norm_tokens(text: str) -> list[str]:
    """Flat list of ASR-comparison tokens. One raw word may yield several."""
    out: list[str] = []
    for w in words(text):
        out.extend(w.norm.split())
    return out


# --------------------------------------------------------- normalisation ----

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]
_SCALE = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]

_SYMBOLS = {
    "%": " percent ", "&": " and ", "+": " plus ", "=": " equals ",
    "<": " less than ", ">": " greater than ", "/": " slash ",
    "*": " times ", "^": " to the power ", "@": " at ", "#": " number ",
    "→": " to ", "≤": " less than or equal ", "≥": " greater than or equal ",
    "≠": " not equal ", "×": " times ", "÷": " divided by ",
}

#: Spelled out the way an ASR transcribes them, which is not always the way
#: they are written. Extend this table when alignment confidence drops.
_LEXICON = {
    "o(log": "oh log", "o(n": "oh n", "o(1)": "oh one",
    "ok": "okay", "vs": "versus", "etc": "etcetera",
    "e.g": "for example", "i.e": "that is",
    "dr": "doctor", "mr": "mister", "mrs": "missus", "prof": "professor",
    "lufs": "l u f s", "srt": "s r t", "api": "a p i", "cpu": "c p u",
    "gpu": "g p u", "ram": "ram", "url": "u r l", "html": "h t m l",
    "ffmpeg": "f f m peg", "tts": "t t s", "asr": "a s r",
}

_ORDINAL_RE = re.compile(r"^(\d+)(st|nd|rd|th)$")
_PLURAL_NUM_RE = re.compile(r"^(\d+)'?s$")
# Only tokens that are wholly numeric (optionally ordinal/plural/decimal)
# may enter _number_to_words(). Mixed algorithm notation such as n-1, O(n),
# 2D, 1-based, and v2 must remain ordinary comparison tokens.
_NUMERIC_TOKEN_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:st|nd|rd|th|'?s)?$")


def _int_to_words(n: int) -> str:
    if n < 0:
        return "minus " + _int_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, r = divmod(n, 10)
        return _TENS[t] + (" " + _ONES[r] if r else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return _ONES[h] + " hundred" + (" " + _int_to_words(r) if r else "")
    for value, name in _SCALE:
        if n >= value:
            q, r = divmod(n, value)
            return _int_to_words(q) + " " + name + (" " + _int_to_words(r) if r else "")
    # Beyond a billion nobody narrates the digits; read them out singly.
    return " ".join(_ONES[int(d)] for d in str(n))


def _number_to_words(tok: str) -> str:
    """Expand a numeric token the way it would actually be said."""
    neg = tok.startswith("-")
    tok = tok.lstrip("+-").replace(",", "")

    if m := _ORDINAL_RE.match(tok):
        n = int(m.group(1))
        base = _int_to_words(n).split()
        last = {"one": "first", "two": "second", "three": "third",
                "five": "fifth", "eight": "eighth", "nine": "ninth",
                "twelve": "twelfth"}.get(base[-1])
        if last is None:
            last = base[-1][:-1] + "ieth" if base[-1].endswith("y") else base[-1] + "th"
        out = " ".join(base[:-1] + [last])
    elif m := _PLURAL_NUM_RE.match(tok):
        out = _int_to_words(int(m.group(1)))
        out = out[:-1] + "ies" if out.endswith("y") else out + "s"
    elif "." in tok:
        whole, _, frac = tok.partition(".")
        out = _int_to_words(int(whole or 0)) + " point " + \
            " ".join(_ONES[int(d)] for d in frac if d.isdigit())
    elif tok.isdigit():
        # A four-digit number in running text is nearly always a year, and a
        # year is said as two pairs: "nineteen ninety nine", not "one thousand".
        n = int(tok)
        if len(tok) == 4 and 1100 <= n <= 2099 and n % 100 != 0:
            out = _int_to_words(n // 100) + " " + (
                "oh " + _ONES[n % 100] if n % 100 < 10 else _int_to_words(n % 100))
        else:
            out = _int_to_words(n)
    else:
        return tok

    return ("minus " + out) if neg else out


def normalise_token(tok: str) -> str:
    """The ASR-comparison form of one whitespace-delimited token.

    Lowercased, symbols and numerals spelled out, punctuation dropped. May
    return several space-separated words, or "" for pure punctuation.
    """
    t = tok.strip().lower()
    if not t:
        return ""

    stripped = t.strip(".,;:!?()[]{}\"'")
    if (hit := _LEXICON.get(stripped)) is not None:
        return hit

    # Handle known mathematical prefixes before punctuation normalization.
    for prefix, expansion in _LEXICON.items():
        if "(" in prefix and stripped.startswith(prefix):
            remainder = stripped[len(prefix):]
            return expansion + (" " + normalise_token(remainder) if remainder else "")

    # Collapse digit grouping *before* punctuation stripping, or "1,000,000"
    # becomes three separate tokens and reads as "one zero zero".
    # Remove grouping commas from integers such as 1,000 and 1,000,000.
    t = re.sub(r"(?<=\d),(?=\d{3}(?:,\d{3})*(?:\D|$))", "", t)

    for sym, rep in _SYMBOLS.items():
        t = t.replace(sym, rep)

    # Keep the digits, the letters, and the dot/apostrophe that carry meaning
    # inside a token (1.5, 2's); everything else is punctuation.
    t = re.sub(r"[^\w\s.'’-]", " ", t)
    t = t.replace("’", "'")

    out: list[str] = []
    for piece in t.split():
        # A leading minus in front of a digit is a sign, not a hyphen — strip
        # it and it silently becomes a positive number.
        neg = bool(re.match(r"^-\d", piece))
        piece = piece.strip(".-")
        if not piece:
            continue
        if neg:
            piece = "-" + piece
        if _NUMERIC_TOKEN_RE.fullmatch(piece):
            out.append(_number_to_words(piece))
        elif piece.isalpha() and len(piece) <= 5 and tok.isupper() and len(tok) > 1:
            # An all-caps token is an initialism; ASR spells it letter by
            # letter far more often than it says it as a word.
            out.append(" ".join(piece))
        else:
            out.append(piece.replace("'", ""))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


# ------------------------------------------------------------- syllables ----

_VOWELS = "aeiouy"


def syllables(word: str) -> int:
    """Rough syllable count, used to weight time between alignment anchors.

    Interpolating on character count makes "through" and "a" equally long,
    which they emphatically are not. This is crude but it is the right shape,
    and it only ever applies to tokens the ASR failed to match.
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    count, prev_vowel = 0, False
    for ch in w:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and count > 1:
        count -= 1
    return max(count, 1)


# -------------------------------------------------------------- captions ----

def caption_lines(text: str, max_line: int | None = None,
                  max_lines: int = 2) -> list[list[str]]:
    """Wrap text into caption cards of at most `max_lines` lines.

    The old splitter allowed 84 characters on a single line, roughly double
    the broadcast norm; two lines of 42 is what subtitles have settled on
    because it is what the eye takes in during one glance.
    """
    from . import cfg
    max_line = max_line or cfg.CAPTION_LINE

    tokens = re.sub(r"\s+", " ", text).strip().split()
    if not tokens:
        return []

    lines: list[str] = []
    buf = ""
    for tok in tokens:
        while len(tok) > max_line:                 # a URL or a long identifier
            if buf:
                lines.append(buf)
                buf = ""
            lines.append(tok[:max_line])
            tok = tok[max_line:]
        if not buf:
            buf = tok
        elif len(buf) + 1 + len(tok) <= max_line:
            buf = f"{buf} {tok}"
        else:
            lines.append(buf)
            buf = tok
    if buf:
        lines.append(buf)

    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]


def caption_text(card: list[str]) -> str:
    return "\n".join(card)