# Prompt2Render Harness Architecture

**Prompt2Render: Artifact-Centric Self-Correcting Agentic Harness for
LLM-Driven Educational Video Generation**

This document describes (1) the current harness architecture as implemented in
this repository, and (2) the upgraded architecture that makes the verification
report actionable memory for the next regeneration. It is the Phase-1 audit
deliverable; behavioral details live in the companion docs
(`SELF_CORRECTION.md`, `VERIFICATION.md`, `REVISION_MODEL.md`,
`RESEARCH_EVALUATION.md`).

---

## 1. Current architecture (as audited)

### 1.1 Execution path: `prompt2render harness <slug>` → final video

```
prompt2render.py (root CLI)
  └─ cmd_harness(slug)
       ├─ load_config() → per-plugin enable/gate_override          (harness/loader.py)
       ├─ build_plugins(config) → resolved plugin DAG              (harness/loader.py)
       │     order comes from declare_dependencies()/declare_effects(),
       │     not a hardcoded list
       ├─ StructuredLogger  → build/harness/log.jsonl              (harness/logging_.py)
       ├─ EventBus          → in-process lifecycle events          (harness/events.py)
       ├─ EventJournal      → build/harness/events.jsonl           (harness/journal.py)
       ├─ build_repair_controller(plugins, ...)                    (harness/loader.py)
       │     RepairController owns the entire repair lifecycle     (harness/repair_controller.py)
       ├─ workspace.cleanup_candidates()                           (harness/workspace.py)
       └─ HarnessRunner(plugins, ..., repair_controller).run(ctx)  (harness/runner.py)
             per stage: _run_one()
               ├─ plugin.run(ctx)                       (hard failure → fatal)
               ├─ _widen_reverification_for_regressions (scene-plan fingerprints)
               ├─ _failures(ctx, plugin)                (blocking findings)
               ├─ if fails: _repair → RepairController.repair_scene(...)
               ├─ gate decision (GateFailure if hard gate still fails)
               └─ log_invocation → log.jsonl
             after all stages:
               └─ _check_final_video_reachable()        (final-video gate)
```

Default plugin order (stills path, `docs/HARNESS.md`):

```
planner_script → chunker_scene → planner_semantic → planner_temporal →
planner_visual → planner_audio → retriever_manim_rag → generator_voice →
generator_align → generator_code → renderer_stills → verifier_execution →
verifier_semantic → verifier_storyboard → verifier_layout → verifier_spatial →
verifier_temporal → verifier_lifecycle → verifier_animation_ir →
verifier_pedagogy* → generator_timeline → renderer_encode → renderer_finish →
verifier_audio → verifier_final_qc → generator_publish
(* whole-video verifiers: verifier_audio, verifier_pedagogy)
```

`--manim` swaps the backend: `generator_manim` + `renderer_manim` +
`renderer_manim_finish` + `verifier_manim_final_qc` + `observer_visual` +
`verifier_motion`, disabling the stills/timeline/encode equivalents. Exactly
one backend may be enabled; the loader rejects effect collisions.

### 1.2 Component inventory

| Concern | Module(s) | Notes |
|---|---|---|
| Planner (pedagogy/script) | `plugins/planner_script`, `planner_llm`, `planner_semantic`, `planner_temporal`, `planner_visual`, `planner_audio`, `pedagogy.py` | LLM narration draft + deterministic animation/semantic/temporal contracts |
| Scene chunking | `plugins/chunker_scene` → `project.parse_script` | produces `scene_plan` |
| Generator (SceneKit) | `plugins/generator_code` → `scenes.generate` | one Gemini call per section; internal preflight retries; continuity anchoring |
| Generator (Manim) | `plugins/renderer_manim` (`GeneratorManimPlugin`) | report-driven regeneration already wired via `scene_report.build_repair_context` |
| Renderer (stills) | `plugins/renderer_stills` → `stills.render_many` (matplotlib) |
| Renderer (Manim) | `plugins/renderer_manim` → `visuals.manim_scene` | one clip per section; previews via `harness/preview.py` |
| Deterministic preflight | `plugins/verifier_execution` → `scenes.validate_scene_source` / `validate_manim_source` | syntax, imports, known-bad kwargs, LaTeX escaping, backend-mix detection |
| Visual observer | `plugins/observer_visual` → `visual_observe.observe_clip` | per-frame ink/motion evidence onto `RenderArtifact` |
| Layout verifier | `plugins/verifier_layout` (+ `scenekit.audit`) | overlaps, overflow, safe-area, crowding — typed subtypes (`LayoutSubtype`) |
| Spatial verifier | `plugins/verifier_spatial` | geometry critic on rendered frames |
| Motion verifier | `plugins/verifier_motion` | rendered-pixel motion vs storyboard motion ops |
| Temporal verifier | `plugins/verifier_temporal` | duration vs narration span |
| Semantic verifier | `plugins/verifier_semantic` | LLM critic over preview + narration (soft/hard configurable) |
| Storyboard verifier | `plugins/verifier_storyboard` | cue ranges, state/motion conformance |
| Lifecycle verifier | `plugins/verifier_lifecycle` | object-identity shell (soft) |
| Audio verifier | `plugins/verifier_audio` | ASR caption drift over finished video |
| Pedagogy verifier | `plugins/pedagogy.py` + `verifier_pedagogy` | whole-video pedagogy review |
| HITL | `plugins/feedback_hitl`, `verifier_hitl_approval`, `harness/hitl.py` | autonomous / human_on_failure / human_approval modes |
| Timeline/encode/finish | `generator_timeline`, `renderer_encode`, `renderer_finish` (`timeline.py`, `encode.py`, `finish.py`) | final mux, captions, `out/final.mp4` |
| Final QC + publish | `verifier_final_qc` (`qc.py`), `generator_publish` (`publish.py`) |
| Repair router | `plugins/repair_router` + `policy.py` | `finding_type → target plugins`; plan/execute only — never decides success |
| Repair controller | `harness/repair_controller.py` | single owner of detect→snapshot→repair→re-verify→compare→decide |
| Candidate workspace | `harness/workspace.py` | sidecar `build/harness/candidates/<stem>/rev<N>/`; promote/discard |
| Quality instrument | `harness/scene_quality.py` | deterministic per-scene evidence + lexicographic comparison |
| Convergence | `harness/convergence.py` | no-progress / A→B→A oscillation stop reasons |
| Revision history | `harness/revision_history.py` | `build/harness/revisions.json` |
| Per-scene report | `harness/scene_report.py` | `build/reports/scenes/<stem>.json` + `build/revisions/<stem>/revision_NN/report.json`; `build_repair_context()` renders it into repair prompts |
| Lineage/staleness | `harness/lineage.py`, `harness/regression.py` | revision-based staleness; scene-plan fingerprints |
| Telemetry | `harness/journal.py` (events.jsonl), `harness/logging_.py` (log.jsonl), `repair_log.jsonl`, `harness/metrics.py`, `harness/experiment_summary.py`, `harness/quality_report.py`, `harness/experience.py` |
| Layout zones | `harness/layout_zones.py` | shared SceneKit/Manim zone + safe-area constants |
| Final-video gate | `HarnessRunner._check_final_video_reachable` | final.mp4 must exist, be non-trivial, and be built from the current scene revisions (`program.is_stale`) |
| Model routing | `llm.py` | Gemini/OpenAI-compatible client; monotonic model chain; key rotation; NOT_FOUND permanent skip; rate-limit rotation |
| CLI | root `prompt2render.py` | `new, doctor, draft, voice, align, scenes, stills, plan, encode, finish, check, build, harness, ablation, events, scene-history, harness-check, report, auto, manim, assemble, publish, animate` |

### 1.3 The repair loop today

`RepairController.repair_scene(context, stem, findings, source_plugin)`:

1. `router.plan(finding, source)` → `RepairPlan` (finding_type, targets,
   category, subtype, allowed_changes, protected_properties,
   repair_instruction).
2. Budgets: `max_repairs_per_scene` (3), `max_total_repairs` (12); a rejected
   candidate still consumes budget.
3. `workspace.open_candidate()` — accepted files untouched; sidecar allocated.
4. `router.execute(plan)` — pushes diagnostic + repair contract text into
   `context.repair_context[stem]`, then `revert_scene` + `regenerate_one`
   on the target generator (writes into the sidecar path).
5. Render candidate (`renderer_stills`/`renderer_manim`).
6. Re-verify with **every** scene-scoped verifier (not just the complainer).
7. `write_scene_report(revision=candidate)` + `archive_revision()`.
8. `_judge()` acceptance rule:
   - VERIFICATION_UNAVAILABLE for a required verifier → reject;
   - candidate render produced no output → reject;
   - new blocking finding **types** introduced → `REGRESSION_REJECTED`;
   - blocking count increased → `REGRESSION_REJECTED`;
   - triggering finding type still present → `TARGET_DEFECT_UNRESOLVED`;
   - `scene_quality.compare()` verdict WORSE → `REGRESSION_REJECTED`;
   - INSUFFICIENT_EVIDENCE → reject;
   - convergence tracker (no progress / oscillation) consulted on reject path.
9. Accept → `workspace.promote()` (only place `scene_versions` advances);
   reject → `workspace.discard()` + restore accepted findings.
10. Journal events (`scene.repair.*`, `scene.accepted`/`scene.rollback`/
    `scene.rejected`), lifecycle transitions, `revisions.json` entry with
    repair_contract, finding_diff, quality before/after, verifier statuses.

### 1.4 What already satisfies the upgrade brief

- Artifact-side candidate isolation and rollback (workspace.py) — Phase 11 core.
- Typed finding taxonomy with routing key (`finding.py`, `policy.py`) — Phase 5 core.
- Report-driven repair prompt on the Manim path (`scene_report.build_repair_context`).
- Deterministic, explained acceptance (scene_quality) — Phases 9/10/20 core.
- Persisted revision history, durable event journal, metrics and experiment
  summaries — Phases 15/21/24 core.
- Final-video reachability invariant with revision-staleness check — Phase 28.
- Model/key fallback with permanent NOT_FOUND classification — Phase 17 core.
- Layout zone constants shared by generator guidance and verifiers — Phase 19 core.
- Deterministic Manim preflight (`validate_manim_source`) — Phase 18 core.

### 1.5 Gap analysis vs. the target architecture

| # | Gap | Resolution (this upgrade) |
|---|---|---|
| G1 | No single per-revision **evidence bundle**: report.json exists but lacks per-check pass/fail map, `must_preserve`, locked properties, hashes | new `harness/evidence.py`; `evidence.json` archived per revision |
| G2 | **Change contract** is prose (allowed/protected/instruction), not the structured problems/targets/required_changes/preserve/success_conditions/forbidden_changes schema; not persisted | `evidence.build_change_contract()`; persisted as `repair.json`; injected verbatim into repair prompts |
| G3 | No **repair scope** classification (LOCAL/REGIONAL/SCENE); repair is always full regeneration | `evidence.classify_repair_scope()`; scope flows into contract + prompt; PATCH preferred where findings carry line targets |
| G4 | **Locked properties** not recorded or enforced: passing dimensions are only prose in the Manim path, absent in the SceneKit path | locked-properties map in evidence bundle; consumed by both generators' repair feedback |
| G5 | Acceptance compares counts only; a candidate may drop layout 100→70 while raising semantic and survive if blocking counts are equal | **dimension regression guard** in `_judge`: hard invariants per quality dimension with tolerance |
| G6 | No **visual memory / visual diff**: no structured per-revision visual state; `regression.py` only fingerprints scene-plan text | `harness/visual_state.py`: zones/bboxes from audit/preview; `visual_diff()` feeds judge as regression evidence |
| G7 | No per-role **model abstraction** (one `P2R_SCENE_MODEL` for everything); fallback events not telemetry-recorded | `harness/model_routing.py` (P2R_PLANNER_MODEL / P2R_GENERATOR_MODEL / P2R_REPAIR_MODEL / P2R_VERIFIER_MODEL ...); `llm.py` fallback records |
| G8 | Preflight misses the brief's canonical cases: undefined identifiers (`CAPPTION_Y`), `align_to(..., buff=...)` | extend `validate_manim_source` (conservative UPPER_CASE typo detector + align_to kwarg check) |
| G9 | CLI lacks `verify/repair/revisions/rollback/replay` for a single scene | new subcommands over shared `harness/scene_ops.py`; no existing command changes |
| G10 | Revision archive lacks generation metadata (model, hashes, parent revision) and an `accepted/` pointer | extend `archive_revision` (`generation.json`, `repair.json`, `evidence.json`, `accepted/`) |
| G11 | Failure attribution (CAUSE/DETECTED_BY/TARGET/REPAIR/RESULT) not a first-class record | attribution block in repair journal events + `revisions.json` entries |
| G12 | SceneKit generator repair path consumes only raw diagnostics, not the report/evidence bundle | wire `build_repair_context` + contract into `generator_code._repair_feedback` |

### 1.6 Known defects found during audit

- `llm.py` `CANONICAL_MODELS[0]` is an accidental string concatenation
  (`"gemini-2.5-flash" "gemini-3.6-flash"` → one invalid model name). The
  rotation machinery tolerates it (permanent NOT_FOUND skip) but it silently
  wastes the first fallback slot. Fixed in this upgrade.

---

## 2. Upgraded architecture

### 2.1 The research loop (unchanged identity)

```
GENERATE → RENDER → VERIFY → EVIDENCE → TARGETED REPAIR → REGRESSION CHECK → ACCEPT/ROLLBACK
```

The harness is the contribution; LLMs are replaceable components behind the
model-routing abstraction.

### 2.2 Artifact-centric scene state

Every evaluated revision gets a persistent bundle under the project:

```
build/revisions/<stem>/
    revision_001/
        scene_<stem>.py        # source snapshot
        report.json            # canonical scene report (existing)
        evidence.json          # NEW: structured evidence bundle
        repair.json            # NEW: change contract used for this revision
        generation.json        # NEW: model, timestamps, hashes, parent
        preview.png            # when available
        <render artifact>      # clip or manifest.json
        visual_state.json      # NEW: structured visual memory
    revision_002/...
    accepted/
        manifest.json          # pointer: accepted revision number + artifact refs
        scene_<stem>.py        # accepted source copy (small files only)
        report.json
        evidence.json
```

Candidate scratch remains `build/harness/candidates/<stem>/rev<N>/`
(deleted on promote/discard as today). Heavy render artifacts are referenced,
not duplicated.

### 2.3 Evidence bundle (schema)

Produced once per verification cycle (`harness/evidence.py`):

```json
{
  "schema_version": "1.0",
  "scene_id": "06", "revision": 2, "status": "fail",
  "checks": {"syntax": "pass", "execution": "fail", "layout": "pass",
              "visual": "pass", "semantic": "pass", "pedagogy": "pass",
              "temporal": "pass"},
  "findings": [ { "finding_id": "...", "finding_type": "execution_failure",
                  "category": "SEMANTIC", "severity": "BLOCKING",
                  "location": {"file": "scene_06.py", "line": 676},
                  "message": "...", "repair_type": "code_local_repair" } ],
  "passing_properties": ["layout", "visual", "semantic", "pedagogy"],
  "locked_properties": {"layout": true, "visual": true, "semantic": true,
                         "pedagogy": true, "execution": false},
  "must_preserve": ["object positions", "caption zone", "animation timing", ...],
  "recommended_actions": [...],
  "quality": { ... SceneQuality.to_dict() ... },
  "visual_state_ref": "visual_state.json"
}
```

Verifiers keep their own evidence fields; the bundle normalizes them without
forcing identical shapes.

### 2.4 Typed failure router (repair_type)

Findings map to repair strategies before any regeneration:

```
execution_failure / undefined_identifier      → code_local_repair
invalid_manim_api                             → manim_api_repair
layout_overflow / text_overlap / crowding     → layout_repair
caption_overflow / caption_collision          → caption_layout_repair
semantic_mismatch                             → semantic_repair
missing_visual_concept                        → scene_content_repair
timing_mismatch / temporal_mismatch           → timing_repair
pedagogy_review                               → pedagogical_repair
motion_absence                                → visual_refinement
conflicting findings across verifiers         → repair_arbitration (documented
                                                precedence, never a blended prompt)
```

The router stays where it is (`repair_router/policy.py`); the repair_type
labels and scope classification live in `evidence.py` and ride on the same
`RepairPlan`.

### 2.5 Change contract + repair scope

Before every regeneration the controller builds a machine-readable contract:

```json
{
  "scene_id": "06", "parent_revision": 1,
  "problems": ["CAPPTION_Y undefined"],
  "targets": ["scene_06.py lines 676-682"],
  "required_changes": ["replace CAPPTION_Y with CAPTION_Y"],
  "preserve": ["all verified layout", "caption zone", "animation timing"],
  "success_conditions": ["execution passes",
                          "previously passing properties remain passing"],
  "forbidden_changes": ["do not redesign the scene",
                         "do not move unrelated objects"],
  "repair_scope": "LOCAL",
  "locked_properties": {"layout": true, "visual": true, ...}
}
```

Repair scope: `LOCAL` (line-targeted; default when findings carry location
and are code/typography class) ≺ `REGIONAL` (one zone/component) ≺ `SCENE`
(full regeneration, only for conceptual failures). The preference order is
**PATCH > PARTIAL > FULL**; the prompt always states: *"Do not redesign the
scene unless the failure explicitly requires redesign. Preserve all
previously verified properties. Fix the reported failure with the smallest
safe change."*

### 2.6 Regression checking and acceptance

Acceptance (in `_judge`, extended):

1. No VERIFICATION_UNAVAILABLE for required verifiers.
2. Candidate render produced output.
3. No newly introduced blocking finding types.
4. Blocking count did not increase.
5. Triggering defect gone.
6. **Dimension guard (new):** every quality dimension that passed in the
   accepted revision is a hard invariant within tolerance — a candidate that
   drops `layout_score` 100→70 while raising semantic is rejected even with a
   higher aggregate. No single scalar dominates.
7. Lexicographic `scene_quality.compare()` verdict BETTER/EQUAL.
8. Visual-diff guard (new, conservative): for LOCAL/REGIONAL repairs, large
   unrelated bounding-box displacement between previews is regression
   evidence.

Rejection restores the accepted revision verbatim (files **and** findings),
records the reason, and consumes budget. The last accepted artifact is never
destroyed by a candidate.

### 2.7 Model abstraction and fallback

`harness/model_routing.py` resolves per-role models:

```
P2R_PLANNER_MODEL / P2R_GENERATOR_MODEL / P2R_REPAIR_MODEL /
P2R_VERIFIER_MODEL / P2R_SEMANTIC_VERIFIER_MODEL / P2R_VISUAL_VERIFIER_MODEL
   → each falls back to P2R_SCENE_MODEL → built-in default
```

All roles use the existing `llm.complete(model_env=...)` machinery; fallbacks
(NOT_FOUND permanent skip, rate-limit rotation) are recorded into the event
journal and metrics (`llm.FALLBACK_RECORDS`).

### 2.8 Manim robustness

- Installed/target version from `manimver.py` (`P2R_MANIM_VERSION`); the
  generator prompt states the exact target version.
- Deterministic preflight before any render: syntax, forbidden imports,
  backend mixing, known-bad kwargs per version, malformed LaTeX, **undefined
  identifier heuristic (edit-distance-1 typo detector for UPPER_CASE
  constants)**, and **`align_to(..., buff=...)` rejection**.

### 2.9 CLI extensions (additive only)

```
prompt2render verify   <slug> --section N      # run scene verifiers on current artifacts
prompt2render repair   <slug> --section N [--dry-run]
prompt2render revisions <slug> --section N     # alias of scene-history
prompt2render rollback <slug> --section N --revision M
prompt2render replay   <slug> --section N      # deterministic re-render + re-verify, no LLM
```

### 2.10 Research/experiment support

`tools/ablation_runner.py` + `experiment_summary.py` already support
condition matrices; the experiment conditions A–F from the brief map to
config toggles (verifiers on/off, repair controller enabled/disabled). All
metrics needed for comparison are already aggregated in
`build/harness/experiment_summary.json` (first-pass success, repair success
rate, regression rate, mean revisions to acceptance, timing, cost fields).

---

## 3. Implementation order (this upgrade)

1. `evidence.py` — bundle, contract, scope, locked properties (G1–G4).
2. Wire evidence/contract into `repair_controller` + both generators (G4, G12).
3. Dimension regression guard + attribution (G5, G11).
4. Visual state + diff (G6).
5. Model routing + fallback telemetry + `llm.py` bug fix (G7).
6. Preflight extensions (G8).
7. Archive extensions: evidence/repair/generation/accepted (G10).
8. CLI: `verify/repair/revisions/rollback/replay` via `scene_ops.py` (G9).
9. Tests for all of the above + synthetic fixtures; full suite green.
10. End-to-end demonstration: injected caption-overflow failure → targeted
    repair → acceptance; injected regressive candidate → rejection + rollback.
