# fdx-studio

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

`fdx build <slug>` runs the whole chain in one go; every stage above is also
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

## Install (once)

### Windows (native)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

Installs Python, Git, ffmpeg, MiKTeX and Manim via winget, writes `.env`,
then fetches the local models (`fdx models --asr base.en --vad --kokoro` —
a few hundred MB, one time) and runs `fdx doctor`. Reopen PowerShell if it
reports things missing from PATH, then re-run — that is normal on first
install.

Everything here runs natively: Manim, ffmpeg, kokoro and the ffmpeg-builtin
whisper filter all support Windows; MiKTeX auto-installs LaTeX packages on
demand, which is actually smoother than TeX Live. MiKTeX/Manim are only
needed for the `fdx manim` hand-authored escape hatch — the main pipeline
(`fdx scenes`) doesn't touch LaTeX at all.

Activate before each session:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
unzip fdx-studio.zip && cd fdx-studio
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
```

Then put your `GEMINI_API_KEY` in `.env` — it's the only key the current
pipeline needs (`fdx scenes` storyboards against it; everything else is
local and free). `fdx doctor` runs at the end of setup and tells you what,
if anything, is still missing.

Verify with a real section, at whatever cost you're comfortable with:

```bash
python fdx.py new smoke-test
python fdx.py voice smoke-test    # local TTS, no API cost
python fdx.py align smoke-test    # local ASR, no API cost
python fdx.py scenes smoke-test --section 1   # one Gemini call
python fdx.py check smoke-test
```

---

## Making a video

```bash
python fdx.py new booths-algorithm
```

**1. Write `projects/booths-algorithm/script.md`.** This is the real work
and takes an hour. Format:

```markdown
## 3 - The key idea
> ANIM: the central visual — this is the frame people screenshot

What you actually say, in your own words.
```

`> ANIM:` is the brief `fdx scenes` storyboards against a fixed drawing API
(`fdx/scenekit.py`) — a small enough surface that a layout mistake is always
something the automated critic can name and hand back for a retry, rather
than something you discover after rendering. Everything else is spoken and
captioned. Target 1100–1700 words for 8–12 minutes.

**2. Run the chain.**

```bash
python fdx.py build booths-algorithm
```

This is `voice -> align -> scenes -> stills -> plan -> encode -> finish ->
check` in one go. Each stage is cached, so re-running after a fix only
redoes what changed. Worth running as stages while you're getting a feel
for it:

```bash
python fdx.py voice booths-algorithm         # synthesises with kokoro by default;
                                              # --backend own uses projects/.../audio/NN.wav
                                              # if you recorded your own narration
python fdx.py align booths-algorithm         # word-level timing
python fdx.py scenes booths-algorithm        # ask the model to storyboard
python fdx.py stills booths-algorithm        # render + audit the PNGs
python fdx.py plan booths-algorithm          # decide when each still appears
python fdx.py encode booths-algorithm --all --jobs 2  # one clip per still, 2 at a time
python fdx.py finish booths-algorithm        # concat, mux, caption, chapter
python fdx.py check booths-algorithm --strict
```

**3. Fix a bad scene, if `fdx check` flags one.** A rejected scene module
lives at `build/scenes/scene_NN.py` — it's plain matplotlib calls through
`scenekit`, not generated Manim, so nudging a `k.array(...)` call is the
whole fix:

```bash
rm projects/booths-algorithm/build/scenes/scene_03.py
python fdx.py scenes booths-algorithm --section 3   # regenerate just that one
```

Not ready to storyboard yet? Either works:

```bash
python fdx.py placeholders booths-algorithm       # title cards
python fdx.py import booths-algorithm ~/clips/    # clips from anywhere
```

**4. Publish.** `fdx finish` already wrote the packet; if you re-narrate or
re-cut after that, refresh it:

```bash
python fdx.py publish booths-algorithm
```

Produces `out/final.mp4`, `out/captions.srt`, `out/thumb_source.png`, and
`out/upload.md` with a description, chapters and a pre-upload checklist.
Work through that checklist — it is short and it is the part that protects
the channel.

---

## Web dashboard

```bash
python fdx.py serve             # http://127.0.0.1:8787, localhost-only by default
```

A local, single-user dashboard over the same pipeline — nothing here that
`python fdx.py <stage>` doesn't already do; it just makes long stages
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
  stills and re-runs `fdx scenes --section N`.
- **Upload** — record-your-own-narration per section (for `--backend own`),
  or point `fdx import` at a folder of pre-made clips.
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
inserted by fdx rather than the TTS engine's own batching, so every sentence
boundary is exact by construction — sample-accurate, not estimated. `fdx
align` then force-aligns word-level timing on top of that with the
ffmpeg-builtin whisper filter, but only ever *refines inside* a sentence:
where whisper disagrees with the exact synthesis boundary, synthesis wins.

`fdx plan` uses those word timings to cut each still to the frame — the
picture changes exactly when the relevant word is spoken (pulled `lead_ms`
earlier so cuts read as edited, not generated), not padded to fit a fixed
per-section duration. `fdx check`'s decisive gate re-runs alignment against
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

## Cost and cadence

- API spend is just `fdx scenes` — one Gemini call per section, a few more
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
fdx.py                 CLI
fdx/cfg.py              paths, env, ffprobe/ffmpeg helpers, constants
fdx/project.py          scaffolding + script.md parser
fdx/voice.py            kokoro TTS, sentence-exact cues, programme mastering
fdx/textseg.py          sentence/word segmentation feeding voice + align
fdx/align.py            force-alignment (ffmpeg whisper filter) + hardening
fdx/asrmodel.py         fetches/validates the local whisper + VAD models
fdx/scenes.py           asks the model to storyboard against scenekit
fdx/scenekit.py         the drawing primitives + the layout-audit critic
fdx/stills.py           executes a scene module to PNG stills
fdx/timeline.py         when every still appears, fit to the frame
fdx/encode.py           one clip per still, dissolve baked into the head, --jobs parallel
fdx/finish.py           concat, mux, caption, chapter — the final assembly
fdx/captions.py         SRT/ASS generation from the alignment
fdx/qc.py               the quality gates behind `fdx check`, caption drift parallelized
fdx/publish.py          upload packet (description, chapters, checklist)
fdx/doctor.py           environment check
fdx/visuals.py          import/placeholder/manim escape hatches
fdx/assemble.py         legacy sync path, for `fdx import`ed clips only
fdx/web/                the `fdx serve` dashboard — FastAPI + SSE over the same stages
docs/RETIRED.md         why the old Code2Video path was replaced, and by what
topics/backlog.yaml     the 30-video queue
projects/<slug>/        script.md, sections/, audio/, build/, out/
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `fdx doctor` reports a missing model | `python fdx.py models --asr base.en --vad --kokoro` |
| `latex failed` in `fdx manim` | install `texlive-latex-extra texlive-science` (or MiKTeX on Windows) — the main `fdx scenes` path never touches LaTeX |
| Windows: `manim` not found | activate the venv: `.\.venv\Scripts\Activate.ps1` |
| Windows: LaTeX prompt pops up | MiKTeX asking to install a package — tick "always", it stops asking |
| Windows: captions look wrong | font fallback; `CAPTION_FONT` in `fdx/cfg.py` |
| `fdx scenes` keeps rejecting a section | open `build/scenes/scene_NN.py` — the audit error in the terminal names the exact overlap or off-frame text; fix the `k.` call or delete the file and regenerate |
| `fdx check` fails "caption drift" | a section's audio was replaced after `fdx align` ran — re-run `align` then `plan`/`encode --all`/`finish` |
| `fdx finish` refuses to concat | clips were encoded with mixed profiles (a `--preview` pass mixed with a final one) — delete `build/clips` and `fdx encode --all` again |
| Rate-limited on `fdx scenes` | Gemini's free tier caps requests/day per model — add a `GEMINI_API_KEY_BACKUP*` key in `.env` for automatic failover, or wait for the quota to reset |
| `fdx encode --jobs N` isn't faster | this machine may already be CPU-bound (other processes, `-preset veryfast` already threading per call) — try `--jobs 1` and compare wall-clock before assuming higher is better |
| `fdx serve` says "a job is already running" | only one pipeline job runs at a time, server-wide, by design (see **Web dashboard**) — wait for it to finish or cancel it from the Pipeline page |
