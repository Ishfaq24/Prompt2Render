"""Forced alignment: when was each word actually spoken?

ffmpeg 8.x is built `--enable-whisper`, so whisper.cpp is available as an
audio filter and alignment costs no Python dependency at all.

The rule that governs everything here: **the ASR contributes timings only.**
Every character of caption text comes from script.md — we already know exactly
what was said, so this is alignment, not transcription, and a whisper word
error can never reach the output. What the ASR hears is matched against the
known script with a sequence diff; matched tokens become time anchors and
everything between them is interpolated.

Two hardening passes make the result trustworthy:

* **Snap to silence.** whisper's token timestamps are estimates (ffmpeg
  exposes no DTW option), but the pauses the voice engine *inserted* are
  ground truth, so a boundary near a detected silence edge snaps to it.
* **Clamp to the prior.** On the kokoro path sentence boundaries are already
  sample-exact, so those win outright and whisper is used only for word-level
  detail inside a sentence. That makes the ASR strictly additive: it can never
  make the result worse than synthesis alone.

**No VAD gate in the whisper filter.** ffmpeg's built-in `vad_model=` option
was tried and measured: on this build it drives whisper's wall time up by
roughly 12x with audio length (a 30 s slice went 16.8 s -> 200.4 s), because
the wrapper doesn't scale with duration the way whisper.cpp itself does. It
existed to stop whisper hallucinating words into the pauses the voice engine
inserts, but that fear is already handled one layer up: a hallucinated token
simply fails to match anything in the known script and difflib drops it as an
unmatched insert, so it never becomes an anchor. Measured on a real project
(bubble-sort, 6 sections): per-section reconciliation confidence with VAD on
was 0.879-0.969; with VAD off on the identical audio, 0.881-0.975 — no
regression, and every timestamp invariant still held. See docs/OPTIMIZATION.md
EXP-01.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import asrmodel, cfg, textseg, voice
from .project import Script

VERSION = 2
MIN_WORD = 0.040               # a word shorter than this is a timing artefact
SNAP_WINDOW = 0.250            # snap a boundary to a silence edge within this
CONF_GOOD = 0.85
CONF_FLOOR = 0.60              # below this, discard the ASR entirely

TS = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)\s*-->\s*"
                r"(\d\d):(\d\d):(\d\d)[,.](\d\d\d)")


# ------------------------------------------------------------- srt parse ---

def parse_srt(path: Path) -> list[dict]:
    """Parse by blank-line-separated blocks.

    Scanning line by line and treating everything after a timestamp as text
    swallows the *next* block's index number, which then rides along on the
    end of the caption. Blocks are unambiguous.
    """
    cues: list[dict] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines:
            continue
        m = TS.search(lines[0])
        if not m:
            continue
        g = m.groups()
        body = " ".join(lines[1:]).strip()
        if body:
            cues.append({"start": _secs(*g[:4]), "end": _secs(*g[4:]),
                         "text": body})

    for i in range(1, len(cues)):
        if cues[i]["start"] < cues[i - 1]["end"]:
            mid = (cues[i]["start"] + cues[i - 1]["end"]) / 2
            cues[i - 1]["end"] = cues[i]["start"] = mid
    return cues


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ----------------------------------------------------------------- asr -----

def _slice(master: Path, start: float, dur: float, dst: Path) -> None:
    cfg.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.6f}",
             "-t", f"{dur:.6f}", "-i", str(master),
             "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


def transcribe(wav: Path, model: Path, workdir: Path) -> list[dict]:
    """Word-level cues from the ffmpeg whisper filter, or [] on failure."""
    out = workdir / "words.srt"
    out.unlink(missing_ok=True)

    opts = [
        f"model={cfg.filter_path(model)}",
        "language=en",
        # The 3 s default starves whisper of context and corrupts every
        # chunk edge; 20 s costs memory and nothing else.
        "queue=20",
        # 2 GB of VRAM on an MX350, and this build advertises no whisper CUDA
        # backend. CPU is both faster and more predictable here.
        "use_gpu=0",
        "format=srt",
        # Enables whisper.cpp token timestamps, which is how you get word
        # granularity out of a filter that does not advertise it.
        "max_len=1",
        f"destination={cfg.filter_path(out)}",
    ]
    # Deliberately no vad_model= here — see the module docstring (EXP-01):
    # ffmpeg's whisper filter's VAD integration costs ~12x wall time for no
    # measured gain in reconciliation confidence, because a hallucinated
    # token just fails to match the known script and gets dropped.

    graph = ("aresample=16000:resampler=soxr,whisper=" + ":".join(opts))
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "warning",
                        "-i", str(wav), "-vn", "-map", "0:a:0",
                        "-af", graph, "-f", "null", "-"])
    if proc.returncode != 0:
        cfg.warn(f"whisper filter failed: {(proc.stderr or '')[-400:]}")
        return []
    if not out.exists() or out.stat().st_size == 0:
        cfg.warn("whisper produced no output — falling back")
        return []
    return parse_srt(out)


def silences(wav: Path, floor_db: int = -45, min_d: float = 0.12) -> list[tuple]:
    """(start, end) of every detected silence. Ground truth for snapping."""
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
                        "-i", str(wav), "-af",
                        f"silencedetect=n={floor_db}dB:d={min_d}",
                        "-f", "null", "-"])
    text = (proc.stderr or "") + (proc.stdout or "")
    starts = [float(m) for m in re.findall(r"silence_start:\s*([-\d.]+)", text)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([-\d.]+)", text)]
    return list(zip(starts, ends))


# -------------------------------------------------------- reconciliation ---

def _asr_tokens(cues: list[dict]) -> list[dict]:
    """Flatten ASR cues to one entry per normalised token."""
    out = []
    for c in cues:
        toks = textseg.norm_tokens(c["text"])
        if not toks:
            continue
        span = max(c["end"] - c["start"], 1e-3) / len(toks)
        for j, t in enumerate(toks):
            out.append({"n": t,
                        "s": c["start"] + j * span,
                        "e": c["start"] + (j + 1) * span})
    return out


def reconcile(sentences: list[textseg.Sentence], asr: list[dict],
              dur: float) -> tuple[list[dict], float]:
    """Map ASR timings onto the known script tokens. Returns (sentences, conf)."""
    # Flatten the ground truth, remembering which sentence each token is in.
    gt, owner = [], []
    for s in sentences:
        for w in s.words:
            for piece in (w.norm.split() or [""]):
                if piece:
                    gt.append(piece)
                    owner.append((s.i, w.raw))
    if not gt:
        return [], 0.0
    if not asr:
        return _spread(sentences, dur), 0.0

    anchors: dict[int, float] = {}
    sm = difflib.SequenceMatcher(None, gt, [a["n"] for a in asr], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            continue
        for k in range(i2 - i1):
            anchors[i1 + k] = asr[j1 + k]["s"]

    conf = len(anchors) / len(gt)
    if conf < CONF_FLOOR:
        # A half-aligned section is worse than an honestly interpolated one:
        # the errors are non-uniform and land in the middle of sentences.
        return _spread(sentences, dur), conf

    times = _interpolate(gt, anchors, dur)
    out, cursor = [], 0
    for s in sentences:
        n = sum(len(w.norm.split()) for w in s.words if w.norm)
        if n == 0:
            continue
        slice_t = times[cursor:cursor + n]
        words = []
        wi = cursor
        for w in s.words:
            pieces = w.norm.split()
            if not pieces:
                continue
            st = times[wi]
            en = times[min(wi + len(pieces), len(times) - 1)]
            words.append({"w": w.raw, "s": round(st, 3),
                          "e": round(max(en, st + MIN_WORD), 3)})
            wi += len(pieces)
        out.append({"i": s.i, "text": s.text,
                    "start": round(slice_t[0], 3),
                    "end": round(max(slice_t[-1] + MIN_WORD, slice_t[0]), 3),
                    "words": words})
        cursor += n
    return out, conf


def _interpolate(gt: list[str], anchors: dict[int, float], dur: float) -> list[float]:
    """Fill unanchored tokens by syllable-weighted position between anchors.

    Interpolating on character count would make "through" and "a" equally
    long, which they emphatically are not.
    """
    n = len(gt)
    weights = [textseg.syllables(t) for t in gt]
    times = [None] * n
    for i, t in anchors.items():
        times[i] = t

    known = sorted(anchors)
    if not known:
        total = sum(weights) or 1
        acc = 0.0
        for i, w in enumerate(weights):
            times[i] = dur * acc / total
            acc += w
        return times

    # Leading run: extrapolate backwards at the local rate.
    rate = _local_rate(known, anchors, weights, dur)
    for i in range(known[0] - 1, -1, -1):
        times[i] = max(0.0, times[i + 1] - weights[i] * rate)

    for a, b in zip(known, known[1:]):
        span = times[b] - times[a]
        wsum = sum(weights[a:b]) or 1
        acc = 0.0
        for i in range(a + 1, b):
            acc += weights[i - 1]
            times[i] = times[a] + span * acc / wsum

    for i in range(known[-1] + 1, n):
        times[i] = min(dur, times[i - 1] + weights[i - 1] * rate)

    # Strict monotonicity, with a floor so two words never share an instant.
    for i in range(1, n):
        if times[i] <= times[i - 1]:
            times[i] = times[i - 1] + MIN_WORD
    return [min(t, dur) for t in times]


def _local_rate(known: list[int], anchors: dict, weights: list[int],
                dur: float) -> float:
    """Seconds per syllable, from the nearest anchors rather than the average."""
    if len(known) < 2:
        return dur / max(sum(weights), 1)
    lo, hi = known[0], known[min(20, len(known) - 1)]
    span = anchors[hi] - anchors[lo]
    syl = sum(weights[lo:hi]) or 1
    return max(span / syl, 0.02)


def _spread(sentences: list[textseg.Sentence], dur: float) -> list[dict]:
    """Last resort: share the section out by syllable weight."""
    weights = [max(sum(textseg.syllables(w.raw) for w in s.words), 1)
               for s in sentences]
    total = sum(weights) or 1
    out, t = [], 0.0
    for s, wt in zip(sentences, weights):
        span = dur * wt / total
        words, wtime = [], t
        for w in s.words:
            wspan = span * textseg.syllables(w.raw) / wt
            words.append({"w": w.raw, "s": round(wtime, 3),
                          "e": round(wtime + wspan, 3)})
            wtime += wspan
        out.append({"i": s.i, "text": s.text, "start": round(t, 3),
                    "end": round(t + span, 3), "words": words})
        t += span
    return out


# ------------------------------------------------------------ hardening ----

def snap(sents: list[dict], gaps: list[tuple]) -> int:
    """Pull sentence boundaries onto real silence edges. Returns count moved."""
    if not gaps:
        return 0
    moved = 0
    for s in sents:
        best = min(((abs(s["start"] - end), end) for _, end in gaps),
                   default=(9e9, 0.0))
        if best[0] <= SNAP_WINDOW:
            s["start"] = round(best[1], 3)
            if s["words"]:
                s["words"][0]["s"] = s["start"]
            moved += 1
    for a, b in zip(sents, sents[1:]):
        if a["end"] > b["start"]:
            a["end"] = b["start"]
    return moved


def clamp_to_prior(sents: list[dict], prior: list[voice.Cue]) -> list[dict]:
    """Sentence boundaries come from synthesis; the ASR only refines inside.

    This is what makes the ASR strictly additive. Synthesis knows to the
    sample when it started and stopped speaking each sentence; whisper is
    estimating. Where they disagree about a boundary, synthesis is right.
    """
    if not prior or len(prior) != len(sents):
        return sents
    for s, p in zip(sents, prior):
        lo, hi = p.start, p.end
        s["start"], s["end"] = round(lo, 3), round(hi, 3)
        for w in s["words"]:
            w["s"] = round(min(max(w["s"], lo), hi), 3)
            w["e"] = round(min(max(w["e"], w["s"] + MIN_WORD), hi), 3)
        if s["words"]:
            s["words"][0]["s"] = round(lo, 3)
            s["words"][-1]["e"] = round(hi, 3)
            for a, b in zip(s["words"], s["words"][1:]):
                if b["s"] < a["s"]:
                    b["s"] = a["s"]
    return sents


# --------------------------------------------------------------- driver ----

def path_for(proj: Path, stem: str) -> Path:
    return proj / "build" / "align" / f"{stem}.json"


def _section_sig(narration: str, start: float, dur: float, master_stamp: int) -> str:
    """Fingerprint of everything that can make a cached alignment wrong.

    The "already aligned, skipping" check below used to trust the file's
    mere existence, so editing a section's narration in script.md and
    re-running `align` without --force silently kept the old timing against
    the new text. narration text and the section's placement/duration catch
    a script edit; master.wav's mtime (not a full content hash -- that would
    mean re-reading the whole programme on every untouched run) catches a
    re-synthesis. A false cache miss just costs a recompute; a false hit
    ships wrong captions.
    """
    raw = f"{narration}|{start:.6f}|{dur:.6f}|{master_stamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load(proj: Path, stem: str) -> dict:
    """Read an alignment, lifting the old bare-list format to v2."""
    p = path_for(proj, stem)
    if not p.exists():
        sys.exit(f"[prompt2render] no alignment for section {stem} — run `prompt2render align`")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"version": 1, "source": "synth", "confidence": 0.0,
                "sentences": [{"i": i, "text": c["text"], "start": c["start"],
                               "end": c["end"], "words": []}
                              for i, c in enumerate(data)]}
    return data


def _window(cues: list[dict], start: float, dur: float) -> list[dict]:
    """Cues falling inside a section, rebased to section-relative time."""
    out = []
    for c in cues:
        if c["e"] <= start or c["s"] >= start + dur:
            continue
        out.append({"n": c["n"],
                    "s": min(max(c["s"] - start, 0.0), dur),
                    "e": min(max(c["e"] - start, 0.0), dur)})
    return out


def _digest(path: Path) -> str:
    """Content hash, read in blocks.

    `read_bytes()` on the master pulls the whole programme into memory to
    throw it away one line later — around 57 MB for a ten-minute narration,
    and it grows with the video. The hash is identical either way.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _chunk_spans(proj: Path, groups: int) -> list[tuple[float, float]]:
    """Split the programme into `groups` spans that fall on section joins.

    Section joins are the one place in the programme where a cut is safe by
    construction: prompt2render/voice.py inserts a paragraph pause there, so the audio
    is silent across the boundary and no word can straddle it. Cutting
    anywhere else would hand whisper half a word.
    """
    try:
        amap = voice.audio_map(proj)
    except SystemExit:
        return []
    secs = sorted(amap["sections"].values(), key=lambda o: o["start"])
    if len(secs) < 2:
        return []
    groups = max(1, min(groups, len(secs)))
    per = -(-len(secs) // groups)                 # ceil
    spans = []
    for i in range(0, len(secs), per):
        block = secs[i:i + per]
        start = block[0]["start"]
        end = block[-1]["start"] + block[-1]["dur"]
        spans.append((start, end - start))
    return spans


def _transcribe_chunked(master: Path, model: Path, spans: list[tuple],
                        jobs: int) -> list[dict]:
    """Transcribe several spans at once, rebased onto programme time."""
    def one(idx_span):
        i, (start, dur) = idx_span
        with tempfile.TemporaryDirectory(prefix=f"prompt2render-asr{i}-") as td:
            part = Path(td) / "part.wav"
            _slice(master, start, dur, part)
            cues = transcribe(part, model, Path(td))
        return [{**c, "start": c["start"] + start, "end": c["end"] + start}
                for c in cues]

    parts = cfg.parallel(one, list(enumerate(spans)), jobs, "asr")
    out: list[dict] = []
    for p in parts:
        out.extend(p)
    out.sort(key=lambda c: c["start"])
    return out


def transcribe_programme(proj: Path, master: Path, model: Path,
                         force: bool = False, jobs: int = 1) -> list[dict]:
    """Transcribe the whole master once and cache it.

    One pass rather than one per section: the 148 MB model is loaded once
    instead of five times, and whisper gets unbroken context across section
    boundaries, which is where a per-section pass has the least to go on.

    `jobs > 1` trades that unbroken context for wall-clock. The whisper filter
    is single-threaded from ffmpeg's point of view and this is by some margin
    the slowest local step in a build, so on a machine with cores to spare the
    trade is usually worth taking — but it is opt-in, because it can move a
    word timing by a few milliseconds where a chunk edge starves whisper of
    context, and everything downstream is timed off these numbers. The cache
    key includes the job count so switching back and forth never serves a
    transcript produced the other way.
    """
    cache = proj / "build" / "align" / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    suffix = "" if jobs <= 1 else f"_x{jobs}"
    stamp = cache / f"{_digest(master)}_{model.stem}{suffix}.srt"

    if stamp.exists() and stamp.stat().st_size and not force:
        cfg.say(f"using cached transcript ({stamp.name})")
        return _asr_tokens(parse_srt(stamp))

    spans = _chunk_spans(proj, jobs) if jobs > 1 else []
    if spans:
        cfg.say(f"transcribing {cfg.duration(master)/60:.1f} min with "
                f"{model.name} in {len(spans)} parallel chunks — cached after "
                "the first run")
        cues = _transcribe_chunked(master, model, spans, jobs)
        if not cues:
            return []
        stamp.write_text(_to_srt(cues), encoding="utf-8")
        return _asr_tokens(cues)

    cfg.say(f"transcribing {cfg.duration(master)/60:.1f} min with "
            f"{model.name} — this is the slow step, and it is cached")
    with tempfile.TemporaryDirectory(prefix="prompt2render-asr-") as td:
        cues = transcribe(master, model, Path(td))
        if not cues:
            return []
        src = Path(td) / "words.srt"
        if src.exists():
            stamp.write_bytes(src.read_bytes())
    return _asr_tokens(cues)


def _stamp_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _to_srt(cues: list[dict]) -> str:
    """Serialise merged chunks so the cache round-trips through parse_srt."""
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_stamp_srt(c['start'])} --> {_stamp_srt(c['end'])}\n"
                   f"{c['text']}\n")
    return "\n".join(out)


def align(proj: Path, script: Script, only: str | None = None,
          force: bool = False, use_asr: bool = True,
          asr_jobs: int | None = None) -> None:
    cfg.need("ffmpeg", "ffprobe")
    adir = proj / "build" / "align"
    adir.mkdir(parents=True, exist_ok=True)
    amap = voice.audio_map(proj)
    master = proj / "build" / "master.wav"
    if not master.exists():
        sys.exit("[prompt2render] no build/master.wav — run `prompt2render voice` first")

    model = asrmodel.available() if use_asr else None
    if use_asr and model is None:
        # Deliberately not fatal: ranks 1-2 of the chain are already exact.
        cfg.warn(asrmodel.missing_note())

    # Silence detection reads the same file the transcription does but needs
    # nothing from it, so it runs alongside rather than after — it is free
    # against a whisper pass that takes minutes. Its result is discarded if
    # the ASR produced nothing, exactly as when it was computed afterwards.
    jobs = asr_jobs or cfg.env_int("P2R_ASR_JOBS", 1)
    if model:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_gaps = pool.submit(silences, master)
            tokens = transcribe_programme(proj, master, model, jobs=jobs)
            gaps = f_gaps.result() if tokens else []
    else:
        tokens, gaps = [], []

    master_stamp = master.stat().st_mtime_ns
    for sec in script.sections:
        if only and sec.stem != only:
            continue
        dst = path_for(proj, sec.stem)
        info = amap["sections"][sec.stem]
        start, dur = info["start"], info["dur"]
        sig = _section_sig(sec.narration, start, dur, master_stamp)
        if dst.exists() and not force:
            try:
                cached_sig = json.loads(dst.read_text(encoding="utf-8")).get("sig")
            except (OSError, ValueError):
                cached_sig = None
            if cached_sig == sig:
                cfg.say(f"section {sec.stem}: already aligned, skipping")
                continue
            cfg.say(f"section {sec.stem}: narration or audio changed since "
                    "last align, redoing")

        sents = textseg.sentences(sec.narration)
        prior = voice.section_cues(proj, sec.stem)
        asr = _window(tokens, start, dur)

        aligned, conf = reconcile(sents, asr, dur)
        local_gaps = [(a - start, b - start) for a, b in gaps
                      if b > start and a < start + dur]
        moved = snap(aligned, local_gaps) if asr else 0
        if prior:
            aligned = clamp_to_prior(aligned, prior)

        source = _source(prior, asr, conf)
        dst.write_text(json.dumps({
            "version": VERSION, "sig": sig, "source": source,
            "confidence": round(conf, 3),
            "audio_dur": round(dur, 3),
            "model": model.name if model else "",
            "asr_tokens": len(asr),
            "snapped": moved,
            "sentences": aligned,
        }, indent=2), encoding="utf-8")
        cfg.say(f"section {sec.stem}: {source}  conf {conf:.2f}  "
                f"{len(aligned)} sentences"
                + (f"  ({len(asr)} asr tokens, {moved} snapped)" if asr else ""))


def _source(prior: list, asr: list, conf: float) -> str:
    if prior and asr and conf >= CONF_FLOOR:
        return "exact+asr"
    if prior:
        return "exact"
    if asr and conf >= CONF_GOOD:
        return "asr"
    if asr and conf >= CONF_FLOOR:
        return "asr-weak"
    return "proportional"
