# Transcription-stage optimization log

Investigation into the reported bottleneck:

```
transcribing 4.8 min with ggml-base.en.bin — this is the slow step, and it is cached
```

Machine: 8 logical cores (Intel, 4c/8t class), NVIDIA MX350 (2 GB VRAM),
ffmpeg 8.1.2 built `--enable-whisper` (bundled whisper.cpp, no CUDA whisper
backend advertised). Model: `ggml-base.en.bin` (148 MB), CPU-only
(`use_gpu=0` — no whisper GPU backend in this ffmpeg build).

## Stage 1/2 findings — architecture was already mostly right

Before touching anything: `prompt2render/align.py` already implements the
"known script is source of truth" architecture the brief asks to evaluate.
Whisper contributes **timing only** — its text output is matched against
`script.md` via `difflib`, matched tokens become anchors, everything else is
interpolated, and on the kokoro TTS path sentence boundaries are already
sample-exact from synthesis and clamp the ASR (`clamp_to_prior`). A whisper
word error cannot reach the output; it just fails to match and gets dropped.
Model load is already amortized once per programme
(`transcribe_programme`), not once per section. Chunk-parallel transcription
(`--asr-jobs`) and concurrent silence-detection already exist. So H4 ("is
whisper only used for timestamps, should we force-align instead") was
already answered *yes* by the existing code — the open question was why the
already-alignment-only ASR pass was still slow.

## Baseline (QuickSort project, 286.9 s / 4.78 min master.wav — the exact
duration behind the reported "4.8 min" log line)

A forced, uncached, single-job `align` run was let run for 701 s wall time
(869.6 s of accumulated CPU time — ~1.24 of 8 cores in use, poor
parallelism) and had **not finished**, so it was killed. Extrapolating from
the isolated 30 s-slice rate below (6.68 s of wall time per second of
audio), the full run would have landed around **1920 s (~32 min)** for 4.8
min of audio — an RTF (real-time factor) of ~6.7x slower than real time.

Isolated, controlled slices (same options `align.py` used: `queue=20`,
`use_gpu=0`, `format=srt`, `max_len=1`, plus `vad_model=`):

| slice | wall time | RTF (wall/audio) |
|---|---|---|
| 5 s  | 19.46 s  | 3.89x |
| 30 s | 200.40 s | 6.68x |

RTF got *worse*, not better, as duration grew — ruling out "fixed model-load
overhead" as the explanation and pointing at something that scales badly
with buffered audio length.

## EXP-01

**Hypothesis:** ffmpeg's whisper-filter VAD integration (`vad_model=`,
added to suppress hallucination in the pauses the TTS engine inserts) is the
dominant cost, not the ASR model itself.

**Change:** stop passing `vad_model=` / `vad_threshold=` /
`vad_min_silence_duration=` to the whisper filter in
`prompt2render/align.py:transcribe()`. Also stopped auto-fetching the now-unused
VAD model from `prompt2render models --asr` (`prompt2render.py:cmd_models`) and
removed the now-stale "VAD model" row from `prompt2render doctor`
(`doctor.py:_check_align`).

**Isolation (30 s slice):**

| variant | wall time | vs baseline |
|---|---|---|
| baseline (VAD on) | 200.40 s | — |
| VAD off | 16.85 s | **11.9x faster** |
| `max_len=1` removed (VAD still on) | 203.88 s | no change — rules out max_len as the cause |

**Full-scale confirmation (QuickSort, 288 s audio, single job, VAD off):**
218.18 s wall time — RTF **0.76x** (faster than real time), vs. baseline's
extrapolated ~1920 s. **~8.8x faster.**

**Output-quality validation (bubble-sort project, 266.4 s audio, 6
sections — this project already had a real VAD-on transcript cached from a
prior normal run, giving a genuine before/after on identical audio):**
re-ran `align.py`'s own `reconcile()` against a freshly generated VAD-off
transcript and compared to the recorded VAD-on confidence per section.

| section | VAD-on confidence (recorded) | VAD-off confidence (fresh) |
|---|---|---|
| 01 | 0.923 | 0.936 |
| 02 | 0.969 | 0.975 |
| 03 | 0.932 | 0.932 |
| 04 | 0.894 | 0.881 |
| 05 | 0.879 | 0.887 |
| 06 | 0.920 | 0.911 |

No section moved by more than 0.013; all comfortably above `CONF_FLOOR`
(0.60) and mostly above `CONF_GOOD` (0.85) either way. This matches the
architecture's own design: an unmatched (hallucinated) token is just an
ignored `difflib` insert, not a corruption. Timestamp invariants
(`start<=end`, monotonic across sentences and words) held on every section
of the fresh output.

**Regression status:** none observed. All 22 existing tests pass. Full
end-to-end `prompt2render align QuickSort --force` through the real (non-mocked)
CLI landed all 8 sections at `exact+asr`, confidence 0.83–0.96, 0 timestamp
invariant violations.

**Decision: KEEP.**

## EXP-02 (no code change — exercising an existing knob)

**Hypothesis:** the existing `--asr-jobs` / `P2R_ASR_JOBS` chunked
parallelism (splits the programme on section joins, one whisper pass per
chunk, already implemented) stacks with the VAD fix, since VAD removal
turned the workload from "barely parallel, ~1.24 of 8 cores" into a
straightforwardly CPU-bound job that benefits from process-level fan-out.

**Result (QuickSort, 288 s audio, VAD off, `--asr-jobs 4`):**
113.4 s wall time end-to-end through the real CLI — RTF **0.39x**. Combined
with EXP-01, this is roughly **17x faster** than the original baseline
estimate. Confidence 0.83–0.96 across 8 sections, no fallback triggered.

**Decision: document, don't change the default.** `align.py` already warns
(correctly) that chunk-parallel ASR can shift a word timing by a few
milliseconds at a chunk edge, since whisper loses cross-chunk context there
— an explicit, pre-existing, opt-in tradeoff. That reasoning is sound and
predates this investigation, so the default stays at `1`; `--asr-jobs 4` (or
whatever matches the machine's core count) is now a very effective
complementary lever worth reaching for explicitly, especially since EXP-01
removed the main serialization bottleneck it used to fight against.

## Rejected / deferred hypotheses

- **H2 (GPU execution).** This ffmpeg build advertises no whisper CUDA
  backend (`use_gpu=0` in the existing code is already a measured, documented
  choice — see the `align.py`/`voice.py` comments referencing the MX350's 2
  GB VRAM). Nothing to test without a different ffmpeg/whisper.cpp build;
  not pursued.
- **H3 (alternative backend — faster-whisper / whisper.cpp CLI).** Neither
  is installed; either would add a new heavy dependency (torch or
  ctranslate2) for a pipeline that currently needs none for alignment. Given
  EXP-01 alone already reaches RTF < 1, and EXP-01+EXP-02 reaches RTF ~0.39,
  the marginal further win didn't justify the dependency and validation cost
  in this pass. Worth revisiting only if a future workload needs faster than
  that.
- **H4 (replace ASR with forced alignment).** Already the architecture — see
  Stage 1/2 findings above. No change made.
- **H6 (cache design) — one real gap found, not fixed here.** The
  *transcript* cache (`transcribe_programme`) is correctly content-hashed
  (audio digest + model + job count). The *per-section alignment* cache
  (`align()`'s `if dst.exists() and not force: skip`) is existence-based, not
  hashed against the section's narration text — editing `script.md` without
  passing `--force` silently ships stale timing. Out of scope for a
  transcription-*latency* fix; flagged for a follow-up.

## Bottom line

> Is prompt2render faster by optimizing Whisper, replacing it with alignment,
> parallelizing the pipeline, or combining all three?

Replacing ASR with forced alignment was already done architecturally.
Optimizing Whisper's *invocation* (dropping a pathologically slow VAD
integration in ffmpeg's whisper filter) was the real lever: **~8.8x** on its
own, measured end-to-end on the exact 4.8-minute case from the bug report,
with no measured confidence regression on a second, independent real
project. Stacking the pipeline's existing chunk parallelism on top reaches
**~17x**, turning a >30-minute (estimated) transcription stage into under
two minutes for the same audio.
