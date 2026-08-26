# Prompt2Render

![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![Status](https://img.shields.io/badge/status-active--development-yellow)
![Local--first](https://img.shields.io/badge/pipeline-local--first%20%2B%201%20API-informational)

End-to-end pipeline for narrated, code-animated explainer videos, built to
frame accuracy.

A model storyboards each section against a small, fixed drawing API
(`scenekit`) rather than writing arbitrary animation code; a layout critic
reads the rendered frame's own pixel geometry and rejects overlaps and
off-frame text before you ever see them; narration is synthesised sentence by
sentence with sample-exact timing, then force-aligned to word level; and the
final cut is timed off real speech, not padded to fit afterwards:

```
script.md ──> voice ──> align ──> scenes ──> stills ──> plan ──> encode ──> finish ──> check
              (TTS,      (word-    (model      (PNG        (frame-   (one clip   (concat,   (the gates
              mastered)  level     storyboard  frames,     exact     per still,  mux,       that say
                         timing)   vs scenekit) audited)    timing)   dissolve)   caption)   shippable)
```

`prompt2render build <slug>` runs the whole chain in one go; every stage above is also
its own command, because each one is worth inspecting and the expensive ones
are cached. See **Layout** below for what each stage does.

The script is written by you. That is deliberate — it is both the quality
ceiling of the video and the thing that keeps the channel clear of
YouTube's inauthentic-content rule.

> An earlier version of this pipeline drove
> [Code2Video](https://github.com/showlab/Code2Video) to render Manim clips,
> then force-fit them to narration by holding the last frame. That path is
> retired — see `docs/RETIRED.md` for why, and what replaced it.

---

## Quickstart

Already installed (see **Install** below)? This is the whole loop, start to
finish, on a different topic than the walkthrough further down:

```bash
python prompt2render.py new twos-complement
# write projects/twos-complement/script.md — this is the one manual step
python prompt2render.py build twos-complement
python prompt2render.py check twos-complement --strict
```

`build` chains `voice -> align -> scenes -> stills -> plan -> encode -> finish
-> check` for you; `out/final.mp4` and `out/upload.md` are what you get at
the end. See **Making a video** for the stage-by-stage version and what to
do when `check` rejects a scene.

---

## Install (once)

### Windows (native)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

Installs Python, Git, ffmpeg, MiKTeX and Manim via winget, writes `.env`,
then fetches the local models (`prompt2render models --asr base.en --vad --kokoro` —
a few hundred MB, one time) and runs `prompt2render doctor`. Reopen PowerShell if it
reports things missing from PATH, then re-run — that is normal on first
install.

Everything here runs natively: Manim, ffmpeg, kokoro and the ffmpeg-builtin
whisper filter all support Windows; MiKTeX auto-installs LaTeX packages on
demand, which is actually smoother than TeX Live.

Manim drives the `--manim` scene backend and the `prompt2render manim`
hand-authored escape hatch. LaTeX is needed by both whenever a scene uses
`MathTex`/`Tex`, which generated educational scenes do routinely — around a
third of the scenes in `projects/` contain an equation. Only the default
matplotlib scene-kit backend (`prompt2render scenes` without `--manim`) is
genuinely LaTeX-free.

Activate before each session:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
unzip prompt2render.zip && cd prompt2render
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
```

Then put your `GEMINI_API_KEY` in `.env` — it's the only key the current
pipeline needs (`prompt2render scenes` storyboards against it; everything else is
local and free). `prompt2render doctor` runs at the end of setup and tells you what,
if anything, is still missing.

Verify with a real section, at whatever cost you're comfortable with:

```bash
python prompt2render.py new smoke-test
python prompt2render.py voice smoke-test    # local TTS, no API cost
python prompt2render.py align smoke-test    # local ASR, no API cost
python prompt2render.py scenes smoke-test --section 1   # one Gemini call
python prompt2render.py check smoke-test
```

---

## Making a video

```bash
python prompt2render.py new booths-algorithm
```

The scaffold defaults to a 6-section, ~10-minute outline (hook, 4 body
beats, recap). Scale it with `--minutes` or pick an exact count with
`--sections`:

```bash
python prompt2render.py new booths-algorithm --minutes 5    # shorter -> fewer body beats
python prompt2render.py new booths-algorithm --sections 9   # exact count
```

Section titles beyond the first four body beats are generic (`Body beat N`)
— it's a starting outline to rename, not a topic-aware one. Add, remove or
retitle sections in `script.md` freely; nothing downstream cares how many
there are.

Want the outline itself tailored to the topic instead — a real title, a
distinct `topic:` summary, and section titles/ANIM briefs specific to what
you're actually explaining, not the generic arc above? Add `--ai` (needs
`GEMINI_API_KEY`):

```bash
python prompt2render.py new merge-sort --ai --minutes 8
```

```
---
title: Merge Sort: Splitting Your Way to O(n log n)
topic: merge sort - divide and conquer, the merge step, O(n log n) complexity, stability
audience: undergraduate computer science
---
```

`--ai` still leaves every section's narration as a `"Narration."` placeholder
— it decides structure and titling, not what gets said; combine with
`prompt2render draft` (below) or your own hand for the words. Pass `--title`
to keep your own title verbatim while still getting an AI-written `topic:`
line and section structure; omit it and the model proposes its own title too.
`--sections N` forces an exact count the same way it does without `--ai`.

**1. Write `projects/booths-algorithm/script.md`.** This is the real work
and takes an hour. Format:

```markdown
## 3 - The key idea
> ANIM: the central visual — this is the frame people screenshot

What you actually say, in your own words.
```

`> ANIM:` is the brief `prompt2render scenes` storyboards against a fixed drawing API
(`prompt2render/scenekit.py`) — a small enough surface that a layout mistake is always
something the automated critic can name and hand back for a retry, rather
than something you discover after rendering. The critic groups the artists by
the `k.` call that drew them and compares the real geometry — boxes, circles,
panels, rules — not just where the letters landed, so a dial drawn through an
array is caught even when the digits happen to miss each other. Its own test
suite is `python tools/test_layout_audit.py`: known-bad frames that must be
caught, and deliberately awkward good ones that must not be, because a critic
that fails a clean frame spends the model's retries teaching it to avoid a
layout that was fine. Everything else is spoken and
captioned. Target 1100–1700 words for 8–12 minutes.

Don't want a blank page? `prompt2render draft <slug>` asks Gemini for a first
pass at any section still holding the `new` placeholder text, and writes it
straight into `script.md`:

```bash
python prompt2render.py draft booths-algorithm            # fills in unwritten sections only
python prompt2render.py draft booths-algorithm --force    # redrafts every section, incl. ones you edited
```

It's a starting point, not step 1 of an unattended pipeline — read it, fix
what's wrong, put it in your own voice, *then* build. The rule from the top
of this section still applies to whatever's in `script.md` when you run
`build`, drafted or not: it's what keeps the channel clear of the
inauthentic-content rule, and disclosure in YouTube Studio is on you if you
ship AI-drafted narration close to as-is.

Want that pause removed anyway — a topic in, a checked `final.mp4` out, no
manual read in between? `prompt2render auto` chains `new --ai -> draft ->
build` into one call:

```bash
python prompt2render.py auto booths-algorithm --minutes 8
```

If the project doesn't exist yet it outlines and drafts one from scratch
(same as `new --ai` + `draft`, unattended); if it already exists, `auto`
drafts only whatever's still a placeholder and builds from there —
`--redraft` forces every section, including ones you wrote by hand. It takes
every flag `build` does (`--motion`, `--jobs`, `--strict`, ...). This is the
one command that ships without a human ever reading the narration — it
prints the same disclosure reminder as `draft` before it starts, but nothing
stops it. Prefer `new`/`draft`/`build` as three separate steps unless you
specifically want that unattended.

**2. Run the chain.**

```bash
python prompt2render.py build booths-algorithm
```

This is `voice -> align -> scenes -> stills -> plan -> encode -> finish ->
check` in one go. Each stage is cached, so re-running after a fix only
redoes what changed. Worth running as stages while you're getting a feel
for it:

```bash
python prompt2render.py voice booths-algorithm         # synthesises with kokoro by default;
                                              # --backend own uses projects/.../audio/NN.wav
                                              # if you recorded your own narration
python prompt2render.py voices                         # list kokoro voice names for --voice
python prompt2render.py align booths-algorithm         # word-level timing
python prompt2render.py scenes booths-algorithm        # ask the model to storyboard
python prompt2render.py stills booths-algorithm        # render + audit the PNGs
python prompt2render.py plan booths-algorithm          # decide when each still appears
python prompt2render.py encode booths-algorithm --all --jobs 2  # one clip per still, 2 at a time
python prompt2render.py finish booths-algorithm        # concat, mux, caption, chapter
python prompt2render.py check booths-algorithm --strict
```

`prompt2render stills` normally prints "stills current, skipping" for every section and
exits. That is correct: `prompt2render scenes` judges a generated module by rendering
it, so by the time it accepts one the frames are already written. The stage
still exists for the case where you hand-edit a `scene_NN.py` — it notices and
re-renders that section only. `--force` re-renders everything regardless.

**3. Fix a bad scene, if `prompt2render check` flags one.** A rejected scene module
lives at `build/scenes/scene_NN.py` — it's plain matplotlib calls through
`scenekit`, not generated Manim, so nudging a `k.array(...)` call is the
whole fix:

```bash
rm projects/booths-algorithm/build/scenes/scene_03.py
python prompt2render.py scenes booths-algorithm --section 3   # regenerate just that one
```

Not ready to storyboard yet? Either works:

```bash
python prompt2render.py placeholders booths-algorithm       # title cards
python prompt2render.py import booths-algorithm ~/clips/    # clips from anywhere
```

**4. Publish.** `prompt2render finish` already wrote the packet; if you re-narrate or
re-cut after that, refresh it:

```bash
python prompt2render.py publish booths-algorithm
```

Produces `out/final.mp4`, `out/captions.srt`, `out/thumb_source.png`, and
`out/upload.md` with a description, chapters and a pre-upload checklist.
Work through that checklist — it is short and it is the part that protects
the channel.

---

## Web dashboard (not built yet)

**`prompt2render serve` currently exits with `ModuleNotFoundError: No module named
'prompt2render.web'` — the `prompt2render/web/` package described below does not exist
in this repository yet.** Everything past this line is the intended design,
kept because it's a complete spec for whoever builds it, not a description
of working software. Use the CLI stages directly (`python prompt2render.py
<stage> <slug>`) until this lands.

```bash
python prompt2render.py serve             # http://127.0.0.1:8787, localhost-only by default
```

A local, single-user dashboard over the same pipeline — nothing here that
`python prompt2render.py <stage>` doesn't already do; it just makes long stages
watchable instead of something you poll from a terminal. Each stage runs
as its own subprocess, exactly like the CLI, so a stage's own live
`cfg.say()` output streams to the page over Server-Sent Events as it runs,
with a progress bar computed from files already on disk (never guessed).

- **Script** — an editor for `script.md` (title/topic/audience, per-section
  title/ANIM/narration, live word-count and pacing feedback). A **Draft
  with AI** button can prefill a rough first pass via `GEMINI_API_KEY`, but
  it only ever fills the form in your browser — nothing is written to disk
  until you hit Save. This project's own rule stands: the script is
  written by you.
- **Pipeline** — one button per stage plus **Build all**, with the live
  log and progress bar described above.
- **Scenes** — a thumbnail gallery per section from each `manifest.json`,
  with a **Regenerate section** action that clears the old storyboard and
  stills and re-runs `prompt2render scenes --section N`.
- **Upload** — record-your-own-narration per section (for `--backend own`),
  or point `prompt2render import` at a folder of pre-made clips.
- **Review** — `out/final.mp4`, the `out/qc.json` gate table, and the
  `out/upload.md` packet.

Only one job runs at a time, server-wide — this pipeline is CPU-heavy
enough on a modest machine that two stages fighting for the same cores
would undo the `--jobs` parallelism below rather than add to it.

`--host 0.0.0.0` exposes the dashboard (and anything it can trigger,
including Gemini calls) to your LAN with no authentication — leave it at
the localhost-only default unless you specifically want that.

---

## How sync works

The narration is synthesised **sentence by sentence** with the pauses
inserted by prompt2render rather than the TTS engine's own batching, so every sentence
boundary is exact by construction — sample-accurate, not estimated. `prompt2render
align` then force-aligns word-level timing on top of that with the
ffmpeg-builtin whisper filter, but only ever *refines inside* a sentence:
where whisper disagrees with the exact synthesis boundary, synthesis wins.

`prompt2render plan` uses those word timings to cut each still to the frame — the
picture changes exactly when the relevant word is spoken (pulled `lead_ms`
earlier so cuts read as edited, not generated), not padded to fit a fixed
per-section duration. `prompt2render check`'s decisive gate re-runs alignment against
the **shipped** audio and captions independently, so drift is caught rather
than assumed away.

Captions come straight from `script.md`, not from transcription, so there
is no drift on symbol-heavy sections.

Audio is mastered once for the whole programme (not per section, which
would flatten the dynamics) to −14 LUFS, YouTube's target, with a static
gain plus a lookahead peak limiter — not `loudnorm`'s own dynamic mode,
which rides the gain and undoes the pacing the pauses were inserted to
create.

---

## Where the time goes

Every stage is cached, so the number that matters is a *cold* build. Roughly,
in descending order:

| Stage | What dominates | Knob |
|---|---|---|
| `align` | one whisper pass over the whole programme | `--asr-jobs N` |
| `encode` | one process per clip — NVENC + `--jobs 3` automatically where available, libx264 + `--jobs 1` otherwise | `--jobs N` |
| `voice` | kokoro inference, sentence by sentence | `$P2R_VOICE_JOBS`, `$P2R_TTS_THREADS` |
| `scenes` | waiting on Gemini | `--jobs N` (default 3) |
| `check` | re-transcribing each section to verify sync | `$P2R_QC_JOBS` |
| `stills` | matplotlib | usually skipped; `--jobs N` |

Two of those defaults are deliberately conservative, because raising them
trades something real:

**`--asr-jobs`** splits the programme and transcribes the pieces at once.
The cuts land on section joins, which are silent by construction — voice.py
puts a paragraph pause there — so no word is ever split. What you give up is
whisper's context across a join, which can move a word timing by a few
milliseconds, and every cut in the video is timed off these numbers. Default
1. On a machine with spare cores, `--asr-jobs 4` is close to four times
faster and the drift gate in `prompt2render check` will tell you honestly if it cost
you anything. Separately, `align` no longer feeds ffmpeg's whisper filter its
own `vad_model=` option — measured at roughly a 12x wall-time cost for no
change in reconciliation confidence; see `docs/OPTIMIZATION.md` for the
experiment log.

**`encode --jobs`** cannot change a byte of any clip — each one is an
independent ffmpeg process. `cfg.default_encode_jobs()` already picks 3 on a
machine with a working NVENC encoder (a fixed-function chip; a couple of
clips in flight lets CPU-side decode/filter for clip N+1 overlap the GPU
actually encoding clip N) and 1 on CPU-only libx264, where more jobs just
means more processes contending for the cores x264 already threads
internally. Measured on a 1080p clip on the CPU path: ~27 ms per frame of
encoding, against ~0.46 s of fixed cost per call (spawn, decode the PNG,
initialise the filter and encoder) — on a five-second clip that fixed part
is about a tenth, and it is the only part a second job can recover there.
Pass `--jobs` explicitly to override either default; time it before
believing anything else.

**`$P2R_VOICE_JOBS`** synthesises several sentences at once, each in its own
process (not a thread — kokoro's tokenizer binds espeak-ng in-process via
ctypes, with no documented thread-safety guarantee, so this sidesteps that
question rather than gambling on it). Verified bit-identical output against
serial synthesis at every job count tested. Default 1: each worker pays
kokoro's own ~2s model-load cost independently, which eats into the win on
a short section — measured +18% faster on a realistic 15-sentence section
at `$P2R_VOICE_JOBS=3`, barely anything on a 5-sentence one. Worth setting
on a longer section; time it on yours before assuming it helps.

The rest is free and on by default: the layout audit is recorded when the
stills are drawn rather than recomputed by `prompt2render check`, the frames are
written from the rasterisation the audit already did instead of being drawn a
second time, and `prompt2render check`'s six full decodes of `final.mp4` are now one
audio pass and one video pass, run at the same time.

`P2R_PNG_EXACT=1` restores matplotlib's own PNG writer if you want the stills
byte-for-byte as they used to be; the frames are pixel-identical either way,
which is all ffmpeg reads.

## Cost and cadence

- API spend is just `prompt2render scenes` — one Gemini call per section, a few more
  on a layout-audit retry. Cents per video, not dollars; everything else
  (voice, align, encode) runs locally for free.
- ~15 min of generation, plus your script and any scene-fixing time.
- **2–3 videos per week.** Not one per day. Daily templated output is the
  exact pattern the inauthentic-content policy exists to catch, and it is
  also more than you can sustain alongside a teaching load.

`topics/backlog.yaml` holds the 30-topic queue with a status field.

---

## Layout

```
prompt2render.py                 CLI
prompt2render/cfg.py              paths, env, ffprobe/ffmpeg helpers, constants
prompt2render/project.py          scaffolding + script.md parser
prompt2render/voice.py            kokoro TTS, sentence-exact cues, programme mastering
prompt2render/textseg.py          sentence/word segmentation feeding voice + align
prompt2render/align.py            force-alignment (ffmpeg whisper filter) + hardening
prompt2render/asrmodel.py         fetches/validates the local whisper + VAD models
prompt2render/scenes.py           asks the model to storyboard against scenekit
prompt2render/scenekit.py         the drawing primitives + the layout-audit critic
prompt2render/stills.py           executes a scene module to PNG stills
prompt2render/timeline.py         when every still appears, fit to the frame
prompt2render/encode.py           one clip per still, dissolve baked into the head, --jobs parallel
prompt2render/finish.py           concat, mux, caption, chapter — the final assembly
prompt2render/captions.py         SRT/ASS generation from the alignment
prompt2render/qc.py               the quality gates behind `prompt2render check`, caption drift parallelized
prompt2render/publish.py          upload packet (description, chapters, checklist)
prompt2render/doctor.py           environment check
prompt2render/manimver.py         the one place that knows which Manim we target
prompt2render/manim_contract.py   the shared Manim generation contract + safe layout kit
prompt2render/manim_smoke.py      the `doctor --render-test` render check
prompt2render/assets/manim_smoke.py  the scenes that check renders
prompt2render/visuals.py          import/placeholder/manim escape hatches
prompt2render/assemble.py         legacy sync path, for `prompt2render import`ed clips only
prompt2render/web/                the `prompt2render serve` dashboard — FastAPI + SSE over the same stages
prompt2render/harness/            the Prompt2Render research/eval harness — see docs/HARNESS.md
docs/RETIRED.md         why the old Code2Video path was replaced, and by what
docs/HARNESS.md         how to use the Prompt2Render harness (tools/harness_run.py etc.)
topics/backlog.yaml     the 30-video queue
projects/<slug>/        script.md, sections/, audio/, build/, out/
```

## Manim

Supported version: **Manim Community 0.21.0**, pinned in `requirements.txt`.

```bash
pip install "manim==0.21.0"
```

`prompt2render/manimver.py` is the single source of truth. Every consumer
derives from it: the dependency pin, the generator prompts, the static
verifier's messages, and a hard guard at both render entry points. `doctor`
only *warns* about a version mismatch — Manim is optional and the default
stills backend never touches it — but a run that has actually selected the
Manim backend refuses to render against a version it does not target, so
`--manim` can never silently run on the wrong Manim.

Check it:

```bash
python prompt2render.py doctor                 # version + API probe, no render
python prompt2render.py doctor --render-test   # renders a real scene and ffprobes it
```

The render test is the one thing in the repo that proves Manim actually
works end to end: it renders `prompt2render/assets/manim_smoke.py` and
asserts the output exists, is non-trivially sized, is readable by ffprobe,
is exactly 1920x1080 and reports exactly 30/1 fps. A render that silently
came back at 1080p60 would pass an exit-code check and then desynchronise
every section against the master audio.

### Running an older Manim on purpose

`docs/MANIM_EXPERIMENT_PROTOCOL.md` pins 0.19.0 for the Code2Video
comparison, because changing Manim mid-experiment introduces a version
confound. Declare the version the run targets:

```bash
pip install "manim==0.19.0"
P2R_MANIM_VERSION=0.19.0 python prompt2render.py build <slug> --harness --manim
```

That makes the whole system self-consistent again — doctor stops warning,
the generator prompts say 0.19.0, the validator's messages say 0.19.0, and
the render guard accepts it. It is a way to *declare* a target, not to
silence a mismatch: a mismatch against the declared target still fails.

### 0.21 compatibility notes

- **`Code`** — colours now come from Pygments. Use
  `Code(code_string=..., language=..., add_line_numbers=True,
  formatter_style="monokai")`. A foreground colour passed through
  `paragraph_config` is **silently ignored** in 0.21 rather than rejected, so
  the static verifier flags it; nothing downstream could detect it, because
  the render succeeds and simply looks wrong. `background_config={"fill_color":
  ...}` still overrides the background.
- **`MathTex`/`Tex`** — unchanged in use, and still the supported maths path.
  0.20 rewrote substring splitting, so a scene that indexes into a `MathTex`
  or relies on `{{ ... }}` grouping is worth re-checking visually. LaTeX
  (plus `dvisvgm`) remains a hard requirement for these.
- **`Text`** — 0.21 raises when a ligature-aware font collapses an ASCII
  digraph into one glyph, where 0.19 silently mis-indexed. Generated code is
  normalised automatically (`->` becomes `→` inside `Text` literals); in
  hand-written scenes, write the Unicode glyph or pass
  `disable_ligatures=True`.
- **Typst** — 0.21 adds `Typst`/`TypstMath` as an optional extra
  (`pip install "manim[typst]"`). Prompt2Render does **not** use it and does
  not require it; `doctor` reports it as optional either way.
- **Caching** — 0.21 changed how scene cache keys hash numpy arrays, so
  caches written by 0.19 are not comparable. Both render entry points pass
  `--disable_caching`; if you have old `media/` or `build/manim/videos`
  trees from a 0.19 run, delete them.

### Text that fits the frame

Generated educational scenes overflow the frame more than they do anything
else wrong, so the fix is structural rather than advisory.
`prompt2render/manim_contract.py` holds one canonical layout block that every
generated scene starts with. It derives its bounds from
`config.frame_width`/`frame_height`, splits the safe area into title /
content / caption bands that cannot overlap, and exposes
`title_text`, `caption`, `fit_text`, `fit_mobject` and `place_content`, each
of which caps *both* width and height. `tests/test_manim_contract.py`
executes that block against the installed Manim and asserts the guarantee
holds for adversarial input — that is how the bands got fixed when a
two-line title turned out to overflow the top.

Text is bounded, not shrunk globally: `fit_text` wraps first, then steps the
font size down proportionally, and only scales as a last resort.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `prompt2render doctor` reports a missing model | `python prompt2render.py models --asr base.en --vad --kokoro` |
| `latex failed` in `prompt2render manim` | install `texlive-latex-extra texlive-science` (or MiKTeX on Windows) — needed for any scene using `MathTex`/`Tex` |
| Windows: `manim` not found | activate the venv: `.\.venv\Scripts\Activate.ps1` |
| `manim <version> is installed but this build targets 0.21.0` | `pip install "manim==0.21.0"`. To keep an older Manim on purpose, declare it: `P2R_MANIM_VERSION=0.19.0` |
| `doctor` says the Manim package and the CLI disagree | the venv is not active, or a second Manim is on PATH — the render path shells out to the `manim` executable, so both must match |
| A `Code(...)` scene renders in the wrong colours | Manim 0.21 takes syntax colours from Pygments. Use `formatter_style="<style>"`; a colour in `paragraph_config` is ignored |
| `Text ... rendered fewer glyph(s)` | a ligature font collapsed an ASCII digraph. Write `→` / `≤` / `≠` instead of `->` / `<=` / `!=`, or pass `disable_ligatures=True` |
| A generated scene's text runs off the frame | build text through the safe-layout helpers (`title_text`, `caption`, `fit_text`, `fit_mobject`) — see `prompt2render/manim_contract.py` |
| Windows: LaTeX prompt pops up | MiKTeX asking to install a package — tick "always", it stops asking |
| Windows: captions look wrong | font fallback; `CAPTION_FONT` in `prompt2render/cfg.py` |
| `prompt2render scenes` keeps rejecting a section | open `build/scenes/scene_NN.py` — the audit error in the terminal names the exact overlap or off-frame text; fix the `k.` call or delete the file and regenerate |
| `prompt2render check` fails "caption drift" | a section's audio was replaced after `prompt2render align` ran — re-run `align` then `plan`/`encode --all`/`finish` |
| `prompt2render finish` refuses to concat | clips were encoded with mixed profiles (a `--preview` pass mixed with a final one) — delete `build/clips` and `prompt2render encode --all` again |
| Rate-limited on `prompt2render scenes` | Gemini's free tier caps requests/day per model — add a `GEMINI_API_KEY_BACKUP*` key in `.env` for automatic failover, or wait for the quota to reset |
| `prompt2render encode --jobs N` isn't faster | this machine may already be CPU-bound (other processes, `-preset veryfast` already threading per call) — try `--jobs 1` and compare wall-clock before assuming higher is better. See **Where the time goes** for the measured ceiling |
| `prompt2render stills` says "current, skipping" | expected — `prompt2render scenes` already rendered them. Edit the scene module and it re-renders that section; `--force` does the lot |
| `prompt2render scenes` returns 429s it didn't before | sections are storyboarded three at a time now, which meters against the free tier's per-minute cap — `--jobs 1` restores the old one-at-a-time pace |
| `prompt2render serve` says "a job is already running" | only one pipeline job runs at a time, server-wide, by design (see **Web dashboard**) — wait for it to finish or cancel it from the Pipeline page |
| `prompt2render animate` exits immediately | retired — it drove the old Manim/Code2Video path. Use `prompt2render scenes` instead; see `docs/RETIRED.md` |
