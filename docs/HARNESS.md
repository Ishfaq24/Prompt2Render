# Prompt2Render harness — how to use

An additive research/evaluation layer over prompt2render's live pipeline. It does **not** replace
`prompt2render build` or any of its CLI subcommands — those still run exactly as documented in the main
`README.md`. This harness wraps the generation/verification/repair loop (script → scene_plan →
code_artifacts → render_artifacts → check_results) in an explicit, pluggable, loggable shape, for
experimenting with verifiers and repair strategies without touching the shipping tool.

Background and the full reconciliation against prompt2render's actual code: `docs/MIGRATION_INVENTORY.md`.

## Quick start

```
python tools/harness_run.py <slug>
```

Runs every enabled plugin, in dependency order, over `projects/<slug>`. Prints the resolved
plugin order, then a PASS/WARN/FAIL/SKIP line per finding. Writes
`projects/<slug>/build/harness/log.jsonl` (one line per plugin invocation) and, if
`repair_router` is enabled, `build/harness/repair_log.jsonl` (one line per repair cycle).

A run needs, at minimum, a project with `script.md`, synthesized narration (`prompt2render voice`), and
alignment (`prompt2render align`) already done — same prerequisites as `prompt2render scenes`. It's safe to run
against a project that's already fully built (`prompt2render build`); most plugins no-op when their output
is already current, same as the CLI stages they wrap.

## The pipeline

Plugins run in an order resolved from what each one reads/writes (`declare_dependencies()` /
`declare_effects()`), not a hardcoded list. For the default config, that resolves to:

```
chunker_scene → planner_llm → planner_audio → generator_code → renderer_stills →
verifier_semantic → verifier_lifecycle → verifier_spatial → verifier_audio →
evaluator_vlm → feedback_hitl
```

| plugin | wraps | default | notes |
|---|---|---|---|
| `chunker_scene` | `project.parse_script` | on | splits `script.md` into `scene_plan` |
| `planner_llm` | *(none live)* | on | passthrough — no LLM planning call exists; marks entries planned |
| `planner_visual` | *(none live)* | **off** | no-op stub |
| `planner_audio` | `align.load` | on | ingests already-synthesized narration timing |
| `retriever_manim_rag` | *(none live)* | **off** | no-op stub, no RAG exists in prompt2render |
| `generator_code` | `scenes.generate_all` | on | the real Coder — one Gemini call per section |
| `renderer_stills` | `stills.render_many` | on | the actual live renderer (matplotlib) |
| `renderer_manim` | `visuals.manim_scene` | **off** | opt-in escape hatch; needs explicit `py_file`/`scene`/`index` in config |
| `verifier_semantic` | *(none live)* | on (soft) | stub — always reports clean |
| `verifier_spatial` | `scenekit.audit()` | on (hard) | real — the working layout critic |
| `verifier_lifecycle` | *(none live)* | on (soft) | always-`[]` shell — no object identity in prompt2render |
| `verifier_audio` | `qc.py` caption-drift gate | on (hard) | whole-video scoped — needs `out/final.mp4` to exist |
| `evaluator_vlm` | *(none live)* | on (soft) | stub — no vision-model call exists anywhere in prompt2render |
| `feedback_hitl` | *(none live)* | on (never gates) | stub — no human-in-the-loop mechanism exists |
| `repair_router` | *(new)* | on | not a pipeline stage — see below |

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
one affected section, and retries up to `repair_router.max_repair_cycles` (default 3) times before
giving up. On giving up, a hard-gated source plugin still halts the run; a soft-gated one gets its
finding demoted to `"open_defect"` and the run continues.

**Known limitation:** today only `generator_code` implements the per-scene `revert_scene()` /
`regenerate_one()` pair the fast repair path needs. `verifier_spatial` — the one verifier with
real detection — will rarely actually trigger this in practice, because `scenes.py`'s own Gemini
call already retries internally against the same audit before a section is ever marked accepted.
The router is real and tested (`tests/harness/test_repair_router.py`, dummy plugins only) for when
`verifier_semantic` / `verifier_lifecycle` / `evaluator_vlm` grow real detection logic.

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
time, repair cycles used (0 throughout Phase A — asserted). The `post_render_findings_by_category`
column is always empty today; no live `evaluator_vlm` exists to populate it (see the table above).
Phase B (detection **and** repair) is intentionally not built — Phase A's numbers should justify
that extra engineering first.

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

## Scope — what this harness does *not* cover

No target plugin folder corresponds to `voice.build`, `align.align`, `timeline.build`,
`encode.encode`, `finish.finish`, or `publish.build_packet` — those remain direct `prompt2render.py` calls,
completely unaffected by anything in `prompt2render/harness/`. `verifier_audio` reads their end result
(`out/final.mp4`) but can't run before it exists. See
`docs/MIGRATION_INVENTORY.md`'s reach-around checklist for the full accounting.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `[harness] no script.md at ...` | wrong slug, or the project was never scaffolded (`prompt2render new`) |
| `verifier_audio` reports `skip` | `out/final.mp4` doesn't exist yet — run `prompt2render build` (or at least `prompt2render finish`) on the project first, outside the harness |
| `DependencyError: cannot resolve plugin order` | a plugin's `declare_dependencies()` names a field nothing produces — check `prompt2render/harness/loader.py`'s `PRESEEDED_FIELDS` and the plugin's own effects |
| `GateFailure` halts a run | a hard-gated plugin found a `"fail"` — read `check_results[<plugin>]` for `detail`, or set `gate_override: false` in config to make it non-blocking |
| `harness_run.py` looks stuck | almost always `verifier_audio` — it re-transcribes the whole finished video, which takes minutes on a full-length project |
| ablation runner is slow | make sure `generator_code`/`renderer_stills` aren't being forced to regenerate — a project with all sections already accepted should make every condition a fast no-op |
