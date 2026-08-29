# Research and experiment support

Prompt2Render is built to evaluate the harness itself: *which verification
stages and repair mechanisms actually improve first-pass LLM scene
generation?* The harness is the contribution; LLMs are replaceable
components behind the model-routing abstraction.

## Experiment conditions

The brief's ladder maps to config toggles (`harness/config.yaml`,
`--config` override) over identical projects:

| Condition | Config |
|---|---|
| A. LLM-only generation | all verifiers off; `repair_router` disabled |
| B. LLM + planning | planners on; verifiers off |
| C. + execution verification | `verifier_execution` on (hard gate) |
| D. + visual verification | + `observer_visual`, `verifier_spatial`/`verifier_layout`, `verifier_motion` |
| E. + semantic verification | + `verifier_semantic`, `verifier_storyboard` |
| F. full self-correcting harness | everything on (the default `prompt2render harness`) |

Model-vs-model experiments: point the role env vars
(`P2R_PLANNER_MODEL`, `P2R_GENERATOR_MODEL`, `P2R_REPAIR_MODEL`,
`P2R_VERIFIER_MODEL`, `P2R_SEMANTIC_VERIFIER_MODEL`) at different models;
`generation.json` and `metrics.json:model_fallbacks` record which model
actually produced each revision.

Determinism knobs for comparability: `P2R_LLM_TEMPERATURE`,
`P2R_LLM_SEED` (`llm.py`), golden baselines
(`tools/golden_baseline.py record|verify --slug <s>`).

## What is recorded

Per run (`build/harness/`):

- `experiment_summary.json` — total/successful/failed scenes, blocking
  findings, warnings, repair attempts, accepted/rejected repairs,
  regression rejections, verification-unavailable events, render failures,
  mean/median repair cycles, repair success rate, regression rate, mean
  temporal error, mean layout/semantic/pedagogical scores, render time,
  verification time, inference cost, final pass.
- `metrics.json` — repair decision counts, per-stage latency,
  model fallbacks.
- `revisions.json` — per-attempt trajectory (mean revisions to acceptance,
  per-scene repair histories, quality before/after each attempt).
- `repair_log.jsonl` — full decision records incl. comparison payloads.
- `events.jsonl` — scene lifecycle with failure attribution.
- `experience_memory.jsonl` — cross-run repair episodes.

This covers the brief's metric list: first-pass success (revision 1
decisions), final success, render success, execution/layout/semantic/
pedagogy failure rates (finding categories), regression rate, mean
revisions to acceptance, repair success rate, time to acceptance
(`stage_latency_seconds` + timestamps), token/cost fields, final quality
scores.

## Tooling

```
python tools/ablation_runner.py --slug <s> [--out path.json]
    # detection matrix over verifier subsets (findings recorded, gates off)

python prompt2render.py report <slug> [--rebuild]
    # experiment summary for one project

python tools/golden_baseline.py verify --slug hash-tables
    # regression guard for deterministic stages

python demo_self_correction.py
    # offline proof of the accept/rollback loop (no API keys)
```

## Methodology notes

- Acceptance is never a single scalar (`scene_quality.compare` is
  lexicographic; dimension guards are hard constraints). Score gaming
  (shrinking text to kill overlap findings) is caught by the dimension/
  visual-diff guards and by readability checks in the layout verifier.
- Rejected attempts stay in `revisions.json` — "what was attempted" is
  part of the data, not log noise.
- Ablation Phase A isolates detection rates from repair effects
  (gates forced off); the full harness (condition F) measures the
  compounded loop.
