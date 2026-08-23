# Prompt2Render versus Code2Video: Evidence-Based Publication Assessment

**Status of this assessment:** repository review and primary-source comparison completed on 23 August 2026. This is a publication-readiness assessment, not a claim of acceptance or a claim that either system is universally superior.

## Executive conclusion

Prompt2Render does **not yet have evidence supporting the statement that it performs better than Code2Video overall**. The two systems share a code-mediated approach to educational video generation, but they optimize different objectives. Code2Video is a published, benchmark-oriented research system built around Planner–Coder–Critic agents, executable Manim code, visual-anchor feedback, and the MMMC/TeachQuiz evaluation suite [1] [2]. Prompt2Render is an evolving local-first pipeline whose strongest potential contribution is narrower: **constrained code generation plus deterministic artifact/layout checks, speech-derived timing, and auditable stage gates**.

The current repository is promising as a systems-and-reproducibility project, but it is **not journal-ready as an empirical paper**. The local code has a useful research hypothesis and a growing test suite, yet the evidence is presently dominated by unit tests, mock harness tests, internal design documents, and individual Windows observations. It lacks a frozen release, independent real-project benchmark, matched Code2Video baseline, human annotation study, learning-outcome evaluation, ablations, confidence intervals, and a validated end-to-end repair experiment.

The most defensible manuscript should not claim “Prompt2Render beats Code2Video.” It should ask a narrower, testable question:

> **Can constraining the rendering API and adding deterministic, execution-time verification reduce educational-video defects and synchronization failures while preserving acceptable visual quality and knowledge transfer?**

That framing creates a credible technical contribution even if Prompt2Render is not best on every aesthetic or expressiveness measure.

## 1. What the primary Code2Video sources establish

The Code2Video project describes an agentic, code-centric educational-video framework with three principal roles: a Planner that structures a topic and prepares visual assets, a Coder that converts storyboard instructions into executable Python/Manim code with debugging, and a Critic that uses visual-language feedback and visual anchors to refine spatial layout and clarity [1] [2]. Its public repository specifies Manim Community v0.19.0, separate LLM and VLM credentials, and an optional IconFinder API for visual assets [1]. The repository is released under the MIT license [1].

The associated paper defines the task as mapping a learning query to executable Manim code. It introduces ScopeRefine, a hierarchical repair strategy that moves from a local line scope to a lecture-line block and then to full-section regeneration when necessary. It also describes a 6-by-6 visual-anchor grid and occupancy information intended to make spatial correction more actionable for the Critic [2]. These are important strengths of the baseline: the system is not merely one-shot code generation, and it has an explicit evaluation story.

Code2Video also contributes the MMMC benchmark. The paper describes 117 long-form videos across 13 subject areas, segmented into 339 semantically coherent clips and 456 total units, with average full-video and segmented-clip durations of approximately 1,014 and 201 seconds respectively [2]. Its evaluation protocol includes five VLM-judge dimensions—Element Layout, Attractiveness, Logic Flow, Visual Consistency, and Accuracy & Depth—plus code-generation efficiency and TeachQuiz knowledge transfer [2].

TeachQuiz is described as a two-stage protocol: first estimate a baseline, then apply an unlearning prompt intended to remove prior access to the target concept, and finally ask the model to answer questions after viewing the video. The reported learning gain is the post-video score minus the post-unlearning score [2]. This is a useful protocol to reproduce, but it is not equivalent to a human learning study. It is affected by model choice, prompt wording, video-input capability, unlearning success, question construction, repeated trials, and possible contamination from training data. Prompt2Render should therefore report TeachQuiz as one automated knowledge-transfer measure, not as conclusive proof of educational effectiveness.

The Code2Video paper reports 30% improvement for direct code-centric generation and a 40% improvement for the full Planner–Coder–Critic pipeline, and reports human-study TeachQuiz results in which agentic videos outperform professional human-made tutorials [2]. Those are claims from the published paper. They should be quoted with the paper's exact experimental definitions and reproduced independently before being used as a numerical target or as evidence that Prompt2Render is inferior or superior.

## 2. Technical comparison

| Dimension | Code2Video | Prompt2Render, based on the current repository | Fair interpretation |
|---|---|---|---|
| Primary rendering substrate | Direct executable Manim/Python code [1] [2] | LLM-generated scene modules against the constrained `scenekit` API, rendered through Matplotlib/Pillow; Manim is an opt-in escape hatch | Code2Video has a larger expressive surface; Prompt2Render can make more deterministic contracts enforceable |
| Planning | Topic outline, section storyboard, lecture lines, animations, and optional external assets [2] | Script/section parsing, pedagogy review/revision, storyboard contract, visual contract, audio planning | Both plan before rendering; Prompt2Render's pedagogy stage is a proposed shift-left mechanism, not yet proven to improve learning |
| Code repair | ScopeRefine: line, block, then global repair [2] | Scene-generation retries plus harness repair router; current documentation says only `generator_code` implements the fast per-scene repair interface | Both are iterative; Prompt2Render's router is broader in design but less empirically validated |
| Layout checking | VLM Critic with visual anchors and occupancy information [2] | Deterministic geometry audit based on recorded primitive geometry; current `verifier_spatial` is the real harness verifier | Prompt2Render can provide stronger guarantees for the checks it actually implements, but cannot infer arbitrary subject-matter truth |
| Semantic/factual checking | VLM Critic and TeachQuiz-oriented evaluation [2] | `verifier_semantic` is documented as a stub that always reports clean; pedagogy checks are mainly structural with optional LLM review | Prompt2Render must not claim factual correctness or complete semantic verification today |
| Rendering/timing | Manim animation timeline and section video generation [1] [2] | Sentence-level local TTS, alignment, still-state timeline, FFmpeg assembly, and final QC | Prompt2Render has a clear synchronization hypothesis; it needs corpus-level shipped-output measurements |
| Audio/caption verification | Not established from the public README/paper as a primary contribution | Dedicated alignment/audio/QC stages, with prior user runs showing caption-drift failures that were not automatically solved | The intended design is stronger on audio auditability; implementation reliability remains an open experiment |
| Auditability | Code and intermediate agent artifacts are available in the repository structure [1] | Intended JSON/JSONL stage logs, provenance, findings, repair records, and `self_correction_report.json` | Prompt2Render's audit trail is a promising contribution, but audit completeness and schema stability need a release and external replay |
| Evaluation | MMMC, TeachQuiz, VLM aesthetics, token usage, generation time [1] [2] | No completed matched benchmark or learning study in this repository review | Code2Video currently has the stronger published evaluation position |
| License/release maturity | Public MIT repository with evaluation entry points [1] | Active-development repository with modified and untracked files at review time | Prompt2Render needs a clean tagged release before comparative claims are credible |

### What Prompt2Render may do better in a narrow sense

A bounded drawing API makes it possible to reject certain classes of errors using geometry and input contracts instead of asking a VLM to recognize them after the fact. For example, a documented domain primitive can reject an invalid number of Hanoi pegs or an invalid state shape, and a geometry audit can detect overlap or off-frame placement when the primitive records the relevant bounds. This is a **conditional guarantee**: it applies only to the implemented primitive, its input validation, and its audit model. It does not prove that the narration is mathematically true, that an animation illustrates the correct claim, or that an arbitrary generated Python program is safe.

Prompt2Render's speech-derived timeline is also a credible engineering hypothesis. The repository separates sentence-level synthesis from word-level alignment and derives still timing from the resulting audio. However, the claim must be evaluated on the final shipped files. Earlier user runs reported a caption-drift failure with a 95th-percentile drift of 4,248 ms and a maximum of 13,024 ms across 81 sentences. That result means the architecture's intended guarantee was not yet achieved in production use; it should be treated as a motivating failure case, not as evidence of success.

### What Code2Video may do better

Code2Video currently has the stronger public research package: a named multi-agent method, a benchmark, evaluation scripts, explicit efficiency measures, and a paper accepted to ICML 2026 according to the project repository [1]. Manim also provides richer continuous animation and mathematical expressiveness than a small still-state API. Prompt2Render may obtain better reliability on selected constrained layouts, but it may lose on motion richness, arbitrary visual forms, or topics not represented by its primitives. Those trade-offs must be measured rather than inferred from screenshots.

The internal Prompt2Render retirement note characterizes the former Manim path as producing opaque clips and being force-fit to audio by holding the last frame. That is a useful hypothesis for a synchronization ablation, but the public Code2Video paper and README reviewed here do not establish that exact behavior as a universal property of Code2Video. The manuscript should inspect and cite the relevant implementation or reproduce the behavior under a specified configuration before making that claim.

## 3. Current implementation evidence and limitations

A local audit on 23 August 2026 found that the repository's current default plugin resolver produces the following order:

```text
planner_script -> chunker_scene -> planner_pedagogy -> reviser_script
-> verifier_pedagogy -> planner_llm -> planner_visual -> generator_voice
-> generator_align -> planner_audio -> verifier_storyboard -> generator_code
-> renderer_stills -> verifier_semantic -> verifier_lifecycle -> verifier_spatial
-> feedback_hitl -> generator_timeline -> renderer_encode -> renderer_finish
-> verifier_audio -> verifier_final_qc -> generator_publish
```

The local graph excludes `renderer_manim` by default. This directly addresses the earlier dependency-order failure in the local checkout, but it does not prove that the user's Windows installation contains the same files. The exact Windows check remains necessary:

```powershell
python -c "from prompt2render.harness.loader import build_plugins; print(' -> '.join(p.name for p in build_plugins()))"
```

The local test run reported **65 passed in 1.67 seconds**. That is useful regression evidence, not end-to-end evidence. The repository's own harness documentation states that `verifier_semantic` is a stub that always reports clean, `verifier_lifecycle` is an empty shell, `feedback_hitl` never gates, and only `generator_code` currently supplies the fast per-scene `revert_scene()`/`regenerate_one()` repair interface. It also states that the repair-router tests use dummy plugins and that the real spatial verifier usually catches issues inside the scene-generation retry loop before the harness-level repair router is exercised.

The repository also has active-development indicators that matter for publication: the review found 33 modified tracked files and 65 untracked paths, including experimental archives, generated artifacts, and new tests. The README explicitly says the web dashboard is not built and that `prompt2render serve` currently exits with `ModuleNotFoundError`. These are not disqualifying for a research prototype, but they mean the present tree is not a frozen artifact that an independent researcher can reliably reproduce.

| Evidence category | Current status | Publication interpretation |
|---|---|---|
| Unit tests | 65 local tests pass | Supports local contracts and regression checks only |
| Default graph order | Verified in the local checkout; not verified on the user's Windows tree | Strong candidate for a release test and installation diagnostic |
| Spatial auditing | Implemented and exercised by local tests/tools | Candidate technical contribution, requiring corpus-level false-positive/false-negative study |
| Pedagogy review | Implemented structural checks plus optional LLM path | Not factual or pedagogical proof; requires annotated evaluation |
| Semantic verifier | Documented stub | Must be implemented or explicitly excluded from claims |
| Lifecycle verifier | Documented stub | Must be implemented or explicitly excluded from claims |
| Repair router | Implemented design and dummy-plugin tests | Real failure → repair → re-render → re-verification remains unproven |
| Audio alignment/QC | Implemented pipeline components; prior real run had large drift failure | Requires final-output benchmark and failure analysis |
| Windows FFmpeg/NVENC | User's GTX 1650 probe still fails to open the encoder | Report CPU fallback honestly; do not claim GPU acceleration is solved |
| Real educational effectiveness | No user study or matched TeachQuiz run | Major missing evidence |

## 4. Novelty assessment

| Proposed contribution | Novel relative to Code2Video? | Defensible now? | Evidence still required |
|---|---:|---:|---|
| Code-mediated educational video generation | No; Code2Video already establishes this paradigm [1] [2] | No as a primary novelty claim | Position against Code2Video and related code/video systems |
| Constrained rendering DSL/API | Potentially yes as a design axis | Partly | Formalize the API, supported topic grammar, guarantees, and expressiveness cost |
| Deterministic geometry and domain-contract verification | Potentially strong | Partly | Error taxonomy, detection precision/recall, adversarial tests, and comparison to VLM critique |
| Shift-left pedagogy review/revision | Potentially useful, but not demonstrated | No | Human annotation, ablation, factuality and learning outcomes |
| Speech-derived still-state timeline and audio QC | Engineering contribution with possible novelty | No empirical claim yet | Drift distribution, latency, caption accuracy, and baseline comparison |
| Generic self-correcting harness with provenance | Useful systems contribution | Partly | Real integration traces, repair success, loops prevented, unresolved-blocking behavior |
| Universal factual/pedagogical correctness | Not supported | No | Do not claim this; deterministic checks are bounded |

The recommended paper title and contribution statement should therefore be closer to **“Auditable, Constrained-Code Educational Video Synthesis with Deterministic Rendering-Time Verification”** than to “A Better Code2Video.” The claimed contribution is the reliability architecture and its measured trade-offs, not a broad assertion that constrained Matplotlib output is aesthetically superior to Manim.

## 5. Fair comparison protocol

A fair comparison must hold the instructional content constant. Do not give one system a topic and the other system a hand-written finished script. Prepare a benchmark of topic packets containing the learning objective, audience, prerequisite assumptions, authoritative facts, worked example, prohibited misconceptions, and a reference narration or content outline. Run both systems from the same topic packet, and run a second condition from the same fixed narration/storyboard where possible.

The benchmark should include at least 24 topics in four families: algorithms and data structures, mathematics, computer architecture or machine learning, and physics or engineering. Include easy and difficult cases, static explanations and state-transition problems, and deliberately adversarial cases such as Hanoi legality, matrix dimensions, sorting invariants, asymptotic notation, neural-network tensor shapes, and sign conventions. Start with 12 topics for debugging and preregistration, then expand to 24 or 48 held-out topics for the main result.

Use the same output constraints: 1920-by-1080 or 1280-by-720, a declared frame rate, maximum duration, caption format, and audio loudness target. Record all model identifiers, prompts, temperature/reasoning settings, API calls, token usage, local CPU/GPU, wall-clock time, retries, failures, and human interventions. For Code2Video, use the official repository and its documented Manim setup [1]. For Prompt2Render, freeze a Git tag and a configuration file. If APIs differ, report those differences rather than hiding them.

| Outcome family | Metric | How to measure |
|---|---|---|
| Reliability | First-pass compile/render success | Successful sections divided by attempted sections before repair |
| Reliability | Final accepted success | Videos passing all declared blocking gates divided by attempted videos |
| Reliability | Blocking-defect escape rate | Expert-annotated blocking defects present in final output |
| Repair | Repair success rate | Failed artifacts that pass after repair divided by repair attempts |
| Repair | Repair cost | Additional calls, tokens, seconds, and regenerated sections |
| Repair | Loop rate | Runs hitting retry budget or repeating the same finding |
| Layout | Collision/off-frame rate | Programmatic audit plus blinded expert annotation |
| Semantics | Claim-to-visual correspondence | Two or more blinded annotators rate whether each visual supports the narrated claim |
| Mathematics/technical | Domain invariant accuracy | Topic-specific executable checkers and expert annotation |
| Timing | Word/caption drift | Absolute difference between intended cue, forced alignment, and final caption timing; report median, p95, max |
| Audio | Caption word error and cue coverage | Compare captions to authored script and independent ASR; report WER and uncovered words |
| Visual quality | Code2Video-style five dimensions | Use the same prompt, model, sampling, and blinding protocol as closely as possible [2] |
| Learning | TeachQuiz gain | Reproduce the unlearning/video protocol with fixed questions and multiple seeds [2] |
| Human learning | Pre/post-test gain and delayed retention | Randomized or counterbalanced study with human learners, not only a VLM |
| Efficiency | Wall time, tokens, API cost, peak memory | Measure cold and warm runs separately |

The primary analysis should use paired topic-level comparisons. Report means and medians with 95% confidence intervals, paired bootstrap intervals or mixed-effects models, effect sizes, and per-topic distributions. Do not report only an average score. A system that produces a beautiful result on 60% of topics and fails silently on 40% has a different research profile from one that produces slightly plainer videos but blocks the failures.

## 6. Required ablations

The core ablation should isolate the claimed reliability mechanisms rather than merely remove arbitrary plugins.

| Condition | Removed component | Main question |
|---|---|---|
| A | Full Prompt2Render | Reference condition |
| B | Pedagogy review/revision | Does shift-left review improve content and learning measures? |
| C | Deterministic spatial/execution verification | Does the bounded verifier reduce escaped defects? |
| D | Repair router and re-verification | Does diagnosis → repair → re-check improve final acceptance? |
| E | Word-level alignment and audio-derived timing | What synchronization defects arise from section-duration or end-padding timing? |
| F | All deterministic gates, with logging retained | How much quality is attributable to generation rather than verification? |
| G | Same renderer/API with only the LLM storyboard changes | Separates API constraints from planning/model effects |

For every ablation, keep topic, script, model, temperature, hardware, output settings, and retry budget fixed. The repair ablation must include intentionally seeded violations and naturally occurring failures, and it must show that a repair is not counted as successful until the relevant verifier passes again.

## 7. Human annotation and learning study

A publication-grade study needs more than screenshots and an LLM judge. Build an annotation rubric in which each topic has a gold fact sheet and a list of required visual claims. Two independent subject-matter annotators should rate factual correctness, mathematical validity, visual correspondence, sequence/order correctness, prerequisite appropriateness, pacing, caption readability, and whether a misconception is introduced. Use a five-level scale from “fully correct” to “blocking error,” define examples before annotation, blind annotators to system identity, and report inter-rater agreement such as Cohen's kappa or Krippendorff's alpha.

For learning outcomes, recruit participants appropriate to the target audience, preregister the primary outcome, and compare at least Prompt2Render, Code2Video, and a human-authored or human-curated reference. A reasonable minimum pilot is a power-informed sample rather than an arbitrary small number; the final sample size should follow an a priori power calculation based on the chosen learning-gain effect. Use pre-test, immediate post-test, delayed retention, transfer questions, perceived clarity, cognitive load, and preference. Counterbalance video order where participants view multiple systems, and ensure the test questions are not copied from the narration verbatim.

TeachQuiz can be included as a reproducible automated evaluation, but it must be reported separately from human learning. Its unlearning success, prompt, model, video sampling, question set, and repeated-run variability must be disclosed. A VLM answering a question after viewing a video is not itself evidence that human learners acquired durable knowledge.

## 8. Threats to validity

| Threat | Why it matters | Mitigation |
|---|---|---|
| Benchmark leakage | MMMC is derived from existing educational videos and may overlap with model training data | Use held-out author-created topics and report both MMMC and a novel test set |
| Judge bias | VLM judges may favor a visual style or be sensitive to system identity | Blind videos, randomize order, use multiple judges, and validate with humans |
| TeachQuiz instability | Unlearning may fail; model answers may be memorized or prompt-sensitive | Report unlearning success, multiple seeds/models, and human outcomes separately |
| Topic-selection bias | Prompt2Render's constrained primitives may favor algorithms and diagrams | Include out-of-domain and failure-inducing topics; report supported-topic coverage |
| Model/API confounding | Different LLMs, versions, quotas, and prompts can dominate results | Freeze model IDs, prompts, sampling settings, and record all calls |
| Repair-budget confounding | More retries can inflate quality and cost | Match or explicitly sweep retry budgets and report marginal cost |
| Silent verifier gaps | Stubs that always pass can create false confidence | Mark stubs as unavailable; make blocking checks fail closed where appropriate |
| Rendering/hardware variance | FFmpeg, fonts, GPU encoders, and OS versions change output | Containerize where possible; publish environment lockfiles and technical metadata |
| Authorship and script quality | A hand-edited Prompt2Render script is not comparable to an unattended Code2Video run | Define separate topic-to-video and fixed-script tracks |
| Human-study underpowering | Small convenience samples produce unstable learning conclusions | Preregister hypotheses and perform power analysis |
| Reproducibility drift | Active uncommitted files and external APIs can change behavior | Tag a release, archive prompts/configs, cache inputs, and publish manifests |

## 9. Journal fit and realistic submission strategy

**IEEE Transactions on Learning Technologies (TLT)** is the best fit if the paper makes a substantive technical/design contribution and convincingly demonstrates support for learning. Its official scope explicitly includes authoring tools for learning materials and states that technology evaluations are appropriate when the technology is novel or yields significant technical insight [3]. A Prompt2Render submission should therefore include the constrained API and verification architecture, but it must also include human or otherwise credible learning evidence.

**Computers & Education** is appropriate only if the manuscript is principally about educational use, learning outcomes, and broadly relevant pedagogical implications. Its official scope says that implementation papers should focus on context of use, interface/usability, user experience, and impacts on learning and teaching, and warns that a small-scale evaluation of one system in one specialist domain is insufficient [4]. A purely technical harness paper would be a poor fit unless the educational study is substantial.

**IEEE Transactions on Multimedia (TMM)** is a plausible technical venue if the paper emphasizes multimedia generation, controllable rendering, synchronization, verification, and reproducibility. Its official scope covers multimedia systems/software/integration and encourages authors to publish code and data needed to reproduce results [5]. It is less suitable if the contribution is primarily a pedagogy intervention without a strong multimedia-method contribution.

The labels “Q1” and “Q2” should not be treated as permanent facts. Quartile depends on the ranking database, subject category, and year. At submission time, verify the current JCR or Scopus/SCImago classification required by the user's institution. The scope fit above is more stable and more important than a generic quartile label.

| Venue | Best manuscript emphasis | What is currently missing |
|---|---|---|
| IEEE TLT | Technical learning-authoring system plus demonstrated learning support | Human study, pedagogy validity, and strong system comparison |
| Computers & Education | Learning outcomes, usability, instructional value, broad educational relevance | Proper educational design; architecture should be secondary |
| IEEE TMM | Constrained multimedia generation, synchronization, deterministic verification, reproducibility | Strong multimedia baselines and quantitative technical evaluation |

## 10. Release and reproducibility checklist

Before submission, create a tagged release containing a clean installation path, a locked dependency file, supported Python/FFmpeg/OS versions, a no-network smoke test, and a deterministic fixture project. Separate unit tests, mocked integration tests, and real external-service tests. Add a command that prints the resolved plugin graph and fails if a disabled or experimental renderer appears in the default path.

The release should include the exact prompts, configuration, model IDs, retry budgets, topic packets, gold fact sheets, generated manifests, raw findings, repair histories, QC outputs, and analysis scripts. For every video, store a provenance record containing source script hash, scene-code hash, renderer version, font set, audio model, alignment model, FFmpeg version, hardware, wall time, token usage, and final gate outcome. Do not include API secrets. Cache any legally redistributable inputs and document how a researcher can substitute local paths when assets cannot be redistributed.

The harness documentation must be synchronized with the code. In particular, it should no longer describe semantic and lifecycle verification as if they were substantive checks if they remain stubs. It should distinguish “implemented,” “implemented but experimental,” and “not implemented.” The final paper should include an artifact appendix showing at least one naturally occurring defect, the finding, the selected repair, the re-render, and the verifier result after repair.

## 11. Recommended next sequence

First, freeze the current default Scenekit path and remove all mixed-version archives and generated artifacts from the release branch. Verify the graph on Windows and run a clean installation from a fresh environment. Second, implement or explicitly disable the semantic and lifecycle gates; a gate that always passes must not be presented as a verifier. Third, create a 12-topic pilot with gold fact sheets and intentionally seeded violations. Fourth, run the full Prompt2Render ablation matrix and record final-output metrics. Fifth, reproduce Code2Video on the same pilot topics using its official repository and declared settings. Sixth, run blinded expert annotation and a small preregistered learning pilot. Only after these steps should the manuscript make comparative claims.

The immediate publication decision is therefore: **do not submit the current repository as a Q1/Q2 empirical paper yet**. Submit only after the evidence package is complete. A workshop, systems/demo paper, or software/artifact paper could be considered earlier if it clearly presents the repository as an engineering prototype and reports limitations honestly, but that would be a different claim from a journal article demonstrating superior educational video quality.

## References

[1]: https://github.com/showlab/Code2Video "Show Lab Code2Video repository and README"

[2]: https://arxiv.org/html/2510.01174v1 "Chen, Lin, and Shou, A Code-centric Paradigm for Educational Video Generation, arXiv:2510.01174v1"

[3]: https://ieee-edusociety.org/publication/about-publications/tlt "IEEE Transactions on Learning Technologies: scope and publication description"

[4]: https://www.sciencedirect.com/journal/computers-and-education "Computers & Education: aims and scope"

[5]: https://signalprocessingsociety.org/publications-resources/ieee-transactions-multimedia/about-tmm "IEEE Transactions on Multimedia: scope and reproducible research guidance"
