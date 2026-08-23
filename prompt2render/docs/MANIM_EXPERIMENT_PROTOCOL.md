# Manim-to-Manim Comparison Protocol: Prompt2Render Harness vs. Code2Video

This protocol defines a controlled experiment to determine whether the Prompt2Render harness (using its `generator_manim` and `repair_router` mechanisms) outperforms Code2Video when both systems are restricted to generating **Manim code** for the same educational topics.

## 1. Experimental Objective

To isolate the effect of the **Prompt2Render Harness** (pedagogy review, storyboard verification, execution repair routing, and forced-alignment timing) from the effect of the **rendering substrate** (Scenekit vs. Manim). 

By forcing Prompt2Render to use Manim via the `--manim` flag, we test the hypothesis:
*Does a "shift-left" pedagogy harness and a deterministic execution-repair router produce higher-quality Manim educational videos than Code2Video's Planner-Coder-Critic architecture?*

## 2. Experimental Conditions

The experiment consists of three conditions run across a shared set of topics.

### Condition A: Code2Video Baseline (Official)
* **System:** The official Code2Video repository (`showlab/Code2Video`).
* **Input:** A bare knowledge point (e.g., "Linear transformations and matrices").
* **Process:** Uses its native Planner (for storyboarding), Coder (with ScopeRefine debugging), and Critic (VLM layout checking with visual anchors).
* **Output:** Manim code, rendered clips, and a final video assembled by holding the last frame to match audio.

### Condition B: Prompt2Render Manim (Unattended)
* **System:** Prompt2Render run via `python prompt2render.py auto <slug> --harness --manim --strict`.
* **Input:** The exact same knowledge point used in Condition A.
* **Process:** Uses `planner_script` to draft the outline, `planner_pedagogy` to review/revise the script, `generator_manim` to write the Manim code, `repair_router` to catch and fix Manim compilation/execution errors, and `generator_align` to cut the timeline to exact word boundaries.
* **Output:** Manim code, rendered clips, and a final video assembled via forced alignment.

### Condition C: Prompt2Render Manim (Human-Authored Script)
* **System:** Prompt2Render run via `python prompt2render.py build <slug> --harness --manim --strict`.
* **Input:** A human-authored `script.md` containing the exact narration and animation briefs that a human educator would write for the topic.
* **Process:** Same as Condition B, but isolates the effect of the code-generation and repair routing from the quality of the AI-drafted script.
* **Output:** Manim code, rendered clips, and a final video assembled via forced alignment.

## 3. Matched Benchmark Dataset

To ensure a fair comparison, the experiment will use a stratified subset of the **MMMC Benchmark** introduced by Code2Video.

Select 20 topics from the MMMC dataset, stratified across four difficulty tiers:
1. **Static Concepts:** (e.g., "The definition of a derivative") - Tests basic text and formula placement.
2. **State Transitions:** (e.g., "The Tower of Hanoi problem") - Tests object tracking and logical rule adherence.
3. **Continuous Transformations:** (e.g., "Linear transformations and matrices") - Tests Manim's core continuous animation strengths.
4. **Adversarial Layouts:** (e.g., "Deep neural network architectures") - Tests the system's ability to avoid spatial overlaps with many elements.

## 4. Controlled Variables

To prevent confounding factors, the following variables must be fixed across all conditions:
* **LLM Provider:** Both systems must use the same underlying LLM (e.g., `gemini-3.5-flash` or `gemini-3.7-flash`) for their Coder/Generator stages.
* **VLM Provider:** Both systems must use the same VLM for visual criticism (if applicable).
* **Manim Version:** Both systems must execute against Manim Community Edition v0.19.0.
* **Retry Budgets:** Code2Video's `max_fix_bug_tries` and Prompt2Render's `repair_router.max_repair_cycles` must be set to the same limit (e.g., 3 retries).
* **Audio Engine:** Both systems must use the same TTS engine (Kokoro) and voice to ensure timing differences are due to the architecture, not the speaker.

## 5. Evaluation Metrics

To answer the research question, the experiment must measure outcomes across three dimensions: Reliability, Synchronization, and Educational Quality.

### 5.1 Reliability and Engineering Metrics
* **First-Pass Compilation Rate:** Percentage of Manim scenes that compile and render successfully on the first LLM attempt without triggering the repair router or ScopeRefine.
* **Final Compilation Rate:** Percentage of scenes that successfully compile after all repair cycles are exhausted.
* **Repair Efficiency:** Average number of LLM calls, token usage, and wall-clock seconds consumed per successful repair.
* **Unresolved Defect Rate:** The percentage of videos that exit the pipeline with known, unfixable errors (e.g., overlapping text, out-of-bounds geometry).

### 5.2 Synchronization Metrics
Because Prompt2Render claims its forced-alignment timeline solves Code2Video's "hold-last-frame" sync issue, we must explicitly measure timing.
* **Caption Drift:** The absolute difference in milliseconds between the spoken word (via Whisper alignment) and the visual state change. Report the median, 95th percentile (p95), and maximum drift for each video.
* **Frozen Frame Duration:** The total duration in seconds that a video holds a static frame waiting for audio to finish. (Code2Video is hypothesized to have high frozen frame duration; Prompt2Render should have near zero).

### 5.3 Educational Quality Metrics
* **TeachQuiz Score:** Run the official `eval_TQ.py` script from the Code2Video repository on the final videos from all three conditions. Report the baseline score, post-unlearning score, and post-video learning gain.
* **VLM Aesthetic Score (AES):** Run the official `eval_AES.py` script from the Code2Video repository to measure Element Layout, Attractiveness, Logic Flow, Visual Consistency, and Accuracy & Depth.
* **Human Annotation (Optional but Recommended):** Blinded expert review of the videos to detect hallucinations, pedagogical errors, and visual correspondence failures that VLMs might miss.

## 6. Required Ablations

To prove *why* Prompt2Render performs the way it does in Manim mode, run the following ablations on Condition B:

1. **No Pedagogy Harness:** Disable `planner_pedagogy` and `reviser_script`. Does the TeachQuiz score drop? This isolates the value of the "shift-left" script review.
2. **No Repair Router:** Disable `repair_router`. Does the Final Compilation Rate drop? This isolates the value of the event-driven execution repair.
3. **No Forced Alignment:** Disable `generator_align` and fall back to Code2Video-style section-duration padding. Does the Caption Drift metric spike?

## 7. Statistical Analysis

* **Sample Size:** 20 topics $\times$ 3 conditions = 60 video generation runs.
* **Significance Testing:** Use paired t-tests or Wilcoxon signed-rank tests (depending on normality) to compare the learning gains (TeachQuiz) and aesthetic scores (AES) between Condition A and Condition B/C.
* **Reporting:** Report all metrics with means, standard deviations, and 95% confidence intervals. Do not report only a single aggregate score. Provide a scatter plot showing the trade-off between Generation Time (cost) and TeachQuiz Gain (quality) for both systems.
