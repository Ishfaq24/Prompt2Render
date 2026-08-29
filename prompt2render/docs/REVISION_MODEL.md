# Revision model: artifact-centric scene state

Every evaluated revision of every scene leaves a persistent, inspectable
record. Accepted work is never destroyed by a candidate.

## Directory layout (per project)

```
build/revisions/<stem>/
    revision_001/
        scene_<stem>.py       # source snapshot
        report.json           # canonical scene report
        evidence.json         # evidence bundle (checks, findings, locked props)
        repair.json           # change contract this revision was built under
        generation.json       # model env/primary, fallbacks, hashes, parent
        visual_state.json     # structured visual memory
        <render artifact>     # manifest.json / clip (archived by scene_report)
        preview.png           # when available
    revision_002/ ...
    accepted/
        manifest.json         # {accepted_revision, revision_dir, artifact refs}
        scene_<stem>.py       # small artifacts copied
        report.json
        evidence.json
```

Candidate scratch: `build/harness/candidates/<stem>/rev<N>/` — allocated on
`workspace.open_candidate`, deleted on promote/discard. Heavy render
artifacts are referenced by `accepted/manifest.json`, never duplicated.

## Revision state

- In-memory: `SceneContext.scene_versions[stem]` (advanced **only** by
  `workspace.promote`), `CodeArtifact.revision`,
  `RenderArtifact.source_revision`.
- Durable: `build/harness/revisions.json` (`revision_history.py`) — one
  record per attempt (accepted *and* rejected), each with revision,
  parent_revision, timestamp, reason, decision, repair_contract,
  finding_diff (resolved/introduced/unchanged), quality before/after,
  triggering finding, verifier statuses, render status, rejection reason.
- Event-sourced: `build/harness/events.jsonl` (`journal.py`) — the ordered
  scene lifecycle (generated/repair.started/candidate/rendered/verified/
  accepted/rollback/rejected), each repair outcome carrying failure
  attribution.

## generation.json provenance

```json
{
  "scene_id": "06", "revision": 2, "parent_revision": 1,
  "timestamp": "...",
  "model_env": "P2R_REPAIR_MODEL", "model_primary": "...",
  "fallbacks": [{"model": "...", "reason": "not_found|rate_limited",
                   "next_model": "...", "label": "..."}],
  "source_sha256": "...", "spec_sha256": "...",
  "trigger_finding_type": "caption_overflow"
}
```

Model selection per role (`model_routing.py`): `P2R_PLANNER_MODEL`,
`P2R_GENERATOR_MODEL`, `P2R_REPAIR_MODEL`, `P2R_VERIFIER_MODEL`,
`P2R_SEMANTIC_VERIFIER_MODEL`, `P2R_VISUAL_VERIFIER_MODEL`, each falling
back to `P2R_SCENE_MODEL`, then the built-in default. Fallbacks are
recorded by `llm.py` (`fallback_records()`), surfaced in
`metrics.json:model_fallbacks`, and per-revision in `generation.json` — a
model switch is never silent.

## Candidate lifecycle

```
open_candidate   accepted artifacts snapshotted; sidecar allocated
   render        into the sidecar only
   re-verify     every scene-scoped verifier
   judge         acceptance rule (SELF_CORRECTION.md)
promote          move sidecar -> canonical; bump revision; sync accepted/
discard          delete sidecar; restore accepted records verbatim
```

Staleness downstream of a scene (timeline, encode, final.mp4) is a
revision comparison (`lineage`, `program.is_stale`), never a heuristic.

## Rollback

- Automatic: every rejected candidate restores the last accepted revision.
- Explicit: `prompt2render rollback <slug> --section N --revision M`
  restores an archived revision's source onto the canonical path, records a
  `rollback` entry in `revisions.json`, and moves the accepted pointer.
  The next harness run or `replay` re-renders from it.

## Single-scene CLI

```
prompt2render verify    <slug> --section N            # deterministic checks + report/evidence
prompt2render repair    <slug> --section N [--manim] [--dry-run] [--config ...]
prompt2render revisions <slug> --section N            # alias of scene-history
prompt2render rollback  <slug> --section N --revision M
prompt2render replay    <slug> --section N            # re-render + re-verify, no LLM
prompt2render events    <slug> [--scene N] [--type scene.rollback]
```
