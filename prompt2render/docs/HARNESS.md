# Prompt2Render harness — how to use

The harness is the explicit, pluggable, and loggable backbone for the complete Prompt2Render workflow.
It now owns the handoff from script and animation planning through narration, voice, alignment, scene
code, still rendering, deterministic and spatial verification, timeline, encoding, finishing, final QC,
and publication. The original standalone CLI commands remain available for debugging and manual stage
execution, but `prompt2render harness <slug>` is the end-to-end path.

Background and the full reconciliation against prompt2render's actual code: `docs/MIGRATION_INVENTORY.md`.

## Quick start

```
python prompt2render.py harness <slug>
```

Runs every enabled plugin, in dependency order, over `projects/<slug>`. Prints the resolved
plugin order, then a PASS/WARN/FAIL/SKIP line per finding. Writes
`projects/<slug>/build/harness/log.jsonl` (one line per plugin invocation) and, if
`repair_router` is enabled, `build/harness/repair_log.jsonl` (one line per repair cycle). The authoritative stage sequence is also visible in `build/harness/log.jsonl`.

A run needs a project with `script.md`. If narration is still the scaffold placeholder, the harness
will invoke the existing draft stage; otherwise it preserves the authored narration. It then performs
voice synthesis and alignment before scene generation. It is safe to run against a project that is
already fully built; cache-aware stages reuse current artifacts where possible.

## The pipeline

Plugins run in an order resolved from what each one reads/writes (`declare_dependencies()` /
`declare_effects()`), not a hardcoded list. For the default config, that resolves to:

```
planner_script → chunker_scene → planner_visual → generator_voice → generator_align → planner_audio →
generator_code → renderer_stills → verifier_semantic → verifier_lifecycle → verifier_spatial →
feedback_hitl → generator_timeline → renderer_encode → renderer_finish → verifier_audio →
verifier_final_qc → generator_publish
```

| plugin | wraps | default | notes |
|---|---|---|---|
| `planner_script` | `draft.draft` for placeholders | on | improves missing narration without overwriting authored text unless forced |
| `chunker_scene` | `project.parse_script` | on | splits the harness-approved `script.md` into `scene_plan` |
| `planner_llm` | optional per-section LLM expansion | off | optional extra storyboard call; disabled by default to avoid quota churn |
| `planner_visual` | deterministic animation contract | on | adds topic-agnostic state, zone, continuity, and validity requirements |
| `planner_audio` | `align.load` | on | ingests timing produced by the harness-owned alignment stage |
| `retriever_manim_rag` | deterministic keyword match over a curated Manim pattern library | on | Tier 2 Phase 7: patterns are injected into `GeneratorManimPlugin`'s prompts (`renderer_manim._pattern_hints`) — no longer a no-op stub |
| `generator_voice` | `voice.build` | on | synthesizes and masters narration; records audio artifacts |
| `generator_align` | `align.align` | on | creates force-aligned timing artifacts |
| `generator_code` | `scenes.generate_all` | on | the real Coder — one Gemini call per section, with preflight and audit retries |
| `renderer_stills` | `stills.render_many` | on | the actual live renderer (matplotlib) |
| `renderer_manim` | `visuals.manim_scene` | **off** | opt-in escape hatch; needs explicit `py_file`/`scene`/`index` in config |
| `verifier_semantic` | *(none live)* | on (soft) | stub — always reports clean |
| `verifier_spatial` | `scenekit.audit()` | on (hard) | real — the working layout critic |
| `verifier_lifecycle` | *(none live)* | on (soft) | always-`[]` shell — no object identity in prompt2render |
| `generator_timeline` | `timeline.build` | on | converts accepted still manifests and narration timing into `build/plan.json` |
| `renderer_encode` | `encode.encode` | on | creates section clips using the configured encoder |
| `renderer_finish` | `finish.finish` | on | concatenates, muxes, captions, and writes `out/final.mp4` |
| `verifier_audio` | `qc.caption_drift` | on (hard) | independent whole-video caption-drift check after finish |
| `verifier_final_qc` | `qc.check` | on (hard) | runs the complete final QC gate before publication |
| `generator_publish` | `publish.build_packet` | on | writes the upload packet only after final QC passes |
| `feedback_hitl` | *(none live)* | on (never gates) | optional asynchronous feedback record |
| `repair_router` | *(new)* | on | event subscriber for verifier findings; see below |

## Configuring

Edit `prompt2render/harness/config.yaml`, or pass `--config path/to/your.yaml` to any tool. Every plugin can
be disabled, and every gate overridden, with no code change:

```yaml
verifier_spatial:
  enabled: true
  gate_override: false   # demote a hard-gated plugin to non-blocking, or vice versa
```

`gate_override: null` (the default) falls back to the plugin's own `is_gate()` default.

## Reading `check_results`

Every verifier writes a list of dicts to `context.check_results[<plugin name>]`. Each entry has at
least a `status` (`pass|warn|fail|skip`) and `detail`. Verifiers built on the shared taxonomy
(currently `verifier_spatial`) also include `category` (`SPATIAL|TEMPORAL|SEMANTIC|AUDIO`) and
`severity` (`BLOCKING|WARNING|INFO`) — see `prompt2render/harness/finding.py`. A `"fail"` status is what
`HarnessRunner` treats as a `check.failed` event; whether that halts the run depends on the
plugin's gate.

## `repair_router`

Not an ordinary pipeline plugin — it's an event subscriber, attached separately:

```python
repair_router.attach(bus=bus, plugins_by_name={p.name: p for p in plugins}, log_path=...)
```

(`tools/harness_run.py` already does this for you.) On a `check.failed` event, it routes the
finding to a target plugin via a `RoutingPolicy` (default: `StaticTableRoutingPolicy`, config key
`repair_router.routing_table`), calls `revert_scene()` + `regenerate_one()` on that plugin for the
one affected section, and retries up to `repair_router.max_repairs_per_scene` (default 3) times before
giving up. On giving up, a hard-gated source plugin still halts the run; a soft-gated one gets its
finding demoted to `"open_defect"` and the run continues.

**Known limitation:** today only `generator_code` implements the per-scene `revert_scene()` /
`regenerate_one()` pair the fast repair path needs. `verifier_spatial` — the one verifier with
real detection — will rarely actually trigger this in practice, because `scenes.py`'s own Gemini
call already retries internally against the same audit before a section is ever marked accepted.
The router is real and tested (`tests/harness/test_repair_router.py`, dummy plugins only) for when
`verifier_semantic` / `verifier_lifecycle` grow real detection logic.

## Regression testing — the golden baseline

```
python tools/golden_baseline.py record --slug hash-tables    # (re-)record the baseline
python tools/golden_baseline.py verify --slug hash-tables    # check current code against it
```

Freezes a project's `script.md`/voice/align/scenes output as a fixture (scenes generation is the
one LLM-touched, non-deterministic stage) and re-runs the deterministic tail
(`stills → plan → encode → finish → check`), fingerprinting JSON artifacts, PNG hashes, and video
technical stats (not raw video bytes — ffmpeg's bitstream isn't guaranteed byte-reproducible even
when behavior is unchanged). `verify` must PASS before trusting a change to any wrapped stage.
Re-record only when a deliberate behavior change makes the old baseline wrong.

## Ablation runner (Phase A — detection only)

```
python tools/ablation_runner.py --slug hash-tables [--out path.json]
```

Runs the 4-condition matrix ({`verifier_spatial`, `verifier_lifecycle`} × {off, on}) over a
project, with both verifiers' gates forced off throughout (findings are recorded, not acted on —
Phase A isolates raw detection rate from repair-induced changes). Writes one row per
(condition × section) to `build/harness/ablation_results.json`: findings by category, render
time, repair cycles used (0 throughout Phase A — asserted). Phase B (detection **and** repair) is
intentionally not built — Phase A's numbers should justify that extra engineering first.

## Tests

```
pytest tests/harness/
```

Dummy plugins only — no Manim, no LLM, no network, no real prompt2render project needed. Covers dependency
ordering, config-driven enable/disable, snapshot/revert, the event bus, JSONL logging, the runner
(including prompt2render's own `sys.exit`-as-fatal-error idiom), routing policy, and the full repair cycle.

## Adding a new plugin

1. `prompt2render/harness/plugins/<name>/__init__.py` — subclass `Plugin` (`prompt2render/harness/plugin.py`),
   implement `declare_dependencies()`, `declare_effects()`, `run()`. Keep it flat — one plugin per
   folder, no nesting by pipeline stage.
2. Register it in `prompt2render/harness/plugins/__init__.py`'s `REGISTRY`.
3. Add a default entry to `prompt2render/harness/config.yaml` (`enabled`, `gate_override`).
4. If it wraps something real, run `pytest tests/harness/` and, if it touches a
   golden-baseline-covered stage, `python tools/golden_baseline.py verify --slug hash-tables`.

## Scope and limitations

The default harness now covers the complete local pipeline, but it does not make arbitrary subject-matter
truth decidable. Deterministic checks validate artifact contracts, documented primitive inputs, cue
ranges, layout geometry, and final technical QC. The optional semantic reviewer and future topic profiles
are still needed for claims that cannot be inferred from the scene API. Manim remains an opt-in escape
hatch and is not part of the default Scenekit path.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `[harness] no script.md at ...` | wrong slug, or the project was never scaffolded (`prompt2render new`) |
| `planner_script` fails on a placeholder | configure Gemini keys/models, or write the narration manually before running the harness |
| `verifier_audio` reports `skip` | no ASR model is available; install one with `prompt2render models --asr base.en` |
| `verifier_final_qc` halts publication | inspect `out/qc.json`; publication is intentionally blocked until the final QC result is acceptable |
| `DependencyError: cannot resolve plugin order` | a plugin's `declare_dependencies()` names a field nothing produces — check `prompt2render/harness/loader.py`'s `PRESEEDED_FIELDS` and the plugin's own effects |
| `GateFailure` halts a run | a hard-gated plugin found a `"fail"` — read `check_results[<plugin>]` for `detail`, or set `gate_override: false` in config to make it non-blocking |
| `harness_run.py` looks stuck | almost always `verifier_audio` — it re-transcribes the whole finished video, which takes minutes on a full-length project |
| ablation runner is slow | make sure `generator_code`/`renderer_stills` aren't being forced to regenerate — a project with all sections already accepted should make every condition a fast no-op |
