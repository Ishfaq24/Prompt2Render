# Migration Inventory — legacy pipeline → Prompt2Render harness

Stage 0 deliverable. Read-only survey; nothing in the repo was modified to produce this
document. Scope: understand what exists today precisely enough that Stages 1–5 of the migration
wrap real behavior instead of an assumed one.

---

## 0. Premise correction — read this first

The migration brief describes moving "an existing, working... Planner/Coder/Critic over Manim"
system into Prompt2Render. That architecture exists in this repository, but **only** as
`vendor/Code2Video/` — a vendored reference clone with its own nested `.git`, patched to call
Gemini/Claude/GPT-4o/GPT-5 through `openai`-compatible endpoints (`vendor/Code2Video/src/
gpt_request.py`). It implements a real Planner→Storyboard→Coder→Critic→Eval loop
(`vendor/Code2Video/src/agent.py`, `TeachingVideoAgent`, stages 1–5 in
`vendor/Code2Video/src/prompts/stage{1..5}*.py`), generating Manim `Scene` subclasses and
critiquing rendered video with a vision-model call (`request_gemini_video_img`).

It is **not live**. `grep -rn "vendor" prompt2render/ prompt2render.py` and `grep -rn "Code2Video" prompt2render/ prompt2render.py`
return zero `import`/call sites — every hit is a prose comment or docstring referencing
Code2Video by name for context, not a dependency. `prompt2render animate`, the CLI command that used to
drive it, is now a permanent stub (`prompt2render.py:222`, `cmd_animate`) that exits immediately pointing
at `docs/RETIRED.md`.

`docs/RETIRED.md` explains why: Code2Video rendered at 480p15 (unshippable), its layout critic
needs a vision-model call the affordable Gemini AI Studio endpoint doesn't support (so the
critic never actually ran, and the paper's own human raters scored its layout 60/100 against
98/100 for hand-made), and it produced one opaque clip per section with no internal cue
structure — forcing a hold-last-frame hack to fit narration, never real sync.

**What is actually live and run end-to-end by `prompt2render.py build` today** is the system that
replaced it: a model storyboards each section against a small, fixed, non-Manim drawing API
(`prompt2render/scenekit.py`), and the critic is a deterministic pixel-geometry auditor reading the
rendered frame's own matplotlib geometry — no vision model, no second API call. Sections become
timed stills cut to the word, not one opaque clip force-fit afterward.

**Resolved with the user (2026-08-20):** Prompt2Render migrates *this* live scenekit pipeline.
`vendor/Code2Video` is documented as disconnected reference material and is not wrapped as a
live plugin set. Section 5 below gives the plugin-role remapping this implies, so Stage 3 has an
explicit, agreed mapping instead of inventing one under pressure to match the brief's original
Manim/VLM framing.

**Update (2026-08-21):** per the user, `vendor/Code2Video/` and `vendor/Code2Video.zip` have been
deleted from disk entirely (they were untracked and git-ignored, so this touches no git history).
Every reference to it in this document is now a historical/comparative pointer to code that no
longer exists in the repo — kept for the reasoning trail, not as a live path.

**Also resolved:** the working tree currently diverges from `HEAD` (commit `276581d`) — see
Section 9. `prompt2render/web/`'s deletion is intentional and out of scope for this migration. The other
uncommitted changes (13 core files, several deleted `projects/*/script.md`) are to be treated as
the current, working state — snapshotted as-is for Stage 1's golden baseline, not reverted to
`HEAD` and not committed by this migration.

---

## 1. Current pipeline map

**Entry point:** `prompt2render.py` (argparse subparsers, `main()`). Every subcommand:

| command | function (prompt2render.py) | role |
|---|---|---|
| `new` | `cmd_new` | scaffold `projects/<slug>/{sections,audio,build,out}` + `script.md` |
| `doctor` | `cmd_doctor` | environment check (`prompt2render/doctor.py`) |
| `models` | `cmd_models` | fetch local whisper/VAD/Kokoro weights |
| `voices` | `cmd_voices` | list Kokoro voice names |
| `serve` | `cmd_serve` | launch `prompt2render.web.app:app` under uvicorn — **currently deleted from disk, intentionally (§9)** |
| `voice` | `cmd_voice` | stage: TTS + programme mastering |
| `align` | `cmd_align` | stage: force-alignment |
| `scenes` | `cmd_scenes` | stage: LLM storyboards each section against scenekit |
| `stills` | `cmd_stills` | stage: render scene module(s) → PNGs (usually a no-op, see below) |
| `plan` | `cmd_plan` | stage: `timeline.build` — decide when each still appears |
| `encode` | `cmd_encode` | stage: one clip per still |
| `finish` | `cmd_finish` | stage: concat/mux/caption/chapter |
| `check` | `cmd_check` | stage: QC gates (`prompt2render/qc.py`) |
| `build` | `cmd_build` | **the whole chain, see below** |
| `import` | `cmd_import` | escape hatch: bring in external clips |
| `placeholders` | `cmd_placeholders` | escape hatch: title-card stand-ins |
| `manim` | `cmd_manim` | escape hatch: render one hand-authored Manim scene |
| `assemble` | `cmd_assemble` | **legacy sync path**, for `prompt2render import`ed clips only |
| `publish` | `cmd_publish` | write `out/upload.md` |
| `animate` | `cmd_animate` | **retired stub** — always exits, points at `docs/RETIRED.md` |

**`cmd_build`'s exact stage order** (`prompt2render.py:154-171`):

```
voice.build(...)  →  align.align(...)  →  scenes.generate_all(...)  →
stills.render_many(...)  →  timeline.build(...)  →  encode.encode(...)  →
finish.finish(...)  →  publish.build_packet(...)  →  qc.check(...)  [exit code]
```

`stills.render_many` in this chain is usually a no-op: `scenes.generate()` already renders and
audits each candidate inline as part of accepting it (§4), so by the time `build` reaches the
`stills` stage the PNGs already exist and are current. The stage exists for the case where a
human hand-edits `build/scenes/scene_NN.py` after generation — `stills` notices the mtime is
newer than the manifest and re-renders just that section.

`assemble.py` (legacy) and `visuals.py` (import/placeholders/manim) are **not** in this chain —
separate, hand-invoked CLI subcommands only. `publish.py` does have one genuine cross-dependency
on the "legacy" module: it imports `assemble.chapters()` for chapter-marker text.

---

## 2. Where state lives

**`prompt2render/cfg.py`** is the de facto globals module — nearly every other file does
`from . import cfg` and reads its module-level constants/caches directly, not through any passed
config object:

- Paths: `ROOT`, `PROJECTS`, `MODELS`; `project_dir(slug)` derives per-project paths at runtime.
- Video: `WIDTH/HEIGHT/FPS = 1920/1080/30`, `CRF`, four ffmpeg option vectors
  (`VOPTS`/`VOPTS_PREVIEW`/`VOPTS_PREVIEW_CPU`/`VOPTS_GPU`) — shared so all clips are
  byte-identical for `-c copy` concat later.
- Audio: `AUDIO_SR`, `TTS_SR`, `AAC_BITRATE`, `LUFS`, `TRUE_PEAK`, `LRA`.
- Timing: `PAUSE_SENTENCE_MS`/`PAUSE_QUESTION_MS`/`PAUSE_CLAUSE_MS`/`PAUSE_PARAGRAPH_MS`,
  `VISUAL_LEAD_MS`.
- Caption: `CAPTION_LINE`, `CAPTION_LINES`, `CAPTION_MIN_S`/`MAX_S`/`CPS`, `CAPTION_FONT`.
- Module-level mutable caches: `_probe_cache`/`_probe_lock` (ffprobe results, keyed on
  path+size+mtime, shared across stages), `_gpu_ok` (GPU-encode probe, cached once).
- `load_env()` — the only place `.env` gets loaded, called once in `prompt2render.py main()`.

**No single source of truth for `P2R_*` env vars.** `cfg.py` itself only names `P2R_PROBE_JOBS`
via its own `env_int`/`env_float` helpers; every other `P2R_*` var is read inline, per-module,
with its own default: `P2R_MOTION`/`P2R_VISUAL_LEAD_MS` (timeline.py), `P2R_STILLS_JOBS`
(stills.py), `P2R_WHISPER_MODEL`, `P2R_TTS_BACKEND`, `P2R_KOKORO_DIR/MODEL/VOICE`,
`P2R_SCENE_MODEL`, `P2R_REASONING`, `P2R_SCENE_JOBS` (scenes.py), `P2R_CONCAT_JOBS` (finish.py),
`P2R_ASR_JOBS` (align.py), `P2R_QC_JOBS` (qc.py), `P2R_PNG_COMPRESS`/`P2R_PNG_EXACT`
(scenekit.py), `P2R_TTS_THREADS`, `P2R_KOKORO_SPEED`, `P2R_LUFS`,
`P2R_PAUSE_SENTENCE_MS`/`P2R_PAUSE_PARAGRAPH_MS`, `P2R_AUDIO_JOBS` (voice.py). `GEMINI_API_KEY`
(+`GEMINI_API_KEY_BACKUP*`) is read in `doctor.py`, `scenes.py`. This scatter is itself a
migration-relevant finding — Stage 2's plugin loader/config is a natural place to consolidate it,
but that consolidation is not this migration's job unless scoped in later.

### File-based reach-around table (the real migration work)

Every hop below is a bare filesystem path convention, not an in-memory handoff. Most are guarded
by an explicit `sys.exit` telling the user which prior stage to run if the file is missing
(cited); a few are silent.

| stage | reads (written by) | writes | guarded? |
|---|---|---|---|
| `voice.build` | `script.md` (project.py); `audio/<stem>.*` (optional user recording) | `build/voice/<stem>/{raw.wav,sentences.json,meta.json}`, `build/master.wav`, `build/master.m4a`, `build/audio_map.json` | n/a (first stage) |
| `align.align` | `build/master.wav`, `build/audio_map.json`, `build/voice/<stem>/sentences.json` (all voice.py) | `build/align/<stem>.json` | guarded — align.py:505 exits "no build/master.wav — run `prompt2render voice` first" |
| `scenes.generate` | `build/align/<stem>.json` (align) | `build/scenes/scene_<stem>.py`, `build/scenes/<stem>/{*.png,manifest.json,audit.json}` | guarded — scenes.py:238 exits "no alignment — run `prompt2render align`" |
| `stills.render_many` | `build/scenes/scene_<stem>.py` (scenes), `build/align/<stem>.json` (align, for cue count) | same PNG/manifest/audit set (usually already current, no-op) | n/a — cache check via `is_current()` |
| `timeline.build` | `build/scenes/<stem>/manifest.json` (stills), `build/align/<stem>.json` (align), `build/audio_map.json` (voice) | `build/plan.json` | implicit — reads what's there |
| `encode.encode` | `build/plan.json` (timeline), `build/scenes/<stem>/*.png` (stills) | `build/clips/*.mp4` | guarded — encode.py:79 exits "missing still ... run `prompt2render stills`" |
| `finish.finish` | `build/plan.json`, `build/clips/*.mp4` (encode), `build/master.m4a` (voice), `build/align/*` + `build/audio_map.json` (captions.py) | `sections/<stem>.mp4`, `build/video.mp4`, `out/final.mp4`, `out/captions.srt`, `out/thumb_source.png` | guarded — finish.py:38 exits "clip not encoded yet — run `prompt2render encode --all`"; also `_preflight()` hard-fails if clips don't share one `cfg.video_params()` profile (mixed `--preview`/final passes) |
| `qc.check` | `out/final.mp4` (finish), `build/plan.json`, `build/align/*`, scene modules + `audit.json` | `out/qc.json` | implicit |
| `publish.build_packet` | `script.md` only (word count, `assemble.chapters()`) | `out/upload.md` | n/a |

`stills.is_current()` (stills.py:229) is the one piece of real cache-invalidation logic beyond
mtime-vs-mtime: it also compares against `scenekit.py`'s own mtime, so editing the critic
invalidates every cached still project-wide — an implicit dependency edge worth preserving
explicitly once this becomes a `declare_dependencies()` plugin.

---

## 3. Planner / Coder / Critic / Render / Repair / RAG / Audio — located and classified

- **Planner + Coder ≈ `prompt2render/scenes.py`** (`generate()`/`generate_all()`, 370 lines). LLM: Gemini
  via the `openai` Python SDK against `https://generativelanguage.googleapis.com/v1beta/openai/`
  (scenes.py:30), model `os.environ.get("P2R_SCENE_MODEL", "gemini-3.6-flash")` (scenes.py:247),
  key `GEMINI_API_KEY` (+ `GEMINI_API_KEY_BACKUP*` failover, scenes.py:139-154). Input per
  section: title, the `> ANIM:` brief (`sec.anim`), the fixed drawing-primitive API doc, a
  progressive-reveal doc, and every aligned sentence with its timestamp (read from
  `build/align/<stem>.json`). Output: a generated Python module `build/scenes/scene_<stem>.py`
  whose `states()` function returns `(name, cue_index, draw_fn[, opts])` tuples using only the
  injected `scenekit` API — not arbitrary code, a constrained DSL surface.
- **Critic ≈ `prompt2render/scenekit.py::audit()`** (scenekit.py:872-931) — **geometric/pixel, not a VLM
  call.** Checks: text-vs-text bbox overlap beyond a tolerance, off-frame text/elements against a
  12px margin, element-vs-element path-intersection collision (grouped by a `_p2r_el` tag every
  drawing primitive sets), tiny-text, and ink-fraction (too blank / too crowded). Every `Problem`
  carries a natural-language message with pixel coordinates — this text is what gets fed back to
  the LLM.
- **Render call ≈ `prompt2render/stills.py::load()`** (stills.py:39-53) — `importlib.util.spec_from_file_
  location` + `exec_module`, an **in-process dynamic import with no sandboxing**. The `k`
  (scenekit) module is injected as `mod.k = k` rather than a real `import`. Exceptions are caught
  and re-raised as `SystemExit` with a traceback so the retry loop can consume them, but nothing
  stops generated code from doing arbitrary I/O, imports, or subprocess calls. `render_many()`
  uses a `ProcessPoolExecutor` for FreeType thread-safety/CPU parallelism, **not** for security
  isolation. **This is a real gap against the task's "sandbox the Manim execution call; generated
  code is untrusted input" constraint** — flagged for Stage 3's `renderer_*` plugin to actually
  close, since it doesn't exist today.
- **Retry/repair ≈ `scenes.py generate()`'s attempt loop** (scenes.py:230-316): up to
  `retries+1` attempts (default 3 retries); each failure's audit-error text (truncated to last
  1500 chars) is appended verbatim as `feedback` for the next Gemini call. `RateLimitError` (429)
  triggers key rotation without consuming a retry. Purely single-loop, no router, no diagnosis —
  this is exactly what `repair_router` (Stage 4) replaces.
- **RAG/retrieval:** none. Confirmed by grepping `prompt2render/` for
  `embedding|vector.?store|retrieval|RAG|faiss|chroma|pinecone|similarity_search` — no real
  matches (only incidental substring hits on "paragraph").
- **Audio/narration:** `prompt2render/voice.py` (649 lines) — Kokoro ONNX TTS (`kokoro_onnx.Kokoro`),
  local/offline, sentence-by-sentence synthesis for sample-accurate boundaries; `own`
  (user-recorded) is the only other implemented backend, `edge` is not. `prompt2render/textseg.py` (389
  lines) is the single shared sentence/word/normalization implementation used by voice, align,
  and captions. `prompt2render/align.py` (570 lines) uses the ffmpeg-builtin whisper.cpp filter (no Python
  whisper package) plus `difflib`-based reconciliation against the known script, snapped to
  detected silence, with Kokoro's own exact synthesis cues taking precedence over ASR inside a
  sentence. `prompt2render/asrmodel.py` bootstraps the local whisper/VAD model files (explicit `prompt2render models`
  step, never mid-build). `prompt2render/captions.py` derives SRT/ASS from real word timings, not
  transcription — no drift on symbol-heavy sections.
- **Manim:** exactly one call site, `prompt2render/visuals.py::manim_scene()` (visuals.py:78-114) — shells
  out to the `manim` CLI on a **hand-authored** `.py` file supplied via
  `prompt2render manim <slug> <pyfile> <scene> <index>`. Opt-in only, never called from `scenes.py`,
  `stills.py`, or `cmd_build`. Deliberately never LLM-driven — the docstring reasons that Manim's
  API surface is too large to point a model at profitably compared to the constrained scenekit
  DSL. `manim` the package is commented out of `requirements.txt` by default.
- **`vendor/Code2Video`** — confirmed disconnected (§0). For completeness: it implements Outline
  (stage1) → Storyboard (stage2, with optional icon-asset fetching via `external_assets.py`) →
  Code (stage3, Manim `Scene` subclasses on a fixed 6×6 grid, `scope_refine.py`'s regex-classified
  repair loop) → Layout feedback (stage4, uploads rendered mp4 + reference grid PNG to a
  Gemini vision call) → Eval (stage5, offline AES scoring + an unrelated selective-unlearning
  eval prompt). Multi-provider LLM client (`gpt_request.py`): Gemini, Claude, Azure GPT-4o/4.1/
  GPT-5/o4-mini, all via `openai`-compatible calls.

---

## 4. Manim / Python / client-library pins

- **Manim:** `manim==0.21.0`, actively pinned (not commented out) in `requirements.txt` — drives
  both the `--manim` harness backend and the `prompt2render manim` escape hatch. `manimver.py` is
  the single source of truth for the target version; `P2R_MANIM_VERSION` overrides it (used to
  reproduce the 0.19.0 Code2Video comparison — see docs/MANIM_EXPERIMENT_PROTOCOL.md and
  docs/MANIM_0_21_MIGRATION.md).
- **Python version:** no pin found anywhere in the repo (no `python_requires`, no
  `.python-version`, nothing in `requirements.txt` or `setup.ps1`/`setup.sh` beyond invoking
  whatever `python`/`winget`-installed interpreter is on PATH).
- **LLM client:** `openai>=1.90` — this is the live client for `prompt2render scenes`, pointed at Gemini's
  OpenAI-compatible endpoint via `base_url`, not the `google-generativeai` package. No
  `google-generativeai` or `anthropic` package in `requirements.txt`.
- **ASR:** no Python whisper package — forced alignment uses ffmpeg's built-in whisper filter.
  `asrmodel.py` fetches GGML model files directly.
- **TTS:** `kokoro-onnx>=0.5.0`, `onnxruntime>=1.20`.
- **Rendering:** `matplotlib>=3.8`, `numpy>=2.0` (scenekit's actual renderer).
- **Web (currently deleted from disk, §9):** `fastapi>=0.115`, `uvicorn>=0.32`,
  `python-multipart>=0.0.9`, `Jinja2>=3.1`.
- **vendor/Code2Video** pins its own dependencies separately in
  `vendor/Code2Video/src/requirements.txt` (not installed into the main `.venv`); irrelevant to
  the live pipeline's pin set.

---

## 5. Plugin-role remapping for Stage 3 (informational — nothing built yet)

The task's target plugin list was written assuming the Manim/VLM architecture. Mapped against
what's actually live, so Stage 3 wraps real code instead of inventing fake wrappers:

| task's target plugin | maps to (live code) | notes |
|---|---|---|
| `planner_llm` | `scenes.py`'s per-section prompt construction (title + `sec.anim` brief + API docs) | same LLM call as `generator_code`, not a separate stage today — Stage 3 will need to decide whether to split it or keep it fused, since splitting changes behavior |
| `generator_code` | `scenes.py generate()`'s Gemini call → `scene_<stem>.py` | the actual "Coder" role, reduced to a constrained DSL, not arbitrary Manim |
| `verifier_spatial` / `verifier_semantic` / `evaluator_vlm` | `scenekit.py::audit()` | **geometric, not VLM** — wrapping this as `evaluator_vlm` without renaming would misrepresent it; recommend classifying it under `verifier_spatial` (or a new, honestly-named role) in Stage 3 rather than forcing the VLM label |
| `verifier_lifecycle` | nothing exists (§8) | true stub, no current behavior to preserve |
| `verifier_audio` | closest existing analogue is `qc.py`'s caption-drift gate (re-transcribes shipped audio, re-aligns, checks drift) | not per-scene, runs once on `out/final.mp4` |
| `chunker_scene` | `project.py::parse_script()`'s section splitting | not a separate stage currently, folded into script parsing |
| `renderer_manim` | `visuals.py::manim_scene()` | opt-in escape hatch only, not in the default graph, never LLM-driven — wrap as a disabled-by-default plugin |
| `retriever_manim_rag` | nothing exists | documented no-op stub |
| `repair_router` | `scenes.py generate()`'s inline attempt loop | this is exactly the ad-hoc logic Stage 4 formalizes |
| `feedback_hitl` | nothing exists | no human-in-the-loop gate found anywhere in `prompt2render/` |
| planner/coder for audio | `voice.py` + `align.py` + `textseg.py` | not LLM-driven at all — deterministic TTS/ASR pipeline, no planning stage |

Stage 3 should treat this table as the starting contract and flag any further mismatch rather
than silently reinterpreting, per the task's own standing instruction.

---

## 6. Test coverage

Stated plainly, not assumed: **there is exactly one real test file in the entire repository**,
`tools/test_layout_audit.py` (225 lines), and it is **untracked in git** (`git ls-files` doesn't
list it; `git status` shows it `??`). It tests only `scenekit.audit()`'s collision/overlap logic
via hand-built `bad_*`/`good_*` scene-drawing functions, auto-collected via `globals()`, checked
against expected pass/fail. No Manim, no LLM/API calls, no network access — pure offline unit
test of one function.

`git ls-files -- '*/tests/*'` returns nothing — no `tests/` package exists anywhere.
`git ls-files -- '*test*'` only matches `projects/burn-test/script.md` and
`projects/smoke-test/script.md`, which are project *content* directories named "test", not test
code.

**No automated tests exist for**: `align.py`, `voice.py`, `encode.py`, `finish.py`, `qc.py`,
`timeline.py`, `project.py` (script parsing), `captions.py`, `publish.py`, or the web dashboard.
Stage 1's golden baseline is the first real regression safety net most of this pipeline has ever
had.

---

## 7. Object-lifecycle state

Explicitly checked and confirmed **absent**. `project.py`'s `Section` dataclass holds only
parsed text/timing fields — no object concept. `timeline.py` works purely off a per-section
`manifest.json` of stills (kind/step/cue/png/anchor), keyed by `sec.stem`; nothing links a shape
or element created in one section to a later one. `scenekit.py` is a drawing-primitive library
plus the geometric auditor — grepping it and `scenes.py` for
`object|lifecycle|identity|persist|carry.*forward` turns up no real hits (only an unrelated type
annotation and prose about bit-carry visuals).

This matters because the task's Stage 2 `object_table` schema (`id`, `created_at_scene`,
`removed_at_scene`, `referenced_at`) assumes this kind of cross-scene tracking is meaningful
today. It isn't — each section renders independently. Building `object_table` correctly is net
new modeling work, not a wrapper around existing behavior; Stage 2 should design the schema (as
instructed) but Stage 3 has nothing to populate it from without new instrumentation in
`scenes.py`/`stills.py`, which is out of scope for a behavior-preserving wrap.

---

## 8. Web dashboard — a separate, likely-unintentional side issue (informational)

Not part of the pipeline's `build` chain and not required for the migration, but worth recording
since it surfaced during inventory: commit `276581d` ("Add prompt2render serve web dashboard...") added 20
files under `prompt2render/web/` (app.py, `draft.py`, `jobs.py`, `progress.py`, six `routes_*.py`,
`schemas.py`, `scriptio.py`, `status.py`, `templating.py`, static/templates). All 20 are
currently deleted from the working tree relative to `HEAD`. Per the user, this deletion is
**intentional** — the dashboard is being removed and is out of scope for this migration. Noted
here only so Stage 1's golden-baseline runner doesn't try to exercise `prompt2render serve`.

---

## 9. Working-tree state (resolved with the user, recorded for the record)

At inventory time, `git status` showed, beyond the `prompt2render/web/` deletion above:

- **Modified, uncommitted:** `README.md`, `prompt2render.py`, `prompt2render/align.py`, `prompt2render/assemble.py`,
  `prompt2render/cfg.py`, `prompt2render/encode.py`, `prompt2render/finish.py`, `prompt2render/qc.py`, `prompt2render/scenekit.py`,
  `prompt2render/scenes.py`, `prompt2render/stills.py`, `prompt2render/visuals.py`, `prompt2render/voice.py` — some diffs are large
  (e.g. `scenekit.py` +315/-0 net, `cfg.py` +188).
- **Deleted, uncommitted:** `.claude/scheduled_tasks.lock`; seven `projects/*/script.md` files
  (`addressing-modes`, `binary-search-v2`, `binary-search`, `burn-test`,
  `example-cache-mapping`, `smoke-test`, `twos-complement`, `verify-run`) — notably, the prior
  commit `cc33c11` is literally titled "Recover projects/*/script.md deleted by an external
  process," meaning this class of loss has happened before.
- **Untracked:** `prompt2render.zip`, `projects/fetch-decode-execute/`, `projects/hash-tables/`.

**Resolved:** per the user, the core-file edits and script.md deletions reflect current, working
state and should be snapshotted as-is for Stage 1's golden baseline — no commit, stash, or
restore performed as part of this inventory. The `prompt2render/web/` deletion is intentional and out of
scope.

---

## Summary — checklist for Stage 3's "reach-around → explicit context" work

**Closed out (2026-08-21).** The Stage 2-5 plan (see the plan file from that session) established
that the harness's scope — the 14 target plugin folders plus the added `renderer_stills/` — is the
generation/verification/repair loop only, not the whole `prompt2render build` chain. Rows below are marked
converted or explicitly out-of-scope accordingly; nothing was silently dropped.

- [x] `scenes.generate` → `scene_<stem>.py` + PNG/manifest/audit, reading `align/<stem>.json` —
      converted: `prompt2render/harness/plugins/generator_code/` (reads `scene_plan`+`narration`, writes
      `code_artifacts`) and `planner_audio/` (ingests the `align/<stem>.json` read into
      `narration`)
- [x] `stills.render_many` → same PNG/manifest/audit set, cache-gated on `is_current()` —
      converted: `prompt2render/harness/plugins/renderer_stills/` (writes `render_artifacts`, including the
      recorded audit); `verifier_spatial/` surfaces that audit as `check_results`
- [x] `qc.check`'s caption-drift gate → `out/qc.json`'s one row, reading `final.mp4` + align —
      converted: `prompt2render/harness/plugins/verifier_audio/`, with the whole-video-scope caveat recorded
      in its own docstring (it needs `out/final.mp4`, which nothing in this harness produces)
- [ ] `voice.build` → `audio_map.json`, `master.wav`/`master.m4a`, per-section
      `sentences.json`/`meta.json` — **out of scope for this harness**: no target plugin folder
      corresponds to it; `prompt2render.py`'s `cmd_voice` still calls it directly, unchanged
- [ ] `align.align` → per-section `align/<stem>.json` — **out of scope**, same reason; `planner_audio`
      only *reads* its output, it doesn't wrap the alignment stage itself
- [ ] `timeline.build` → `plan.json` — **out of scope**, no target plugin folder
- [ ] `encode.encode` → `clips/*.mp4` — **out of scope**, no target plugin folder
- [ ] `finish.finish` → `sections/*.mp4`, `out/final.mp4`, `out/captions.srt`,
      `out/thumb_source.png` — **out of scope**, no target plugin folder (and the reason
      `verifier_audio` above can only run against an already-finished project)
- [ ] `publish.build_packet` → `out/upload.md` — **out of scope**, no target plugin folder

The five "out of scope" rows all share one cause: the canonical Stage 2/3 brief's 14 target
folders describe the generate → render → verify → repair loop, with narration as an *input*
(`planner_audio`) rather than a stage of its own. `prompt2render.py`'s CLI keeps running
`voice`/`align`/`timeline`/`encode`/`finish`/`publish` exactly as it does today — this harness is
additive (`tools/harness_run.py`), not a replacement for that CLI (see the plan's
reconciliation #10).
