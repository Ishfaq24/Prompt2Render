# Retired: the Code2Video path

`fdx animate` used to drive [Code2Video](https://github.com/showlab/Code2Video)
to generate silent Manim clips from a script, which `fdx assemble` then
force-fit to narration by holding the last frame. That path is retired.

## Why

- Code2Video rendered at 480p15 — too low to ship.
- Its own layout critic needs a vision model on the rendered frame; the
  Gemini AI Studio endpoint this project can afford doesn't accept that, so
  the critic never ran, and the paper's own human raters scored its element
  layout 60/100 against 98 for hand-made.
- It produces one opaque clip per section with no internal cue structure —
  no way to know when a word is spoken relative to what's on screen. That is
  what forced `fdx assemble`'s hold-last-frame-until-narration-finishes hack,
  which can only pad or trim, never actually sync.

## What replaced it

`fdx scenes` asks a model to storyboard each section directly against a small
fixed drawing API (`fdx/scenekit.py`) instead of writing arbitrary Manim.
Small API surface, few ways to be wrong, and every mistake — an off-frame
label, two elements overlapping — is caught by `scenekit.audit()` from the
rendered frame's own pixel geometry and fed straight back to the model. No
vision model, no extra API call, and it closes the exact gap Code2Video's critic
couldn't.

Because each section is now a list of timed stills (`fdx stills` / `fdx plan`)
rather than one opaque clip, `fdx encode` / `fdx finish` know when every word
is spoken and cut to it — sync by construction, not by padding afterwards.

See the pipeline stages in the main `README.md`.

## What was removed

- `fdx/animate.py`, `fdx/narrate.py`, `fdx/kokoro_tts.py` — superseded by
  `fdx/visuals.py` and `fdx/voice.py`, and unreferenced by `fdx.py`.
- `tools/*.py` (`build_video.py`, `gen_scenes.py`, `narrate_aligned.py`,
  `render_scene.py`, `scenekit.py`) — the pre-package prototype the current
  `fdx/` package grew out of. `tools/kokoro/` (the model weights) is unrelated
  and stays.
- `vendor/Code2Video` is still present (git-ignored) for anyone who wants to
  compare, but nothing in `fdx/` calls into it anymore.

`fdx animate` remains as a stub that points here rather than silently doing
the wrong thing.
