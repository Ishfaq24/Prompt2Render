# Prompt2Render — Architectural Audit (Phase 0)

**Status:** read-only survey. No production code was modified to produce this document.
**Date:** 2026-08-25
**Commit audited:** `e30043e1378a8c9cd948a14b244317803192d70d` (`main`)

This is the baseline record required before any architectural transformation. Every claim
below was verified against source; file:line references are given so each can be re-checked.

---

## 0. Recorded baseline

| Property | Value |
|---|---|
| Commit | `e30043e` (`main`, clean tree except generated `self_correction_report.json`) |
| Tests | **139 passed**, 0 failed, 0 skipped |
| Warnings | 1 (`cloup`/Click `__version__` DeprecationWarning — third-party, unrelated) |
| Python | 3.13.7 |
| Manim | Community Edition 0.19.0 |
| Platform | Windows 11 (10.0.26200) |
| Source size | 85 `.py` files, 31,663 LOC (excluding `harness_old*`) |
| Largest module | `harness/plugins/renderer_manim/__init__.py` — 2,272 LOC |
| CLI subcommands | 23 (`new draft doctor models voices serve voice harness align scenes stills plan encode finish check build auto import placeholders manim assemble publish animate`) |
| Benchmark command | **none** |
| Installed but unused | `cv2`, `numpy`, `scipy`, `jsonschema`, `pydantic` |

Reproduce with: `pytest prompt2render/tests -q`

---

## 1. Current architecture

Two generations of pipeline coexist.

**Legacy path** (`scenes.py`, `stills.py`, `timeline.py`, `encode.py`, `finish.py`) — direct
module calls driven by CLI subcommands.

**Harness path** (`harness/`) — a plugin DAG. `SceneContext` is the single mutable state
object; plugins declare dependencies/effects and the loader topologically orders them.
This is the active architecture and the subject of this audit.

```
prompt/script.md
  → planner_script → chunker_scene → planner_pedagogy → reviser_script → verifier_pedagogy
  → planner_llm (storyboard) ─┐
  → planner_visual ───────────┤
  → generator_voice → generator_align → planner_audio (narration timing)
  → verifier_storyboard ──────┘
  → generator_code → verifier_execution
  → renderer_stills  (OR renderer_manim — mutually exclusive)
  → verifier_lifecycle / verifier_semantic / verifier_spatial / verifier_temporal
  → feedback_hitl
  → generator_timeline → renderer_encode → renderer_finish
  → verifier_audio → verifier_final_qc → generator_publish
```

### 2. Plugin dependency graph (resolved default order, 25 plugins)

| # | Plugin | Gate | Depends on | Produces |
|---|---|---|---|---|
| 1 | `planner_script` | ✔ | `prompt` | `script_artifact` |
| 2 | `chunker_scene` | ✔ | `prompt`, `script_artifact` | `scene_plan` |
| 3 | `planner_pedagogy` | ✔ | `scene_plan` | `pedagogy_review` |
| 4 | `reviser_script` | ✔ | `scene_plan`, `pedagogy_review` | `script_revision` |
| 5 | `verifier_pedagogy` | ✔ | +`script_revision` | `pedagogy_verified` |
| 6 | `planner_llm` | ✔ | `scene_plan`, `pedagogy_verified` | `storyboard_plan` |
| 7 | `planner_visual` | ✔ | `scene_plan`, `pedagogy_verified` | `animation_plan` |
| 8 | `generator_voice` | ✔ | `scene_plan`, `animation_plan` | `audio_artifacts` |
| 9 | `generator_align` | ✔ | `audio_artifacts` | `alignment_artifact` |
| 10 | `planner_audio` | ✔ | `scene_plan`, `alignment_artifact` | `narration` |
| 11 | `verifier_storyboard` | ✔ | `scene_plan`, `storyboard_plan`, `narration` | `storyboard_verified` |
| 12 | `generator_code` | ✔ | `scene_plan`, `narration`, `storyboard_verified` | `code_artifacts` |
| 13 | `verifier_execution` | ✔ | `code_artifacts` | `static_code_verified` |
| 14 | `renderer_stills` | ✘ | `code_artifacts` | `render_artifacts` |
| 15 | `verifier_lifecycle` | ✘ | `code_artifacts`, `scene_plan` | `check_results` |
| 16 | `verifier_semantic` | ✔ | +`render_artifacts` | `check_results` |
| 17 | `verifier_spatial` | ✘ | `render_artifacts` | `check_results` |
| 18 | `verifier_temporal` | ✔ | `render_artifacts`, `code_artifacts`, `scene_plan` | `check_results` |
| 19 | `feedback_hitl` | ✘ | `render_artifacts` | `hitl_annotations` |
| 20 | `generator_timeline` | ✔ | `render_artifacts`, `audio_artifacts`, `alignment_artifact` | `timeline_plan` |
| 21 | `renderer_encode` | ✔ | `timeline_plan` | `video_artifacts` |
| 22 | `renderer_finish` | ✔ | `video_artifacts` | `final_video` |
| 23 | `verifier_audio` | ✘ | `final_video`, `narration`, `render_artifacts` | `check_results` |
| 24 | `verifier_final_qc` | ✔ | `final_video` | `final_qc` |
| 25 | `generator_publish` | ✔ | `final_qc` | `publish_packet` |

Ordering rules (`harness/loader.py`): a plugin is schedulable when every dependency is in
`PRESEEDED_FIELDS` (`:45-60`) or already produced. Ties break on registry order (`:302`).
`MERGEABLE_EFFECTS = {"check_results"}` (`:42`) exempts verifiers from the single-producer
rule (`:208-232`); everything else must have exactly one producer.

---

## 3. State ownership

`SceneContext` (`harness/context.py:171-327`) is a flat dataclass. Ownership is by
`declare_effects()` convention only — nothing enforces that a plugin writes only what it declares.

Owned fields: `scene_plan`(chunker_scene), `narration`(planner_audio),
`code_artifacts`(generator_code | generator_manim), `render_artifacts`(renderer_stills |
renderer_manim), `audio_artifacts`(generator_voice), `video_artifacts`(renderer_encode),
`storyboard_plan`(planner_llm), `pedagogy_review`(planner_pedagogy),
`hitl_annotations`(feedback_hitl), `history`(runner), `repair_context`/`repair_records`(repair_router).

**Gaps relative to a grounded, IR-based pipeline** — there is no field for:
an intermediate representation (the closest is `storyboard_plan: dict[str, Any]`, untyped
LLM-shaped JSON), quality scores (no numeric field exists anywhere), rendered-output
observations, provenance (`HistoryEntry:155` records plugin/time/effects/ok only — no input
hash, model id, token count or cost), or cross-run experience/memory (`repair_context` is
per-run and is actively *deleted* on success, `runner.py:744-748`).

---

## 4. LLM vs deterministic boundaries

**LLM-driven:** `planner_script` (script drafting), `planner_pedagogy` / `reviser_script`
(pedagogy review + revision), `planner_llm` (storyboard), `generator_code` /
`GeneratorManimPlugin` (scene source), `verifier_semantic` (the only LLM/VLM verifier,
`gemini-3.7-flash`).

**Deterministic:** `chunker_scene`, `planner_audio`, `verifier_storyboard`,
`verifier_execution` (AST), `verifier_lifecycle` (AST), `verifier_spatial` (bbox
pass-through), `verifier_temporal` (ffprobe + regex), `verifier_audio` (Whisper ASR),
`verifier_final_qc`, all renderers, the whole repair-routing table.

The boundary is currently drawn in a defensible place, with one significant exception:
**the entire choreography and layout of a Manim scene is LLM-authored free text** with no
deterministic post-check of geometry (see §7, §14).

---

## 5. Renderer boundaries

There is **no renderer capability model**. A repo-wide grep for
`capability|capabilities|renderer_profile` in `harness/` returns nothing.

Backend selection is an all-or-nothing, process-wide swap enforced by an *effect-name
collision*: `renderer_stills` and `renderer_manim` both declare `render_artifacts`, so the
loader rejects the DAG if both are enabled (`config.yaml:88-92` documents this).
The `--manim` flag (`prompt2render.py:251-300`) flips enablement and then **monkey-patches**
`GeneratorManimPlugin` over `generator_code` after `build_plugins()` — that class is not in
`REGISTRY` at all (`harness/plugins/__init__.py:73-142`).

`--manim` additionally disables `generator_timeline`, `renderer_encode`, `renderer_finish`,
`generator_publish`, `verifier_audio` and `verifier_final_qc` — i.e. **the entire production
tail. Manim mode cannot currently produce a final video and is an experimental branch, not a
shippable path.**

A real per-section routing heuristic *does* exist — `scenes.select_renderer` (`scenes.py:917-944`,
tag + keyword based) — but it lives in the legacy path and is unreachable from the harness.

---

## 6. Existing validation

| Verifier | Kind | Checks | Gate |
|---|---|---|---|
| `verifier_pedagogy` | LLM-assisted | score + blocking pedagogy issues | ✔ |
| `verifier_storyboard` | deterministic | section coverage, ≥1 state, `cue` in range + monotonic, non-empty `visual`/`transition`, `validate_motion_ops` | ✔ |
| `verifier_execution` | deterministic (AST) | artifact exists/non-empty, backend detect, `validate_manim_source` or `validate_scene_source`, writes `.trace.json` | ✔ |
| `verifier_semantic` | **LLM/VLM** | data consistency, invariants, illegal states, pedagogy, layout (only if preview attached) | ✔ |
| `verifier_spatial` | pass-through | re-surfaces `RenderArtifact.audit`; recomputes nothing | ✘ |
| `verifier_lifecycle` | deterministic (AST) | `k.array` length changes between adjacent scenes | ✘ |
| `verifier_temporal` | deterministic | ffprobe duration vs narration (±1.5s), regex cue-sync | ✔ |
| `verifier_audio` | deterministic (ASR) | caption drift over final video | ✘ |
| `verifier_final_qc` | deterministic | `qc.check()` gates | ✔ |

**Test coverage gaps:** no test file exists for `verifier_semantic`, `verifier_spatial`,
`verifier_lifecycle`, `verifier_audio`, `verifier_final_qc`, `feedback_hitl`, or `qc.py`.

---

## 7. Existing repair loop

`HarnessRunner._run_one` (`runner.py:243-644`) runs a plugin, then while failures remain:
emits `check.failed` **synchronously** (so `repair_router` repairs in-band), then *always
re-runs the verifier itself* rather than trusting the router's `resolved` claim
(`:476-498`). Bounded by `max_reverify_attempts=3` (`:56`).

The outer loop (`run()`, `:83-204`) additionally **rewinds** the pipeline when a repair
invalidated earlier artifacts, computing
`trigger = new_repairs | stale_renders | missing_renders` (`:155`) and jumping back to
`_rewind_target_index` (`:210-237`), bounded by `MAX_SAME_REWINDS=3` / `MAX_TOTAL_REWINDS=10`.

`repair_router` (`policy.py:56-67`) maps `finding_type` → target plugin, with sub-tables for
`audio_visual_mismatch` (by `mismatch_subtype`) and `vlm_post_render_defect` (by category).
Budget is keyed `scene:finding_type:source`, capped by `max_repair_cycles=3`.

This is a genuine strength: **verification is independent of generation, and the router's
optimistic "resolved" is never trusted.**

---

## 8. Existing provenance

Persisted under `<project>/build/harness/`: `log.jsonl` (per-invocation, with input/output
context hashes), `repair_log.jsonl`, `storyboard.json` (with `prompt_sha256`),
`provenance/storyboard.prompt.txt`, `provenance/script.{original,planned,revision_NN}.md`,
`pedagogy_review.json`, `pedagogy_history.json`, and `out/self_correction_report.json`.

**Not persisted:** model identity/version, token or cost accounting, per-scene render timings,
prompt→response pairs for any stage except `planner_llm`, or any cross-run index. `token_usage`
is a field in the log schema that no caller ever populates (`runner.py:331,594,632`).

---

## 9. Existing motion model

`harness/motion.py:24-32` defines a 7-op vocabulary — `Create`, `Write`, `FadeIn`, `FadeOut`,
`Transform{target,into}`, `MoveTo{target,anchor}`, `Highlight` — deliberately excluding timing.
`validate_motion_ops` (`:35-89`) additionally requires every target/into/anchor to be a valid
non-keyword Python identifier, since it becomes `self.<name>` in compiled output.

It is authored into the storyboard prompt (`planner_llm:492-504`), normalised (`:229-243`),
validated (`:428`) and **hard-gated** by `verifier_storyboard`. See F1 in §12 for why none of
this reaches the rendered output.

---

## 10. Existing temporal alignment

`align.py` produces per-sentence `{i, text, start, end, words[]}`; `align.load()` also exposes
`audio_dur`. `_load_timing` (`renderer_manim:436-536`) converts this into
`(duration, timing_table, sentences)`.

Three different definitions of "how long is this section" are currently in use:

| Definition | Used by | Includes inter-sentence silence? |
|---|---|---|
| `sum(sentence durations)` | `_load_timing:475`, `verifier_temporal:198` | **No** |
| `sentences[-1]["end"]` | `verifier_execution:204-227` | **Yes** |
| `audio_dur` | `_load_timing` fallback only | Yes |

---

## 11. Strengths (preserve these)

1. **Clean plugin DAG with declared effects** — ordering is derived, not hardcoded, and
   double-production is rejected at load time.
2. **Verification is independent of generation**, and re-verification never trusts the repairer.
3. **Bounded, instrumented repair** with rewind, cycle caps and stagnation detection.
4. **A real deterministic layout critic exists** (`scenekit.audit`) with its own adversarial
   regression suite (`tools/test_layout_audit.py`, 32 synthetic frames).
5. **Typed findings** with categories/severities and a declarative routing table.
6. **Structured provenance already exists** for storyboard, script revisions and repair cycles.
7. **HITL already works end-to-end** and is documented.
8. Deterministic AST validators for both backends, run *before* render.

---

## 12. Weaknesses (verified)

| # | Finding | Evidence |
|---|---|---|
| **F1** | **Motion compiler is dead code.** Fully implemented, 29 passing tests, **zero production callers**. `motion` is planned, normalised, validated and hard-gated, yet affects no output. `_splice_construct_method` has no callers at all, not even tests. | `renderer_manim:539-960`, `_build_setup_prompt:1615`; `_generate_one:1921-1936` |
| **F2** | **Every Manim scene is instructed to end early.** `duration` excludes inter-sentence silence but the prompt asserts the total *must equal* it. Measured on `History and Definition of Pi`: **13.50s missing across 342.08s (3.9%)**, per-section 1.28–3.26s. | `_load_timing:475`, `_build_prompt:1464` |
| **F3** | **No visual grounding.** Nothing samples a rendered video frame anywhere. Evidence surface = matplotlib bbox math on *stills* + one preview PNG. `cv2` is installed but never imported. | repo-wide grep; `visuals.py:222-238` |
| **F4** | **`verifier_spatial` is inert on the Manim path** — `renderer_manim` never sets `RenderArtifact.audit`, so it always yields `skip`; its gate is `False`, so the degradation is silent. | `verifier_spatial:206-210`; `renderer_manim:1031,1059,1151` |
| **F5** | **Repair lifecycle events are never delivered.** `repair.started`/`repair.finished` are absent from `VALID_EVENTS`, so every emit raises and is swallowed by a bare `except Exception: return`. `repair.triggered` is declared but emitted by nothing. | `events.py:41-48`; `repair_router:430,557,567,622-637` |
| **F6** | **`verifier_temporal` is absent from `config.yaml`** — silently `enabled=True` with a hard blocking gate, invisible to config readers and not neutralised by the ablation runner. | `config.yaml`; `verifier_temporal:599` |
| **F7** | **Two conflicting narration-duration definitions** (see §10) — `verifier_execution`'s docstring warns it must agree with the compiler; nothing enforces agreement with `verifier_temporal`. | `verifier_temporal:198` vs `verifier_execution:204-227` |
| **F8** | **`verifier_lifecycle` mislabels its subtype** as `mismatch_subtype="temporal_mismatch"` on a lifecycle finding. **Corrected during Phase 0.5:** this does *not* misroute today — `decide()` only reads `mismatch_subtype` when `finding_type == "audio_visual_mismatch"`, and lifecycle sets `lifecycle_violation`, so routing is provably identical with and without the key. It is a latent trap (it would misroute the moment `lifecycle_violation` gains a subtype table), not a live defect. | `verifier_lifecycle:345`; `policy.py:139-157` |
| **F9** | **Dead route:** `vlm_post_render_defect` has a routing table entry and a category sub-table, but **no plugin emits it**. | `policy.py:164,247` |
| **F10** | **`verifier_semantic` gates on possibly-stale previews.** `has_preview` is a bare `Path.exists()` with no freshness check against the code artifact. Outside repair it judges whatever PNG happens to be on disk. | `verifier_semantic:405-415` |
| **F11** | **`finding_type` is not a `Finding` field** although the entire routing table keys on it — verifiers hand-add it to the raw dict. The typed layer and the routing layer are disjoint. | `finding.py:113-122`; `policy.py:125-130` |
| **F12** | **No renderer capability model**; `--manim` disables the production tail → not shippable (see §5). | `prompt2render.py:251-300` |
| **F13** | **`GeneratorManimPlugin` is not registered** — monkey-patched over `generator_code` post-build. | `plugins/__init__.py:73-142` |
| **F14** | **RAG is a keyword matcher over ~10 hardcoded SceneKit snippets**, disabled by default, and targets a vocabulary irrelevant to Manim. Not embedding-based (by explicit design). | `retriever_manim_rag:44,266-341`; `config.yaml:57` |
| **F16** | **No benchmark harness.** `ablation_runner.py` is not CLI-wired and counts findings without separating pass from fail; `manim_experiment_runner.py` requires `data/mmmc_subset.json`, absent from the repo → the committed experiment protocol is unexecutable. | `tools/` |

---

## 13. Technical debt (F15)

- `harness_old/` (2,172 LOC) + `harness_old_2/` (2,299 LOC) — **4,471 LOC dead**, zero inbound references.
- `SceneContext.object_table` — declared, never populated (`context.py:139` admits it).
- **7 phantom DAG tokens** — `script_artifact`, `animation_plan`, `alignment_artifact`,
  `timeline_plan`, `final_video`, `final_qc`, `publish_packet` are declared as effects but are
  **not `SceneContext` fields**. The loader never checks that an effect names a real field.
- Duplicate validator: public `validate_manim_source` (`scenes.py:608`) vs private
  `_validate_manim_source` (`:1012`) — potential drift.
- `docs/` exists in **two locations** (`prompt2render/docs/` 8 files, `C:\fdx-studio\docs\` 5 duplicates).
- `verifier_execution` **writes to the artifact it verifies** (BOM stripping, `:292`).
- `write_self_correction_report(final_pass=True)` is never called anywhere.
- `visuals.manim_scene` docstring still claims the file is "hand-authored only" — stale.
- `llm.py` exposes **no temperature or seed control** — an unmanaged nondeterminism source.
- `projects/*/build/` is gitignored → no tracked home for golden/benchmark artifacts.

---

## 14. Duplicate responsibilities

- **Duration computation** — three definitions across three modules (§10, F7).
- **Manim source validation** — two near-identical functions in `scenes.py`.
- **HITL file reading** — `feedback_hitl` and `hitl_status_sets` (`renderer_manim:48`) both
  parse `hitl_feedback.json` independently, for different purposes.
- **Layout rules** — encoded twice as prose: `_build_prompt` §4/§5 (`renderer_manim:1467-1533`)
  and `MANIM_API_DOC` (`scenes.py:851-914`), for two different code paths.
- **Pedagogy** — split across root `pedagogy.py` and `harness/plugins/pedagogy.py` (this split
  is deliberate and documented, and is *not* debt).

---

## 15. Implicit contracts (undeclared, load-bearing)

1. `finding_type` must be hand-added to every finding dict; absent it, the router falls back to
   `_DEFAULT_FINDING_TYPE[source_plugin]` (F11).
2. `revert_scene`/`regenerate_one` are **duck-typed**, discovered by `hasattr`
   (`repair_router:479-488`). Only 4 plugins implement them; every other repair target silently
   degrades to a full `target.run(ctx)`.
3. Exactly one of `renderer_stills`/`renderer_manim` may be enabled — enforced only by an
   effect-name collision, not by any explicit rule.
4. `motion` target/into/anchor values must be valid Python identifiers because they are
   interpolated as `self.<name>`.
5. Manim rejects `self.wait(0)`; the cue map must suppress zero-gap waits.
6. `hitl_feedback.json`: `"accept"` is a **hard regeneration lock**, not merely an approval.
7. A verifier emitting no `check_results` entry is interpreted as *pass* (`runner.py:354-365`).

---

## 16. Target architecture

```
Educational intent
  → Pedagogical planning → Storyboard
  → AnimationIR                      (typed, renderer-neutral, versioned, hashed)
  → Semantic animation planning      (CONTEXT→ANTICIPATION→ACTION→CONSEQUENCE→HOLD)
  → Motion compilation (deterministic) + Temporal compilation (narration-authoritative)
  → Renderer capability analysis → renderer selection (Manim | Matplotlib | hybrid)
  → Executable artifact → rendered video
  → Visual observation               (frame sampling, object/motion traces)
  → Multi-verifier: semantic | temporal | spatial | motion | continuity | pedagogical
  → Quality score → PASS ─→ final artifact
                  └ FAIL ─→ diagnosis → targeted repair at the earliest wrong representation
                                      → HITL escalation when policy requires → ↺
```

The decisive shift is **F3**: today the system can only answer *"did the Python execute?"*.
Answering *"did the animation teach what was intended?"* requires a machine-checkable statement
of intent (AnimationIR) plus observation of what actually rendered, and comparison of the two.

---

## 17. Migration plan

Staged, each phase gated by INSPECT → DESIGN → IMPLEMENT → TEST → REGRESSION → REVIEW →
DOCUMENT → CHECKPOINT.

- **Phase 0 (this document)** — audit + baseline.
- **Phase 0.5** — fix the live defects F2, F5, F6, F7, F8, F9, F10, F11.
- **Tier 1 (Phases 1-3)** — AnimationIR; storyboard→IR bridge + validation gate; semantic
  animation planner. *A richer op vocabulary is the specific fix for the sparse-scene failure
  that caused the compiler to be reverted — 7 ops with `MIN_STATES=2` was too thin.*
- **Tier 2 (Phases 4-9)** — motion compiler (re-wire F1 **behind a config flag, default off**);
  TemporalIR; Manim-as-compiler; pattern RAG (replacing F14); renderer capability profiles +
  router + hybrid, which must also resolve F12 and F13.
- **Tier 3 (Phases 10-15)** — unified multi-verifier; **closed-loop visual grounding** (F3,
  deterministic CV first, VLM only for semantic judgments); motion traces; reproducible weighted
  quality scoring; verifier-driven repair with regression detection; experience memory.
- **Tier 4 (HITL)** — three modes (`AUTONOMOUS`/`HUMAN_ON_FAILURE`/`HUMAN_APPROVAL`) **extending
  the existing `hitl_feedback.json` contract, never a second system**; versioned artifacts;
  every human action a provenance record.
- **Tier 5 (Phases 16-25)** — benchmark suite + real CLI (F16); baselines; ablations; human-eval
  protocol; regression + reproducibility; cleanup (F15); final documentation.

**Backward-compatibility constraint:** the stills pipeline is the shippable default and must keep
working unchanged throughout. The Manim path is experimental until F12 is resolved.

---

## 18. Existing HITL contract (must be extended, not replaced)

Interface: `<project>/hitl_feedback.json`, keyed by 2-digit stem.

```json
{ "04": { "status": "reject", "reason": "Text overlaps the arrows; move the label up-left." } }
```

Two independent consumers:
1. `feedback_hitl` (`plugins/feedback_hitl/__init__.py:47-62`) — each `"reject"` becomes a
   BLOCKING `feedback_hitl` finding routed to the code generator, and is appended to
   `context.hitl_annotations` as `{stem, reason}`. Gate defaults `False` (`:72`) so an automated
   run never blocks waiting for a human.
2. `hitl_status_sets` (`renderer_manim:48-83`) — returns `(rejected, locked)`, where
   **`"accept"` is a hard lock**: a locked stem is never regenerated or re-rendered even if an
   unrelated staleness heuristic would otherwise sweep it in.

Documented in `HITL_WORKFLOW.md`. Any future HITL work must preserve both consumers and the
existing `accept`/`reject` semantics.

---

## Appendix — measured evidence for F2

`projects/History and Definition of Pi`, per section:

| stem | sum(dur) | true end | shortfall |
|---|---|---|---|
| 01 | 60.95 | 64.21 | 3.26 |
| 02 | 58.28 | 60.20 | 1.92 |
| 03 | 55.53 | 58.41 | 2.88 |
| 04 | 57.07 | 58.99 | 1.92 |
| 05 | 56.66 | 58.90 | 2.24 |
| 06 | 40.09 | 41.37 | 1.28 |
| **total** | **328.58** | **342.08** | **13.50 (3.9%)** |
