# Pedagogy Harness Design

The current Prompt2Render harness validates artifacts and geometric layout. It does not validate the educational quality of the script, narration, or animation plan before code generation begins. The proposed pedagogy harness introduces a dedicated educational review and improvement cycle *before* the expensive rendering and validation stages.

## The Problem

1. **Scaffolded Outlines**: The `auto` command generates a structural outline, but it may lack necessary prerequisites, clear examples, or sufficient depth for the target audience.
2. **Drafted Narration**: The AI-drafted narration might be too superficial, too dense, or fail to connect with the animation brief.
3. **Animation Briefs**: The human-authored or AI-drafted `> ANIM:` briefs might describe static scenes instead of dynamic, step-by-step state changes that match the narration.
4. **Late Discovery**: Currently, pedagogical errors (like an incorrect Hanoi rule demonstration or a confusing explanation) are only caught *after* scene code generation, or they slip through entirely if the code is geometrically valid.

## Proposed Architecture

We will introduce a new set of harness plugins that run *after* the initial script/narration generation but *before* voice synthesis and scene generation.

### 1. `planner_pedagogy` (The Editor)

This plugin acts as the lead editor. It reviews the entire `script.md` (outline, animation briefs, and narration) against a strict educational rubric:

*   **Audience Alignment**: Does the depth match the target audience (e.g., undergraduate computer science)?
*   **Prerequisites**: Are necessary foundational concepts introduced before complex algorithms?
*   **Concrete Examples**: Does the script trace a specific, concrete example (e.g., sorting the array `[5, 2, 9, 1]`) rather than just explaining abstract rules?
*   **Animation-Narration Sync**: Does the narration explicitly describe what is happening in the `> ANIM:` brief? Are the animation steps broken down progressively?
*   **Pacing and Cognitive Load**: Is any single section trying to explain too much at once? Should it be split?

**Output**: A structured critique (`pedagogy_critique`) identifying specific weaknesses and suggesting concrete revisions.

### 2. `reviser_script` (The Writer)

If the `planner_pedagogy` produces a critique with required changes, this plugin rewrites the affected sections of `script.md` (updating the outline, `> ANIM:` briefs, and narration) to address the feedback.

**Output**: An updated `script.md` and a refreshed `scene_plan`.

### 3. `verifier_pedagogy` (The Gatekeeper)

This plugin reviews the revised script. If the script meets the educational rubric, it passes. If it still fails after a maximum number of revision cycles, it halts the harness run, requiring human intervention.

**Output**: A PASS/FAIL status in `check_results`.

## Integration into the Pipeline

The new sequence will be:

```text
(initial outline/drafting)
→ planner_script (initial narration draft if missing)
→ chunker_scene
→ planner_pedagogy (critique)
→ reviser_script (rewrite if needed)
→ verifier_pedagogy (gate)
→ planner_visual (apply deterministic animation contract)
→ generator_voice
... (rest of pipeline)
```

## Configuration

The pedagogy harness will be configurable in `config.yaml`:

```yaml
planner_pedagogy:
  enabled: true
  strictness: high # (low, medium, high) Determines how aggressive the critique is.
  max_revisions: 2 # Maximum number of automatic rewrite cycles.
```

## Why this approach?

1.  **Shift-Left Quality**: We fix the script *before* we spend Gemini quota on scene generation or Kokoro time on TTS.
2.  **Separation of Concerns**: The Editor (critique) and the Writer (revision) are separate LLM calls. This produces much better results than asking a single prompt to "review and rewrite" simultaneously.
3.  **Inspectability**: The critique is saved to the harness log, so you can see *why* the AI decided to change your script.
4.  **Topic-Agnostic**: The rubric focuses on structural educational quality (concrete examples, pacing, sync) rather than hardcoding domain-specific rules (like Hanoi).


## Implemented behavior

The design is now implemented by `prompt2render/harness/plugins/pedagogy.py` and `prompt2render/pedagogy.py`. The default order is `planner_script → chunker_scene → planner_pedagogy → reviser_script → verifier_pedagogy → planner_visual → generator_voice`. The review is video-level, not one independent request per scene. Deterministic checks always run; when a configured Gemini key is available, one compact JSON review is added, followed by at most `max_revisions` rewrite/recheck cycles.

The reviewer is deliberately conservative about automatic rewriting. A failed review without an available or valid LLM completion never overwrites `script.md`; it remains a blocking finding instead. After a successful rewrite, the scene plan is reparsed from the updated script before animation planning and TTS.

## Math speech handling

The source script may retain LaTeX-like display notation such as `$O(n)$`, `$x^2 + y^2 = z^2$`, or `\\frac{a}{b}`. `prompt2render/mathspeech.py` creates a speech-only rendering for Kokoro, so delimiters are not pronounced as “dollar”. Common operators are verbalized conservatively, for example “oh n”, “squared”, “plus”, “equals”, and “a over b”. Captions and alignment continue to retain the source narration text, so the visual and written equation are not replaced by the spoken approximation.

This handling is intentionally limited to recognized paired math delimiters. A standalone currency value such as `$5` is not treated as an equation span.
