"""Narration: synthesis, pacing and mastering.

Two ideas carry this module.

**Synthesise one sentence at a time.** kokoro's own `create()` phonemises the
whole text, splits it on *spaces* at a 510-phoneme ceiling, trims the silence
off each batch and concatenates — so the seams land mid-clause and the pacing
is whatever falls out. Going sentence by sentence and inserting the pauses
ourselves fixes the pacing, and it hands us something more valuable for free:
**sentence boundaries that are exact by construction**, sample-accurate rather
than estimated. Everything downstream stops guessing.

**Master the programme, not the section.** Integrated loudness is a
programme-level measurement; normalising each section to -14 LUFS separately
flattens the dynamics you wrote in and makes a short punchy section jump. So
sections are concatenated as PCM first, mastered once, and encoded to AAC
exactly once — which also removes the ~4 ms of encoder priming gap that every
per-section AAC concat was accumulating.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import wave
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import cfg, mathspeech, textseg
from .project import Script, Section

ENGINE = 4                      # math-aware speech rendering invalidates old TTS cache
KOKORO_SR = 24000
PHONEME_LIMIT = 500             # kokoro truncates at 510; leave headroom
FADE_MS = 8.0                   # raised-cosine edge on each sentence

RAW_EXTS = (".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg")

_kokoro = None


# ------------------------------------------------------------- backends ----

KOKORO_RELEASE = ("https://github.com/thewh1teagle/kokoro-onnx/releases/"
                  "download/model-files-v1.0")
#: name -> (url, approximate MB), same shape and same _download() as the
#: whisper models in asrmodel.py — sizes are sanity bounds, not checksums.
KOKORO_FILES = {
    "kokoro-v1.0.onnx":      (f"{KOKORO_RELEASE}/kokoro-v1.0.onnx", 326),
    "kokoro-v1.0.int8.onnx": (f"{KOKORO_RELEASE}/kokoro-v1.0.int8.onnx", 92),
    "voices-v1.0.bin":       (f"{KOKORO_RELEASE}/voices-v1.0.bin", 28),
}


def _kokoro_paths() -> tuple[Path, Path]:
    kdir = cfg.ROOT / Path(os.environ.get("P2R_KOKORO_DIR", "tools/kokoro"))
    model = kdir / os.environ.get("P2R_KOKORO_MODEL", "kokoro-v1.0.onnx")
    voices = kdir / "voices-v1.0.bin"
    return model, voices


def fetch_kokoro(force: bool = False, int8: bool = False) -> tuple[Path, Path]:
    """Download the kokoro weights `prompt2render models --kokoro` needs once.

    int8 gets you a ~92 MB model instead of ~326 MB, at a small quality cost —
    the right trade on a CPU-only box. Same atomic-download discipline as the
    whisper models: fetch to .part, size-check, then rename into place.
    """
    from . import asrmodel
    kdir = cfg.ROOT / Path(os.environ.get("P2R_KOKORO_DIR", "tools/kokoro"))
    mname = "kokoro-v1.0.int8.onnx" if int8 else "kokoro-v1.0.onnx"
    for fname in (mname, "voices-v1.0.bin"):
        dst = kdir / fname
        if dst.exists() and not force:
            cfg.say(f"{fname} already present ({dst.stat().st_size/1e6:.1f} MB)")
            continue
        url, mb = KOKORO_FILES[fname]
        asrmodel._download(url, dst, mb)
    return kdir / mname, kdir / "voices-v1.0.bin"


def _ort_threads() -> int:
    """Intra-op threads for the TTS session.

    onnxruntime's CPU provider defaults to one thread per *logical* core,
    which on a machine with SMT means half the threads are fighting their own
    siblings for the same execution units — measurably slower than asking for
    the physical count. There is no portable way to read that, so half the
    logical count is the standard approximation, floored at 2 because a
    single-threaded session is the one setting that is definitely wrong.
    """
    want = cfg.env_int("P2R_TTS_THREADS", 0)
    if want > 0:
        return want
    return max(2, (os.cpu_count() or 4) // 2)


def kokoro():
    """The Kokoro session, loaded once per process.

    Built through an explicit InferenceSession where the installed
    kokoro-onnx allows it, so the thread count above actually takes effect —
    synthesis is the single longest local step in a build and it is entirely
    this session. Any version that does not expose `from_session` falls back
    to the plain constructor and simply runs with onnxruntime's defaults.
    """
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    model, voices = _kokoro_paths()
    if not model.exists() or not voices.exists():
        sys.exit(
            f"[prompt2render] kokoro model files not found under {model.parent}\n"
            "      run: python prompt2render.py models --kokoro  (~350 MB, one time)")
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        sys.exit("[prompt2render] kokoro-onnx not installed — pip install -r requirements.txt")

    _kokoro = _tuned_session(Kokoro, model, voices) or Kokoro(str(model),
                                                             str(voices))
    return _kokoro


def _tuned_session(Kokoro, model: Path, voices: Path):
    """A Kokoro bound to a thread-tuned onnxruntime session, or None."""
    if not hasattr(Kokoro, "from_session"):
        return None
    try:
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = _ort_threads()
        so.inter_op_num_threads = 1          # one graph at a time; no gain here
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess = ort.InferenceSession(str(model), sess_options=so,
                                    providers=["CPUExecutionProvider"])
        return Kokoro.from_session(sess, str(voices))
    except Exception as e:                   # noqa: BLE001
        cfg.warn(f"could not tune the TTS session ({type(e).__name__}); "
                 "falling back to onnxruntime defaults")
        return None


def voices() -> list[str]:
    return sorted(kokoro().get_voices())


def phoneme_len(text: str) -> int:
    """How many phonemes kokoro would produce. The truncation guard needs this."""
    try:
        return len(kokoro().tokenizer.phonemize(text, "en-us"))
    except Exception:                            # noqa: BLE001
        # espeak can fail on odd input; a character-count proxy is a safe
        # over-estimate and only ever causes a harmless extra split.
        return len(text)


# ------------------------------------------------------------ synthesis ----

@dataclass
class Cue:
    """One spoken sentence, timed against the start of its section."""
    i: int
    text: str
    start: float
    end: float


def _fade(pcm: np.ndarray, sr: int) -> np.ndarray:
    """Raised-cosine edges. kokoro's per-batch trim leaves a click otherwise."""
    n = min(int(sr * FADE_MS / 1000), len(pcm) // 2)
    if n <= 1:
        return pcm
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, n, dtype=np.float32)))
    out = pcm.copy()
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def pause_after(sent: textseg.Sentence, is_last: bool, pauses: dict) -> float:
    """Seconds of silence to place after this sentence."""
    if is_last:
        # A section ends into a dissolve; give the picture somewhere to land.
        return pauses["paragraph"] / 1000
    if sent.clause_continuation:
        return pauses["clause"] / 1000
    if sent.ends_question:
        return pauses["question"] / 1000
    return pauses["sentence"] / 1000


def _synth_one(args: tuple) -> tuple[np.ndarray, int]:
    """Pool worker. Top-level and tuple-argued so it pickles on Windows.

    A dedicated process, not a thread: kokoro-onnx's tokenizer binds
    espeak-ng in-process via ctypes (phonemizer's EspeakWrapper), and that
    binding carries no documented thread-safety guarantee -- concurrent
    calls sharing one loaded library risk silently wrong phonemes, not just
    contention, the same class of hazard stills.py's own docstring notes
    for FreeType. A separate process gets its own espeak-ng load, sidestepping
    the question rather than gambling on it. Each worker pays kokoro()'s
    model-load cost once, amortised across every sentence it synthesises --
    the same tradeoff align.py's --asr-jobs already makes.
    """
    text, voice_name, speed = args
    pcm, sr = kokoro().create(text, voice=voice_name, speed=speed, lang="en-us")
    return np.asarray(pcm, dtype=np.float32), sr


def synthesise(sentences: list[textseg.Sentence], voice: str, speed: float,
               pauses: dict, jobs: int | None = None) -> tuple[np.ndarray, list[Cue]]:
    """Render sentences to one f32 track at KOKORO_SR, with measured cues."""
    k = kokoro()
    if voice not in k.get_voices():
        sys.exit(f"[prompt2render] kokoro voice '{voice}' not available — "
                 "run: python prompt2render.py voices")

    # Break anything the synthesiser could not take whole *before* rendering,
    # so a long sentence becomes two clauses with a short pause rather than a
    # silently truncated one.
    prepared: list[textseg.Sentence] = []
    for s in sentences:
        prepared.extend(textseg.fit_to_synthesiser(s, phoneme_len, PHONEME_LIMIT))

    # The ONNX inference is what actually costs time; everything below stays
    # strictly sequential regardless (cursor position depends on every prior
    # sentence's length, so cue bookkeeping can't parallelise anyway) -- this
    # only precomputes each non-blank sentence's audio, in order, before that
    # loop runs. voice.py used to be the one pipeline stage with no
    # concurrency knob at all; every other stage (align, encode, scenes,
    # check) already has one.
    jobs = jobs or cfg.env_int("P2R_VOICE_JOBS", 1)
    # TTS receives a spoken rendering of recognized math spans. Cue text stays
    # as the original narration so captions and alignment retain the source.
    idx_text = [(i, mathspeech.speech_text(s.text))
                for i, s in enumerate(prepared) if s.text.strip()]
    if jobs > 1 and len(idx_text) > 1:
        n = max(1, min(jobs, len(idx_text)))
        cfg.say(f"synthesising {len(idx_text)} sentences, {n} at a time")
        payload = [(t, voice, speed) for _, t in idx_text]
        try:
            with ProcessPoolExecutor(max_workers=n) as pool:
                computed = list(pool.map(_synth_one, payload))
        except Exception as exc:
            # Do not silently fall back to serial synthesis after a worker
            # failure: a partial process pool can otherwise hide the real
            # backend error and make a failed build look like a cache issue.
            raise RuntimeError(
                f"parallel Kokoro synthesis failed with "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    else:
        computed = [_synth_one((t, voice, speed)) for _, t in idx_text]
    pcm_by_index = dict(zip((i for i, _ in idx_text), computed))

    chunks: list[np.ndarray] = []
    cues: list[Cue] = []
    cursor = 0                                   # in samples

    for n, sent in enumerate(prepared):
        if not sent.text.strip():
            continue
        pcm, sr = pcm_by_index[n]
        if sr != KOKORO_SR:                      # future-proof, not expected
            sys.exit(f"[prompt2render] kokoro returned {sr} Hz, expected {KOKORO_SR}")
        pcm = _fade(pcm, sr)

        start = cursor / sr
        chunks.append(pcm)
        cursor += len(pcm)
        cues.append(Cue(i=len(cues), text=sent.text,
                        start=round(start, 4), end=round(cursor / sr, 4)))

        gap = pause_after(sent, n == len(prepared) - 1, pauses)
        if gap > 0:
            silence = np.zeros(int(round(gap * sr)), dtype=np.float32)
            chunks.append(silence)
            cursor += len(silence)

    if not chunks:
        sys.exit("[prompt2render] nothing to synthesise — the section has no narration")
    return np.concatenate(chunks), cues


# ------------------------------------------------------------------ i/o ----

def _write_wav(pcm: np.ndarray, sr: int, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            sys.exit(f"[prompt2render] {path} is not 16-bit mono PCM")
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0, sr


def _resample_to_work(src: Path, dst: Path) -> None:
    """One high-quality resample to the delivery rate, done exactly once."""
    cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-af", f"aresample=resampler=soxr:precision=28:osr={cfg.AUDIO_SR}",
             "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


def _decode_recording(src: Path, dst: Path) -> None:
    cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-af", f"aresample=resampler=soxr:precision=28:osr={cfg.AUDIO_SR}",
             "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


def find_recording(audio_dir: Path, sec: Section) -> Path | None:
    """A recording you made, if there is one. Never matches our own output."""
    for ext in RAW_EXTS:
        for name in (f"{sec.stem}{ext}", f"{sec.index}{ext}"):
            p = audio_dir / name
            # audio/NN.m4a is *our* preview slice; treating it as a source
            # would re-master our own output every run.
            if p.exists() and not (ext == ".m4a" and name == f"{sec.stem}.m4a"):
                return p
    return None


# ------------------------------------------------------------- mastering ---

def _chain(profile: str) -> str:
    """The broadcast chain, in the order that actually works.

    HPF first: filtering after measurement would invalidate the measurement,
    which is what the old per-section `loudnorm,highpass` did.

    De-ess *after* the compressor: compression raises sibilance, so de-essing
    its output is what removes it. Note acompressor's threshold is linear
    (0.000976563-1), not dB — 0.089 is about -21 dBFS. Writing "-18dB" here is
    out of range and errors.
    """
    if profile == "voice":                       # a real microphone in a room
        return ("afftdn=nf=-28,"
                "highpass=f=90,"
                "acompressor=threshold=0.063:ratio=3:attack=8:release=150:"
                "makeup=2:knee=6:detection=rms,"
                "deesser=i=0.4:m=0.5:f=0.45:s=o")
    return ("highpass=f=85,"                     # tts: already even
            "acompressor=threshold=0.089:ratio=2.5:attack=12:release=200:"
            "makeup=1.8:knee=6:detection=rms,"
            "deesser=i=0.35:m=0.5:f=0.45:s=o")


def _read_loudnorm_stats(stats: Path) -> dict:
    if not stats.exists():
        sys.exit(f"[prompt2render] loudnorm wrote no stats to {stats}")
    text = stats.read_text(encoding="utf-8")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        sys.exit(f"[prompt2render] loudnorm wrote invalid stats to {stats}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        sys.exit(f"[prompt2render] invalid loudnorm JSON in {stats}: {exc}")
    if "input_i" not in data or "input_tp" not in data:
        sys.exit(f"[prompt2render] loudnorm stats missing input_i/input_tp in {stats}")
    return data


def _measure(src: Path, chain: str, lufs: float, stats: Path) -> dict:
    stats.parent.mkdir(parents=True, exist_ok=True)
    stats.unlink(missing_ok=True)
    cfg.run([
        "ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-y", "-i", str(src),
        "-af", (f"{chain},loudnorm=I={lufs}:TP={cfg.TRUE_PEAK}:LRA={cfg.LRA}"
                f":print_format=json:stats_file={cfg.filter_path(stats)}"),
        "-f", "null", "-",
    ])
    return _read_loudnorm_stats(stats)


def loudness_of(src: Path) -> dict:
    """Measure a finished file without applying anything. Used by qc."""
    with tempfile.TemporaryDirectory(prefix="prompt2render-ln-") as td:
        stats = Path(td) / "ln.json"
        cfg.run([
            "ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-y",
            "-i", str(src), "-map", "0:a:0",
            "-af", (f"loudnorm=I={cfg.LUFS}:TP={cfg.TRUE_PEAK}:LRA={cfg.LRA}"
                    f":print_format=json:stats_file={cfg.filter_path(stats)}"),
            "-f", "null", "-",
        ])
        return _read_loudnorm_stats(stats)


def _apply(src: Path, dst: Path, chain: str, gain_db: float) -> None:
    """Chain, one static gain, then a peak limiter. Nothing dynamic."""
    # alimiter caps *sample* peaks; true peak is reconstructed between samples
    # and measures a few tenths higher. Give it that margin so the delivered
    # file really is under the target rather than just about.
    limit = 10 ** ((cfg.TRUE_PEAK - 0.3) / 20)   # -1.8 dB -> 0.813 linear
    cfg.run([
        "ffmpeg", "-y", "-hide_banner", "-v", "error", "-i", str(src),
        "-af", (
            f"{chain},"
            f"volume={gain_db:+.3f}dB,"
            # level=0 matters: the default auto-level normalises *up* to the
            # limit and would undo the gain staging. latency=1 compensates the
            # 5 ms lookahead so the limiter cannot shift the programme
            # relative to the alignment.
            f"alimiter=limit={limit:.4f}:attack=5:release=50:level=0:latency=1,"
            f"aresample=resampler=soxr:precision=28:osr={cfg.AUDIO_SR}"
        ),
        "-ar", str(cfg.AUDIO_SR), "-ac", "1", "-c:a", "pcm_s16le", str(dst),
    ])


def master(raw_master: Path, dst_wav: Path, dst_m4a: Path,
           lufs: float, profile: str) -> dict:
    """Measure, apply one static gain, limit the peaks, verify.

    Why not loudnorm's own two-pass `linear=true`: narration at -20 LUFS with
    peaks at -5 dBTP needs +6 dB to reach -14, which would put the peaks above
    0 dBFS. loudnorm sees that, silently gives up on linear, and falls back to
    `dynamic` — gain riding, which is exactly what flattens the pacing the
    pauses were inserted to create. Measured on this very programme.

    So the gain staging is explicit instead: one static gain (dynamics
    untouched, to the sample) followed by a lookahead limiter that only ever
    touches the loudest transients. That is what a mastering engineer does,
    and unlike loudnorm it cannot quietly change strategy on us.
    """
    if not raw_master.exists() or raw_master.stat().st_size <= 44:
        sys.exit(f"[prompt2render] empty or missing raw programme: {raw_master}")

    chain = _chain(profile)
    stats = raw_master.with_name("loudnorm.json")

    cfg.say("measuring programme loudness")
    m = _measure(raw_master, chain, lufs, stats)
    gain = lufs - float(m["input_i"])
    cfg.say(f"  {float(m['input_i']):.2f} LUFS, peak {float(m['input_tp']):.2f} "
            f"dBTP -> applying {gain:+.2f} dB")

    _apply(raw_master, dst_wav, chain, gain)

    # Limiting removes a little energy, so verify and trim once rather than
    # assume. One extra audio-only pass; cheap, and it makes the loudness gate
    # deterministic instead of hopeful.
    #
    # The delivery AAC encode reads the same finished WAV and does not depend
    # on what the verification finds, so the two go at once. In the ordinary
    # case (no trim needed) that is one whole pass over the programme saved;
    # in the rare trim case both are simply redone, exactly as before. The
    # AAC is still encoded from the quantised 16-bit file rather than from the
    # filter graph, so the delivered bytes are unchanged.
    def encode_aac() -> None:
        cfg.run(["ffmpeg", "-y", "-hide_banner", "-v", "error",
                 "-i", str(dst_wav), "-c:a", "aac", "-b:a", cfg.AAC_BITRATE,
                 "-ar", str(cfg.AUDIO_SR), "-ac", "1", str(dst_m4a)])

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_aac = pool.submit(encode_aac)
        got = loudness_of(dst_wav)
        f_aac.result()

    err = lufs - float(got["input_i"])
    if abs(err) > 0.3:
        cfg.say(f"  landed at {float(got['input_i']):.2f} LUFS, "
                f"trimming {err:+.2f} dB")
        _apply(raw_master, dst_wav, chain, gain + err)
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_aac = pool.submit(encode_aac)
            got = loudness_of(dst_wav)
            f_aac.result()

    return {**m, "applied_gain_db": round(gain, 3),
            "output_i": got["input_i"], "output_tp": got["input_tp"],
            "normalization_type": "linear+limit"}


# --------------------------------------------------------------- driver ----

def _meta(backend: str, voice: str, speed: float, text: str,
          pauses: dict, n: int, samples: int) -> dict:
    return {
        "engine": ENGINE, "backend": backend, "voice": voice, "speed": speed,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "pauses": pauses, "n_sentences": n, "samples": samples,
    }


def settings(args=None) -> dict:
    """Voice settings from flags, then env, then defaults."""
    g = lambda n, d: getattr(args, n, None) or d   # noqa: E731
    return {
        "backend": g("backend", os.environ.get("P2R_TTS_BACKEND", "kokoro")),
        "voice": g("voice", os.environ.get("P2R_KOKORO_VOICE", "am_eric")),
        "speed": float(g("speed", cfg.env_float("P2R_KOKORO_SPEED", 1.0))),
        "lufs": float(g("lufs", cfg.env_float("P2R_LUFS", cfg.LUFS))),
        "profile": g("audio_profile", "tts"),
        "pauses": {
            "sentence": int(g("pause_sentence",
                              cfg.env_int("P2R_PAUSE_SENTENCE_MS",
                                          cfg.PAUSE_SENTENCE_MS))),
            "question": cfg.PAUSE_QUESTION_MS,
            "clause": cfg.PAUSE_CLAUSE_MS,
            "paragraph": int(g("pause_paragraph",
                               cfg.env_int("P2R_PAUSE_PARAGRAPH_MS",
                                           cfg.PAUSE_PARAGRAPH_MS))),
        },
    }


def build(proj: Path, script: Script, opts: dict, only: str | None = None,
          force: bool = False) -> Path:
    """Synthesise, then master. Returns build/master.wav."""
    cfg.need("ffmpeg", "ffprobe")
    vdir = proj / "build" / "voice"
    vdir.mkdir(parents=True, exist_ok=True)
    audio_dir = proj / "audio"
    audio_dir.mkdir(exist_ok=True)

    backend, pauses = opts["backend"], opts["pauses"]
    used_own = False

    for sec in script.sections:
        if only and sec.stem != only:
            continue
        sdir = vdir / sec.stem
        sdir.mkdir(parents=True, exist_ok=True)
        raw, cues_f, meta_f = sdir / "raw.wav", sdir / "sentences.json", sdir / "meta.json"

        own = find_recording(audio_dir, sec)
        if own or backend == "own":
            if not own:
                sys.exit(f"[prompt2render] backend 'own' but no recording for section "
                         f"{sec.stem} in {audio_dir}")
            used_own = True
            src_hash = hashlib.sha256(own.read_bytes()).hexdigest()
            want = {"engine": ENGINE, "backend": "own", "source_sha256": src_hash}
            if raw.exists() and meta_f.exists() and not force \
                    and json.loads(meta_f.read_text()) == want:
                cfg.say(f"section {sec.stem}: recording unchanged, skipping")
                continue
            cfg.say(f"section {sec.stem}: using your recording ({own.name})")
            _decode_recording(own, raw)
            # No exact cues: alignment falls to the ASR rank of the chain.
            cues_f.write_text(json.dumps([]), encoding="utf-8")
            meta_f.write_text(json.dumps(want, indent=2), encoding="utf-8")
            continue

        if backend != "kokoro":
            sys.exit(f"[prompt2render] backend '{backend}' is not supported for synthesis "
                     "— use kokoro, or record into <project>/audio/")

        if not sec.narration.strip():
            sys.exit(f"[prompt2render] section {sec.stem} has no narration text")

        sents = textseg.sentences(sec.narration)
        want = _meta(backend, opts["voice"], opts["speed"], sec.narration,
                     pauses, len(sents), 0)
        if raw.exists() and meta_f.exists() and not force:
            have = json.loads(meta_f.read_text())
            if {k: v for k, v in have.items() if k != "samples"} == \
               {k: v for k, v in want.items() if k != "samples"}:
                cfg.say(f"section {sec.stem}: cached, skipping")
                continue

        cfg.say(f"section {sec.stem}: {len(sents)} sentences "
                f"({opts['voice']} @ {opts['speed']:g}x)")
        pcm, cues = synthesise(sents, opts["voice"], opts["speed"], pauses)

        with tempfile.TemporaryDirectory(prefix="prompt2render-tts-") as td:
            native = Path(td) / "native.wav"
            _write_wav(pcm, KOKORO_SR, native)
            _resample_to_work(native, raw)

        cues_f.write_text(json.dumps([asdict(c) for c in cues], indent=2),
                          encoding="utf-8")
        want["samples"] = len(pcm)
        meta_f.write_text(json.dumps(want, indent=2), encoding="utf-8")
        cfg.say(f"  {len(pcm)/KOKORO_SR:.1f}s across {len(cues)} measured cues")

    if only:
        # `--only` is a synthesis/cache operation, not a partial programme
        # master. A programme master necessarily needs every section in order.
        # Refuse here with a useful message instead of failing later on a
        # missing raw.wav from another section.
        missing = [
            sec.stem for sec in script.sections
            if not (vdir / sec.stem / "raw.wav").exists()
        ]
        if missing:
            sys.exit(
                f"[prompt2render] voice --only {only} produced no full master; "
                f"missing section audio: {', '.join(missing)}"
            )

    return _assemble_master(proj, script, opts, used_own)


def _assemble_master(proj: Path, script: Script, opts: dict,
                     used_own: bool) -> Path:
    """Concat section PCM, master once, slice previews."""
    vdir = proj / "build" / "voice"
    build = proj / "build"
    raw_master = vdir / "raw_master.wav"

    tracks: list[np.ndarray] = []
    for sec in script.sections:
        p = vdir / sec.stem / "raw.wav"
        if not p.exists():
            sys.exit(f"[prompt2render] section {sec.stem} has no voice — run `prompt2render voice` "
                     "for every section before mastering")
        pcm, sr = _read_wav(p)
        if sr != cfg.AUDIO_SR:
            sys.exit(f"[prompt2render] {p} is {sr} Hz, expected {cfg.AUDIO_SR}")
        if pcm.size == 0:
            sys.exit(f"[prompt2render] {p} contains no audio samples")
        tracks.append(pcm)

    if used_own:
        tracks = _match_levels(tracks)

    # Concatenating PCM in memory is exact. Concatenating the encoded AAC (as
    # the old finish stage did) adds ~4 ms of encoder priming per section.
    _write_wav(np.concatenate(tracks), cfg.AUDIO_SR, raw_master)

    master_wav, master_m4a = build / "master.wav", build / "master.m4a"
    stats = master(raw_master, master_wav, master_m4a,
                   opts["lufs"], opts["profile"])

    offsets, clock = {}, 0.0
    for sec, pcm in zip(script.sections, tracks):
        offsets[sec.stem] = {"start": round(clock, 6),
                             "dur": round(len(pcm) / cfg.AUDIO_SR, 6),
                             "samples": len(pcm)}
        clock += len(pcm) / cfg.AUDIO_SR

    (build / "audio_map.json").write_text(json.dumps({
        "sample_rate": cfg.AUDIO_SR, "total": round(clock, 6),
        "lufs_target": opts["lufs"], "measured": stats, "sections": offsets,
    }, indent=2), encoding="utf-8")

    _slice_previews(proj, script, master_wav, offsets)
    cfg.say(f"master: {master_wav.name}  ({clock/60:.2f} min)  "
            f"{float(stats['output_i']):.2f} LUFS, "
            f"{float(stats['output_tp']):.2f} dBTP")

    # Pace is the one thing a synthesised voice gets wrong in a way that is
    # obvious to a listener and invisible in the logs. Say it out loud.
    wpm = script.word_count / (clock / 60) if clock else 0
    note = ""
    if wpm > 170:
        note = "  <- fast for an explainer; try --speed 0.85"
    elif wpm < 120:
        note = "  <- slow; try --speed 1.1"
    cfg.say(f"pace: {script.word_count} words in {clock/60:.1f} min "
            f"= {wpm:.0f} wpm{note}")
    return master_wav


def _match_levels(tracks: list[np.ndarray]) -> list[np.ndarray]:
    """Bring each section toward the programme median before concatenation.

    Sections recorded on different days sit at different levels; fixing that
    before a single programme-wide measurement is the professional order of
    operations.
    """
    def lufs_ish(x: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
        return 20 * np.log10(max(rms, 1e-9))

    levels = [lufs_ish(t) for t in tracks]
    target = float(np.median(levels))
    out = []
    for t, lv in zip(tracks, levels):
        delta = target - lv
        if abs(delta) > 0.5:
            cfg.say(f"  level match: {delta:+.1f} dB")
            t = t * (10 ** (delta / 20))
        out.append(np.clip(t, -1.0, 1.0))
    return out


def _slice_previews(proj: Path, script: Script, master_wav: Path,
                    offsets: dict) -> None:
    """audio/NN.m4a for auditioning. Never an input to anything.

    One short AAC encode per section, and no section depends on another, so
    they go out together rather than one after the next.
    """
    audio = proj / "audio"
    audio.mkdir(exist_ok=True)

    def slice_one(sec) -> None:
        o = offsets[sec.stem]
        dst = audio / f"{sec.stem}.m4a"
        part = dst.with_name(dst.stem + ".part.m4a")
        cfg.run(["ffmpeg", "-y", "-v", "error",
                 "-ss", f"{o['start']:.6f}", "-t", f"{o['dur']:.6f}",
                 "-i", str(master_wav),
                 "-c:a", "aac", "-b:a", cfg.AAC_BITRATE,
                 "-ar", str(cfg.AUDIO_SR), "-ac", "1",
                 str(part)])
        part.replace(dst)

    cfg.parallel(slice_one, list(script.sections),
                 cfg.env_int("P2R_AUDIO_JOBS", 4), "preview")


def section_cues(proj: Path, stem: str) -> list[Cue]:
    """Exact synthesis cues for a section, or [] when there are none."""
    p = proj / "build" / "voice" / stem / "sentences.json"
    if not p.exists():
        return []
    return [Cue(**c) for c in json.loads(p.read_text(encoding="utf-8"))]


def audio_map(proj: Path) -> dict:
    p = proj / "build" / "audio_map.json"
    if not p.exists():
        sys.exit("[prompt2render] no build/audio_map.json — run `prompt2render voice` first")
    return json.loads(p.read_text(encoding="utf-8"))