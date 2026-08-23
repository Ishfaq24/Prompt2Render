"""Standalone entrypoint for the Prompt2Render harness — additive, does not touch prompt2render.py's CLI
(see the migration plan's reconciliation #10).

    python tools/harness_run.py <slug> [--config path/to/config.yaml] [--section N]

Writes build/harness/log.jsonl (and, once Stage 4 lands, build/harness/repair_log.jsonl) inside
the project directory, same as every other prompt2render build artifact.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt2render import cfg
from prompt2render.harness.context import SceneContext
from prompt2render.harness.events import EventBus
from prompt2render.harness.loader import build_plugins, build_repair_router
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.harness.runner import GateFailure, HarnessRunner


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug")
    ap.add_argument("--config", type=Path, default=None)
    a = ap.parse_args()

    cfg.load_env()
    proj = cfg.project_dir(a.slug)
    script_path = proj / "script.md"
    if not script_path.exists():
        sys.exit(f"[harness] no script.md at {script_path}")

    plugins = build_plugins(config_path=a.config)
    repair_router = build_repair_router(config_path=a.config)

    log_path = proj / "build" / "harness" / "log.jsonl"
    logger = StructuredLogger(log_path)
    bus = EventBus()
    if repair_router is not None:
        repair_router.attach(
            bus=bus,
            plugins_by_name={p.name: p for p in plugins},
            log_path=proj / "build" / "harness" / "repair_log.jsonl",
        )

    ctx = SceneContext(prompt=script_path, project_dir=proj)
    runner = HarnessRunner(plugins, logger, bus)

    print(f"[harness] running {len(plugins)} plugins over {a.slug}: "
          + " -> ".join(p.name for p in plugins))
    try:
        ctx = runner.run(ctx)
    except GateFailure as e:
        sys.exit(f"[harness] hard gate failed: {e}")

    print(f"[harness] done — log at {log_path}")
    for name, findings in ctx.check_results.items():
        for f in findings:
            print(f"  [{f.get('status', '?'):5}] {name}: {f.get('detail', '')}")


if __name__ == "__main__":
    main()
