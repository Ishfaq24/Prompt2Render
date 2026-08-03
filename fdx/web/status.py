"""Derive each stage's completion from files already on disk.

No pipeline stage needs to run for this -- it's the same filesystem
evidence a human would check by eye (does build/master.wav exist? how many
build/align/*.json are there against the section count?). This backs both
the project list's badges and the pipeline panel's per-stage checkmarks.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..project import Script


def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def project_status(proj: Path, script: Script) -> dict:
    n = len(script.sections)
    build = proj / "build"

    aligned = sum(1 for s in script.sections
                 if (build / "align" / f"{s.stem}.json").exists())
    storyboarded = sum(1 for s in script.sections
                       if (build / "scenes" / f"scene_{s.stem}.py").exists())

    plan = _read_json(build / "plan.json")
    encoded, plan_total = 0, 0
    if plan:
        clips = plan.get("clips", [])
        plan_total = len(clips)
        for c in clips:
            p = proj / c["clip"]
            if p.exists() and p.stat().st_size > 2048:
                encoded += 1

    final = proj / "out" / "final.mp4"
    qc = _read_json(proj / "out" / "qc.json")
    qc_summary = None
    if qc:
        rows = qc.get("gates", [])
        qc_summary = {
            "pass": sum(1 for r in rows if r["status"] == "pass"),
            "warn": sum(1 for r in rows if r["status"] == "warn"),
            "fail": sum(1 for r in rows if r["status"] == "fail"),
            "skip": sum(1 for r in rows if r["status"] == "skip"),
            "shippable": not any(r["status"] == "fail" for r in rows),
        }

    return {
        "title": script.title,
        "sections": n,
        "voiced": (build / "master.wav").exists(),
        "aligned": aligned, "aligned_total": n,
        "storyboarded": storyboarded, "storyboarded_total": n,
        "planned": plan is not None,
        "encoded": encoded, "encoded_total": plan_total,
        "finished": final.exists(),
        "checked": qc is not None,
        "qc": qc_summary,
    }
