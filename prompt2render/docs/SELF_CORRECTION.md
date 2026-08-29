# Self-Correction: the repair loop

Prompt2Render's research loop:

```
GENERATE -> RENDER -> VERIFY -> EVIDENCE -> TARGETED REPAIR
    -> REGRESSION CHECK -> ACCEPT / ROLLBACK
```

The verification report is **actionable memory** for the next regeneration.
A regeneration is never "fix it" — it is a contract-bound, scope-limited,
regression-checked revision.

## The loop, step by step

Owned by `harness/repair_controller.py` (`RepairController.repair_scene`),
invoked by `HarnessRunner._repair` when a stage leaves blocking scene
findings. Budgets: `max_repairs_per_scene` (3), `max_total_repairs` (12);
a rejected candidate still consumes budget, so a scene cannot be retried
forever.

1. **Classify.** `repair_router/policy.py` maps the finding's
   `finding_type` to repair targets; `evidence.repair_type_for` labels the
   strategy (`code_local_repair`, `caption_layout_repair`,
   `semantic_repair`, ...).
2. **Evidence.** `evidence.build_evidence_bundle` snapshots the accepted
   revision's checks, findings (with verifier-specific evidence preserved),
   passing properties, locked properties, and must-preserve list.
3. **Contract.** `evidence.build_change_contract` converts the findings
   into problems / targets / required_changes / preserve /
   success_conditions / forbidden_changes, with a repair scope
   (`LOCAL > REGIONAL > SCENE`; PATCH > PARTIAL > FULL).
4. **Lock.** Passing dimensions are recorded as locked properties and sent
   to the generator verbatim: *"Preserve all properties that already passed
   verification. Modify only what is necessary... smallest safe change."*
5. **Repair.** The candidate is written to a sidecar
   (`build/harness/candidates/<stem>/rev<N>/`) — the accepted files are
   never touched during evaluation.
6. **Render + re-verify.** Every scene-scoped verifier re-runs, not just
   the one that complained.
7. **Judge.** The acceptance rule below decides; the convergence tracker
   (`harness/convergence.py`) additionally stops no-progress and A→B→A
   oscillation cycles.
8. **Accept or rollback.** `workspace.promote` or `workspace.discard`;
   every decision is journaled with failure attribution (cause /
   detected_by / target / repair / result) and persisted to
   `revisions.json`.

## Acceptance rule (`_judge`)

A candidate is accepted only if **all** hold:

1. No `VERIFICATION_UNAVAILABLE` for a required verifier.
2. The candidate render produced output.
3. No newly introduced blocking finding **types**.
4. Total blocking count did not increase.
5. The triggering defect is gone.
6. Lexicographic quality comparison (`scene_quality.compare`) is BETTER or
   EQUAL — blocking, then warnings, then skips, then numeric tie-breaks.
7. **Dimension guard:** every dimension that was clean (≥95) in the
   accepted revision may drop by at most `DIMENSION_REGRESSION_TOLERANCE`
   (5 points). Layout 100→70 while semantic rises is rejected; 100→98 is
   accepted. No aggregate score overrides a hard dimension regression.
8. **Visual-diff guard:** for LOCAL/REGIONAL repairs, structural visual
   churn (states vanishing, frame loss >30%, warning growth) is rejected.

Anything else: reject, restore the accepted scene verbatim (files **and**
findings), record the reason.

## Stop conditions

- accepted,
- budget exhausted (`REPAIR_BUDGET_EXHAUSTED`),
- not routable (`NOT_ROUTABLE` — whole-video findings, unknown types),
- no progress / oscillation (`convergence.py`),
- repeated repair errors (`REPAIR_ERRORED`).

The loop never runs indefinitely.

## Reproduction

```
python demo_self_correction.py        # offline scripted demonstration
pytest prompt2render/tests/harness/test_dimension_regression.py
pytest prompt2render/tests/harness/test_repair_controller_wiring.py
```
