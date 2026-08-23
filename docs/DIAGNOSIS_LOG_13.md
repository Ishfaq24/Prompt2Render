# Diagnosis of `pasted_content_13.txt`

## 1. The Command Run
`python prompt2render.py auto "History and Definition of Pi" --harness --strict --manim`

This tells the runner to:
1. Generate an AI outline.
2. Draft AI narration.
3. Run the harness with `--manim`, which replaces `generator_code` with `generator_manim` and `renderer_stills` with `renderer_manim`.

## 2. Key Observations from the Log

### A. Gemini Fallback Bug
Lines 3-12 show the model fallback logic:
- Tries `gemini-3.6-flash` keys 1 through 4. All fail (rate-limited).
- Switches to `gemini-3.6-flash-lite`.
- `gemini-3.6-flash-lite` fails with `NOT_FOUND or unsupported. Skipping permanently.`
- It then successfully falls back to `gemini-3.5-flash` and eventually `gemini-3.5-flash-lite`, which works.
*Diagnosis:* The fallback logic correctly recovers from the `NOT_FOUND` error on 3.6-lite, but it wastes time and API calls attempting a non-existent model. This matches the user's earlier complaint.

### B. Harness Order
Line 34 shows the resolved plugin order:
`planner_script -> chunker_scene -> planner_pedagogy -> reviser_script -> verifier_pedagogy -> planner_llm -> planner_visual -> generator_voice -> generator_align -> planner_audio -> verifier_storyboard -> generator_manim -> renderer_manim -> renderer_manim -> verifier_semantic -> verifier_lifecycle -> verifier_spatial -> feedback_hitl -> generator_timeline -> renderer_encode -> renderer_finish -> verifier_audio -> verifier_final_qc -> generator_publish`

*Diagnosis:* 
1. The Manim plugins successfully swapped in (`generator_manim`, `renderer_manim`).
2. **BUG:** `renderer_manim` appears *twice* in the pipeline.
3. The overall order is correct (planners -> voice -> align -> code -> render -> verify -> encode).

### C. The Fatal Crash
Lines 64-67:
```
[prompt2render] storyboard: trying gemini-3.5-flash-lite (model 4/4, key 3/4)
[prompt2render] storyboard: trying gemini-3.5-flash-lite (model 4/4, key 3/4)
[prompt2render] storyboard: trying gemini-3.5-flash-lite (model 4/4, key 3/4)
[prompt2render] harness hard gate failed: verifier_storyboard: hard gate failed — [{'status': 'fail', 'finding_type': 'storyboard_failure', 'category': 'STORYBOARD', 'severity': 'BLOCKING', 'stem': '07', 'detail': 'state 1 cue 3 is outside 0..2'}]
```

*Diagnosis:*
1. The crash happens in `verifier_storyboard`.
2. Section 07 has 3 sentences (indices 0, 1, 2).
3. The generated storyboard for Section 07 contains a state that attempts to cue on sentence index 3.
4. `verifier_storyboard` catches this invalid index and raises a `BLOCKING` failure.
5. **CRITICAL BUG:** The `repair_router` did not catch and fix this! The run immediately halted with `harness hard gate failed`.

Why didn't the repair router fix it?
In `docs/HARNESS.md`, we noted: "today only `generator_code` implements the per-scene `revert_scene()` / `regenerate_one()` pair the fast repair path needs."
But in `--manim` mode, `generator_code` is swapped out for `generator_manim`. Wait, the crash is in `verifier_storyboard`, which checks the output of `planner_llm` (the storyboard generator), not the code generator.
If `planner_llm` does not implement `revert_scene()` and `regenerate_one()`, the `repair_router` cannot fix storyboard failures, causing a hard crash.

Let's verify `planner_llm` and `verifier_storyboard`.

### D. The Root Cause of the Hard Crash
`planner_llm` uses an LLM to generate a JSON storyboard. It does not implement `revert_scene()` or `regenerate_one()`. 
When `verifier_storyboard` finds a blocking error (e.g., `cue 3 is outside 0..2`), the `repair_router` intercepts the failure but realizes the source plugin (`planner_llm`) cannot perform a per-scene repair. Thus, the repair router gives up, and because `verifier_storyboard` is a hard gate (`_default_gate` returns `True`), the runner halts the pipeline.

### E. Gemini 3.6 Lite Fallback Bug Root Cause
In `prompt2render/llm.py` (which we need to inspect), there is likely a hardcoded list of fallback models that includes `gemini-3.6-flash-lite`, which Google never released (they went from 3.5-flash-lite to 3.7-flash, skipping 3.6-lite). When the rate limit hits, it tries this invalid model and crashes out or skips permanently.

### F. The Registry Bug (Duplicate Manim Renderer)
In `prompt2render.py` around line 254:
```python
    if getattr(a, "manim", False):
        from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin, RendererManimPlugin
        # Replace generator_code with generator_manim
        plugins = [GeneratorManimPlugin() if p.name == "generator_code" else p for p in plugins]
        # Replace renderer_stills with renderer_manim
        plugins = [RendererManimPlugin() if p.name == "renderer_stills" else p for p in plugins]
```
Wait, earlier in `prompt2render/harness/plugins/__init__.py`:
```python
    "renderer_stills": RendererStillsPlugin,
    "renderer_manim": RendererManimPlugin,
```
Both `renderer_stills` and `renderer_manim` are already in the `plugins` list if they were returned by `build_plugins`.
Wait, `build_plugins` only returns enabled plugins.
In `prompt2render.py` line 247:
```python
    if not getattr(a, "manim", False):
        cfg_dict.setdefault("renderer_manim", {})["enabled"] = False
```
If `--manim` is passed, `renderer_manim` defaults to its own `is_gate()` or `enabled` status, which is `False` by default, but wait...
If it is somehow enabled, it's in the list. Then `prompt2render.py` replaces `renderer_stills` with *another* instance of `RendererManimPlugin`. Thus it runs twice!

### Summary of Required Fixes
1. **Model Fallback:** Remove `gemini-3.6-flash-lite` from `CANONICAL_MODELS` in `llm.py` so it stops trying a non-existent model and wasting time.
2. **Harness Order/Duplication:** In `prompt2render.py`, the hot-swap logic for `--manim` is flawed because it blindly replaces `renderer_stills` with `renderer_manim` without ensuring `renderer_manim` isn't already there.
3. **Storyboard Repair:** `planner_llm` must implement `revert_scene()` and `regenerate_one()` so the `repair_router` can catch `verifier_storyboard` failures and retry the LLM call, rather than hard-crashing the pipeline.

### G. The Manim-to-Timeline Contract Mismatch
The second crash in the log:
`[prompt2render] ! timeline planning failed: [prompt2render] no stills for section 01 — run prompt2render stills`

*Diagnosis:*
The pipeline order in the harness is:
`generator_manim -> renderer_manim -> verifier_semantic -> ... -> generator_timeline -> renderer_encode -> renderer_finish`

`renderer_manim` wraps `visuals.py::manim_scene()`. This function calls the Manim CLI, produces a single `.mp4` clip for the section, and copies it to `projects/<slug>/sections/NN.mp4`.
However, `generator_timeline` wraps `timeline.build()`. This function expects `scenekit` output: it looks for `build/scenes/NN/manifest.json` containing cue timings, still paths, and PNG files to plan word-level cuts. Because Manim does not produce still manifests or PNGs, `timeline.build()` immediately fails with "no stills for section 01".

The Code2Video approach generated opaque section clips and assembled them by padding/holding the last frame (which Prompt2Render does in its legacy `assemble.py` path). When the Prompt2Render harness was wired up for `--manim`, the downstream stages (`timeline`, `encode`, `finish`) were blindly left in the graph. They are fundamentally incompatible with Manim's single-clip output.

*Fix:*
When `--manim` is active, the harness must bypass `generator_timeline`, `renderer_encode`, and `renderer_finish`, and instead use a plugin that wraps the legacy `assemble.assemble()` function (which pads/holds frames to fit audio, matching the Code2Video behavior).

Wait, in `prompt2render.py` (around line 287):
```python
    # The default harness now runs timeline -> encode -> finish -> final QC ->
    # publish natively. Do not run qc.check a second time; it would repeat the
    # expensive independent caption-drift transcription. The final-QC plugin
    # has already recorded the authoritative result in the harness log.
    if getattr(a, "manim", False):
        from prompt2render import assemble
        cfg.say("harness: assembling Manim section clips...")
        assemble.assemble(d, s, burn_captions=getattr(a, "burn", False))
```
The CLI wrapper *does* call `assemble.assemble()` after the harness finishes! But the harness itself is still running `generator_timeline`, `renderer_encode`, and `renderer_finish` because they are enabled by default in `config.yaml` and not disabled in `prompt2render.py` when `--manim` is passed.

To fix this, we must explicitly disable the incompatible downstream plugins when `--manim` is active.

## Diagnosis of the complete log (`pasted_content_14.txt`)

### What succeeded

The run successfully completed the AI script reuse, pedagogy stage, narration generation, audio mastering, cached ASR alignment, storyboard generation, and Manim rendering for Sections 01, 02, 03, 04, and 08. The log confirms Manim 0.19.0 rendered those scenes at 1080p30 and normalized their section clips to narration durations.

The Manim 0.19.0 warning is informational, not the failure. Code2Video's published README also documents Manim Community v0.19.0, so upgrading to v0.21.0 during a comparison would introduce a version confound. Keep v0.19.0 for the controlled experiment unless a separate compatibility migration is intentionally tested.

### Manim code-generation failures

Section 05 fails because generated code calls `Axes.get_x_label(..., font_size=20, direction=...)`; the installed Manim 0.19.0 reports that the generated getter does not accept `font_size`.

Section 06 fails because generated code calls `arc.move_to(bl_corner, corner=DL)`; `Mobject.move_to()` in the installed version does not accept `corner`.

Section 07 fails because generated code calls `Code(..., theme="monokai")`; `Code.__init__()` in the installed version does not accept `theme`.

These are generated-code API-compatibility failures, not GPU or audio failures. The generator prompt has now been strengthened with the exact compatible alternatives: create labels with `Text` and `next_to`, call `move_to(point)` without `corner`, and call `Code(code_string=..., language=...)` without `theme`.

### Why the run still reached timeline

The user's installed `prompt2render.py` still resolved `generator_timeline -> renderer_encode -> renderer_finish` in Manim mode. That proves the previous downstream-stage change was not present in the exact Windows file used for this run, or that only part of the prior archive was copied. Since Manim emits section MP4 clips and no Scenekit still manifest, timeline planning must not run in Manim mode.

The corrected local `prompt2render.py` now removes `generator_timeline`, `renderer_encode`, `renderer_finish`, `verifier_audio`, `verifier_final_qc`, and `generator_publish` from the active Manim graph even if a stale config enables them. It then assembles the section clips with `assemble.assemble()` and checks that `out/final.mp4` exists and is non-trivial before returning success.

### Repair behavior correction

Manim render failures are now recorded as `finding_type: execution_failure` with category `RENDER`, and the repair router aliases its normal `generator_code` target to `generator_manim` when the Manim generator is active. This allows a failed section to be regenerated using the Manim generator's repair context instead of being treated as an unrepairable missing target.

The local regression suite passes **66 tests** after these changes, including a new graph test asserting exactly one `renderer_manim` and no still-based downstream stages in Manim mode. A real Windows run with Gemini, Manim, FFmpeg, and the user's project is still required; local tests do not prove the generated Manim API will pass for every topic.

## Latest log (`pasted_content_15.txt`)

The previous timeline contract fix is now active: the latest log ends at `renderer_manim: hard gate failed` and does not reach `generator_timeline`. Sections 01, 02, 03, 04, and 08 render successfully. The repair loop regenerated Sections 05, 06, and 07; Section 05 and Section 06 then rendered successfully.

The remaining blocking failure is Section 07:

```text
TypeError: Code.__init__() got an unexpected keyword argument 'insert_line_numbers'. Did you mean 'add_line_numbers'?
```

This is another Manim 0.19 API mismatch in generated code. It is not an NVENC, TTS, storyboard, or timeline failure. The Manim renderer correctly records it as a blocking `RENDER` / `execution_failure` finding and the hard gate stops assembly because Section 07 has no valid final clip.

The log also shows the Harness repair loop is active: after the first render failures, it requests new Manim code for Sections 05, 06, and 07 and successfully repairs two of them. Therefore the current run demonstrates Harness-mediated retry behavior, but not a complete successful run yet.

The next correction must add `insert_line_numbers` -> `add_line_numbers` to the Manim 0.19 compatibility prompt and apply a deterministic normalization before saving generated code. Keep Manim 0.19.0 for the Code2Video comparison; do not upgrade to 0.21.0 during this experiment.

## Latest attachment (`pasted_content_15.txt`)

The previous downstream contract fix is active: the run no longer reaches the Scenekit timeline stage. Sections 01–04 and 08 render on the first or cached attempt. Sections 05 and 06 are repaired successfully by the Harness after Manim failures.

The remaining failure is Section 07. The first generated version used `UP_LEFT`, which is not a valid Manim 0.19 name; the next generated version used `Code(insert_line_numbers=...)`, but Manim 0.19 expects `add_line_numbers`. A later retry also generated malformed `MathTex` braces, producing a LaTeX `Missing } inserted` error. These are generated-code compatibility/syntax failures, not GPU or timeline failures.

The renderer now records these as blocking `RENDER` / `execution_failure` findings, and the Harness correctly stops before assembly when any section remains invalid. The generator prompt now forbids the incompatible forms and a deterministic pre-write normalizer converts common safe aliases (`insert_line_numbers` to `add_line_numbers`, and `UP_LEFT`/related names to `UL`/related names). Local tests pass **67 tests** including the new normalizer test.

A real Windows rerun is still necessary. The corrected run should show no `generator_timeline`, `renderer_encode`, or `renderer_finish` entries after `--manim`, and it should end with a valid Manim assembly only if all sections pass the render gate.
