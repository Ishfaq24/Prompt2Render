# Retired: the Code2Video path

`prompt2render animate` used to drive [Code2Video](https://github.com/showlab/Code2Video)
to generate silent Manim clips from a script, which `prompt2render assemble` then
force-fit to narration by holding the last frame. That path is retired.

## Why

- Code2Video rendered at 480p15 — too low to ship.
- Its own layout critic needs a vision model on the rendered frame; the
  Gemini AI Studio endpoint this project can afford doesn't accept that, so
  the critic never ran, and the paper's own human raters scored its element
  layout 60/100 against 98 for hand-made.
- It produces one opaque clip per section with no internal cue structure —
  no way to know when a word is spoken relative to what's on screen. That is
  what forced `prompt2render assemble`'s hold-last-frame-until-narration-finishes hack,
  which can only pad or trim, never actually sync.

## What replaced it

`prompt2render scenes` asks a model to storyboard each section directly against a small
fixed drawing API (`prompt2render/scenekit.py`) instead of writing arbitrary Manim.
Small API surface, few ways to be wrong, and every mistake — an off-frame
label, two elements overlapping — is caught by `scenekit.audit()` from the
rendered frame's own pixel geometry and fed straight back to the model. No
vision model, no extra API call, and it closes the exact gap Code2Video's critic
couldn't.

Because each section is now a list of timed stills (`prompt2render stills` / `prompt2render plan`)
rather than one opaque clip, `prompt2render encode` / `prompt2render finish` know when every word
is spoken and cut to it — sync by construction, not by padding afterwards.

See the pipeline stages in the main `README.md`.

## What was removed

- `prompt2render/animate.py`, `prompt2render/narrate.py`, `prompt2render/kokoro_tts.py` — superseded by
  `prompt2render/visuals.py` and `prompt2render/voice.py`, and unreferenced by `prompt2render.py`.
- `tools/*.py` (`build_video.py`, `gen_scenes.py`, `narrate_aligned.py`,
  `render_scene.py`, `scenekit.py`) — the pre-package prototype the current
  `prompt2render/` package grew out of. `tools/kokoro/` (the model weights) is unrelated
  and stays.
- `vendor/Code2Video` — was kept around (git-ignored) for anyone who wanted to
  compare, but nothing in `prompt2render/` ever called into it. Removed from disk
  entirely as part of the Prompt2Render migration; see
  `docs/MIGRATION_INVENTORY.md`.

`prompt2render animate` remains as a stub that points here rather than silently doing
the wrong thing.
