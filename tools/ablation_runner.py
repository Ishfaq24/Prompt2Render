"""Stage 5, Phase A — detection-only ablation runner.

Per the migration brief §3b: Phase A measures raw catch rate, uncontaminated by repair-induced
regeneration changing what gets rendered. repair_on_findings stays off for verifier_spatial and
verifier_lifecycle throughout — findings are recorded, not acted on. Phase B (detection+repair)
is explicitly NOT built here; the brief is clear Phase A's numbers should justify that extra
engineering first.

4-condition matrix: {spatial: off, lifecycle: off}, {on, off}, {off, on}, {on, on}. Each condition
still renders every section (§3b: "the pipeline must still render even in the {off, off}
condition"), so gates for both verifiers are forced off throughout — only their `enabled` flag
toggles between conditions; `enabled: false` still runs generator_code/renderer_stills, it just
skips computing that verifier's findings.

    python tools/ablation_runner.py --slug hash-tables [--out path.json]

Output: one row per (condition x section): pre-render findings by category (from whichever of
verifier_spatial/verifier_lifecycle was on), post-render findings by category (from
evaluator_vlm — see the caveat below), render time, repair cycles used (0 throughout Phase A,
verified as an invariant).

evaluator_vlm caveat: no live vision-model call exists anywhere in prompt2render (docs/MIGRATION_INVENTORY.md
§3/§8) — its column is wired and always empty, reported honestly as unpopulated rather than
faked. The derived "would this post-render defect have been caught pre-render" table therefore
only has ground truth once a real evaluator_vlm exists; until then this runner still produces
real pre-render detection data (verifier_spatial's actual catch rate), which is Phase A's actual
deliverable.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt2render import cfg
from prompt2render.harness.context import SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.loader import DEFAULT_CONFIG_PATH, load_config, resolve_order
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.harness.plugins import NON_PIPELINE, REGISTRY
from prompt2render.harness.runner import GateFailure, HarnessRunner

CONDITIONS = [
    {"spatial": False, "lifecycle": False},
    {"spatial": True, "lifecycle": False},
    {"spatial": False, "lifecycle": True},
    {"spatial": True, "lifecycle": True},
]


def _condition_config(base: dict, spatial_on: bool, lifecycle_on: bool) -> dict:
    """Phase A invariant: gates for both verifiers stay off no matter what — see module
    docstring. `enabled` is the only thing the 4-condition matrix actually toggles."""
    cfg_copy = copy.deepcopy(base)
    cfg_copy.setdefault("verifier_spatial", {})["enabled"] = spatial_on
    cfg_copy["verifier_spatial"]["gate_override"] = False
    cfg_copy.setdefault("verifier_lifecycle", {})["enabled"] = lifecycle_on
    cfg_copy["verifier_lifecycle"]["gate_override"] = False
    # generator_code must always be able to re-run for a fresh ablation pass, and renderer_stills
    # must always render, in every condition — so the {off, off} condition still renders per §3b.
    cfg_copy.setdefault("generator_code", {})["enabled"] = True
    cfg_copy.setdefault("renderer_stills", {})["enabled"] = True
    # verifier_audio is whole-video scoped (needs out/final.mp4, re-transcribes it) and orthogonal
    # to this experiment's spatial/lifecycle question — off in every condition, or every run would
    # pay its cost for no signal this runner reports.
    cfg_copy.setdefault("verifier_audio", {})["enabled"] = False
    return cfg_copy


def _by_category(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        cat = f.get("category", "UNKNOWN")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def run_condition(slug: str, spatial_on: bool, lifecycle_on: bool, base_config: dict) -> list[dict]:
    proj = cfg.project_dir(slug)
    condition_cfg = _condition_config(base_config, spatial_on, lifecycle_on)

    instances = []
    for name, cls in REGISTRY.items():
        if name in NON_PIPELINE:
            continue
        pcfg = dict(condition_cfg.get(name, {}))
        inst = cls(pcfg)
        if inst.enabled():
            instances.append(inst)
    plugins = resolve_order(instances)

    log_path = proj / "build" / "harness" / "ablation" / f"s{int(spatial_on)}_l{int(lifecycle_on)}.jsonl"
    logger = StructuredLogger(log_path)
    bus = EventBus()   # no repair_router attached — Phase A never routes on these findings
    runner = HarnessRunner(plugins, logger, bus)

    ctx = SceneContext(prompt=proj / "script.md", project_dir=proj)
    t0 = time.monotonic()
    try:
        ctx = runner.run(ctx, halt_on_gate_failure=True)
    except GateFailure as e:
        # Should not happen — both verifiers' gates are forced off above — but if some other
        # plugin's hard gate trips, surface it rather than silently reporting a partial row.
        sys.exit(f"[ablation] unexpected hard gate failure in condition "
                f"spatial={spatial_on} lifecycle={lifecycle_on}: {e}")
    render_time = time.monotonic() - t0

    pre_render = (ctx.check_results.get("verifier_spatial", []) +
                 ctx.check_results.get("verifier_lifecycle", []))
    post_render = ctx.check_results.get("evaluator_vlm", [])
    repair_cycles_used = sum(len(v) for v in ctx.repair_context.values())   # invariant: 0

    rows = []
    stems = sorted({f.get("stem") for f in pre_render if f.get("stem")}
                  or [e.stem for e in ctx.scene_plan])
    for stem in stems:
        stem_pre = [f for f in pre_render if f.get("stem") == stem]
        rows.append({
            "condition": {"spatial": spatial_on, "lifecycle": lifecycle_on},
            "section": stem,
            "pre_render_findings_by_category": _by_category(stem_pre),
            "post_render_findings_by_category": _by_category(post_render),  # always {} — see caveat
            "render_time_s": round(render_time, 3),
            "repair_cycles_used": repair_cycles_used,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default="hash-tables")
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    cfg.load_env()
    base_config = load_config(a.config or DEFAULT_CONFIG_PATH)

    all_rows = []
    for condition in CONDITIONS:
        print(f"[ablation] condition spatial={condition['spatial']} "
              f"lifecycle={condition['lifecycle']}")
        rows = run_condition(a.slug, condition["spatial"], condition["lifecycle"], base_config)
        all_rows.extend(rows)
        assert all(r["repair_cycles_used"] == 0 for r in rows), \
            "Phase A invariant violated: repair cycles were used"

    out_path = a.out or (cfg.project_dir(a.slug) / "build" / "harness" / "ablation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"[ablation] wrote {len(all_rows)} rows to {out_path}")

    # Derived table: only meaningful once evaluator_vlm has a real vision-model call (§8) — see
    # module docstring. Printed as an honest zero-row table, not omitted, so its absence is
    # visible rather than silently missing.
    would_have_caught = [r for r in all_rows if r["post_render_findings_by_category"]]
    print(f"[ablation] post-render-vs-pre-render derived rows: {len(would_have_caught)} "
          f"(0 expected — no live evaluator_vlm; see module docstring)")


if __name__ == "__main__":
    main()
