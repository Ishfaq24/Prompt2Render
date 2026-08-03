# fdx-studio

End-to-end pipeline for narrated, code-animated explainer videos.

Code2Video makes silent ~2-minute Manim clips. YouTube pays for narrated
8–12 minute videos. This closes that gap:

```
script.md ──> Code2Video ──> sections/*.mp4  ─┐
    │                                          ├──> sync ──> concat ──> final.mp4
    └───────> narration ──> audio/*.m4a  ──────┘              + captions.srt
                                                              + upload.md
```

The script is written by you. That is deliberate — it is both the quality
ceiling of the video and the thing that keeps the channel clear of
YouTube's inauthentic-content rule.

---

## Install (once)

### Windows (native)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

Installs Python, Git, ffmpeg, MiKTeX and Manim via winget, clones
Code2Video, writes `.env`. Reopen PowerShell if it reports things missing
from PATH, then re-run — that is normal on first install.

Everything here runs natively. Manim, ffmpeg and edge-tts all support
Windows; MiKTeX auto-installs LaTeX packages on demand, which is actually
smoother than TeX Live. The one Windows-specific dependency is **Git for
Windows**, because Code2Video ships `.sh` entrypoints and fdx runs them
through the `bash.exe` that Git installs.

Activate before each session:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS / WSL2

```bash
unzip fdx-studio.zip && cd fdx-studio
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
```

Then fill in **two** places (Code2Video reads its own config, not `.env`):

1. `fdx-studio/.env` → `CODE2VIDEO_DIR`, TTS voice
2. `Code2Video/src/api_config.json` → `ANTHROPIC_API_KEY` (Coder),
   `GEMINI_API_KEY` (Critic), `ICONFINDER_API_KEY` (icons)

Verify:

```bash
source .venv/bin/activate
python fdx.py new smoke-test
python fdx.py placeholders smoke-test   # title cards, no API cost
python fdx.py assemble smoke-test --tts
```

If `out/final.mp4` plays with voice and captions, the chain is sound and
only Code2Video remains to configure.

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

`> ANIM:` lines go to Code2Video. Everything else is spoken and captioned.
Target 1100–1700 words for 8–12 minutes.

**2. Animate.**

```bash
python fdx.py animate booths-algorithm     # ~15 min, real API spend
```

Not ready yet? Either works:

```bash
python fdx.py placeholders booths-algorithm       # title cards
python fdx.py import booths-algorithm ~/clips/    # clips from anywhere
```

**3. Fix the layout.** This is the step that separates you from the AI-slop
channels. The Code2Video paper's own human raters scored its element layout
**60/100** against 98 for hand-made — overlapping text is the usual culprit.
The generated Manim is plain readable Python. Open it, nudge the offending
`.move_to()`, then:

```bash
python fdx.py rerender booths-algorithm path/to/section3.py SectionThree 3
```

**4. Narrate.** Your own voice is worth the extra thirty minutes — record
per section as `audio/01.wav`, `audio/02.wav`, …

```bash
python fdx.py narrate booths-algorithm          # uses your recordings if present
python fdx.py narrate booths-algorithm --tts    # else synthesises
```

**5. Assemble and publish.**

```bash
python fdx.py assemble booths-algorithm         # add --burn to hardcode captions
```

Produces `out/final.mp4`, `out/captions.srt`, `out/thumb_source.png`, and
`out/upload.md` with a description, chapters and a pre-upload checklist.
Work through that checklist — it is short and it is the part that protects
the channel.

Everything after the script in one go:

```bash
python fdx.py run booths-algorithm --tts
```

---

## How sync works

Per section the pipeline holds the **last animation frame** until your
narration finishes, rather than slowing the video down — speed-ramping
maths animations looks cheap and breaks the timing of the explanation. If
the animation overruns your voice by more than 2 seconds it is trimmed
instead, so you never ship dead air.

Captions come straight from `script.md`, not from transcription, so there
is no drift on symbol-heavy sections.

Audio is normalised to −14 LUFS, which is YouTube's target.

---

## Cost and cadence

- ~$1–4 per video in API spend at Opus-class quality, more with retries.
- ~15 min of generation, plus your script and layout time.
- **2–3 videos per week.** Not one per day. Daily templated output is the
  exact pattern the inauthentic-content policy exists to catch, and it is
  also more than you can sustain alongside a teaching load.

`topics/backlog.yaml` holds the 30-topic queue with a status field.

---

## Layout

```
fdx.py                 CLI
fdx/cfg.py             paths, env, ffprobe helpers
fdx/project.py         scaffolding + script.md parser
fdx/animate.py         Code2Video, import, rerender, placeholders
fdx/narrate.py         your voice or TTS, loudness normalised
fdx/assemble.py        sync, concat, SRT, chapters
fdx/publish.py         upload packet
topics/backlog.yaml    the 30-video queue
projects/<slug>/       script.md, sections/, audio/, build/, out/
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `latex failed` in Manim | install `texlive-latex-extra texlive-science` |
| `edge-tts` SSL error | corporate/proxy TLS interception — record your own audio |
| Windows: `no bash found` | install Git for Windows, reopen PowerShell |
| Windows: `manim` not found | activate the venv: `.\.venv\Scripts\Activate.ps1` |
| Windows: LaTeX prompt pops up | MiKTeX asking to install a package — tick "always", it stops asking |
| Windows: captions look wrong | font fallback; `CAPTION_FONT` in `fdx/cfg.py` |
| Code2Video finds no mp4 | check `CASES/` under `Code2Video/src`, then use `fdx import` |
| Concat looks glitchy | a clip skipped normalisation — re-run `fdx import` |
| Captions drift | a section's audio was replaced after assembly — re-run `assemble` |
