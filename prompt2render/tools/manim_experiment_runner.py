#!/usr/bin/env python3
"""
Manim Experiment Runner: Prompt2Render vs Code2Video

This script provides the scaffolding to run the experiment defined in
docs/MANIM_EXPERIMENT_PROTOCOL.md. It executes the Prompt2Render pipeline
in `--manim` mode across a list of topics and collects the results for
comparison against Code2Video's MMMC benchmark.

Usage:
    python tools/manim_experiment_runner.py --topics data/mmmc_subset.json --out out/manim_experiment.json
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

def run_p2r_manim(slug: str, title: str, topic: str, minutes: float = 5.0) -> dict:
    """Run Prompt2Render in auto --manim mode and return metrics."""
    start_time = time.time()
    
    print(f"\n[{slug}] Starting Prompt2Render Manim run...")
    
    # 1. Scaffold and run the pipeline
    cmd = [
        "python", "prompt2render.py", "auto", slug,
        "--title", title,
        "--minutes", str(minutes),
        "--harness", "--manim", "--strict"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        success = result.returncode == 0
    except Exception as e:
        print(f"[{slug}] Pipeline execution failed: {e}")
        return {"slug": slug, "success": False, "error": str(e)}
        
    end_time = time.time()
    
    # 2. Collect metrics
    project_dir = Path("projects") / slug
    log_path = project_dir / "build" / "harness" / "log.jsonl"
    repair_log_path = project_dir / "build" / "harness" / "repair_log.jsonl"
    qc_path = project_dir / "out" / "qc.json"
    
    metrics = {
        "slug": slug,
        "success": success,
        "wall_time_seconds": end_time - start_time,
        "return_code": result.returncode,
        "repair_cycles": 0,
        "caption_drift_p95_ms": None,
        "caption_drift_max_ms": None
    }
    
    # Count repair cycles
    if repair_log_path.exists():
        with open(repair_log_path, "r") as f:
            metrics["repair_cycles"] = sum(1 for line in f if line.strip())
            
    # Extract sync metrics if QC passed
    if qc_path.exists():
        try:
            with open(qc_path, "r") as f:
                qc_data = json.load(f)
                drift_data = next((item for item in qc_data if item.get("check") == "caption drift"), None)
                if drift_data and drift_data.get("status") in ("pass", "warn"):
                    # The detail string looks like: "p95 120 ms, max 250 ms over 40 sentences"
                    import re
                    detail = drift_data.get("detail", "")
                    m_p95 = re.search(r"p95 (\d+) ms", detail)
                    m_max = re.search(r"max (\d+) ms", detail)
                    if m_p95: metrics["caption_drift_p95_ms"] = int(m_p95.group(1))
                    if m_max: metrics["caption_drift_max_ms"] = int(m_max.group(1))
        except Exception as e:
            print(f"[{slug}] Failed to parse QC data: {e}")

    return metrics

def main():
    parser = argparse.ArgumentParser(description="Run Manim comparison experiment.")
    parser.add_argument("--topics", required=True, help="JSON file containing list of topics to run")
    parser.add_argument("--out", required=True, help="Output JSON file for results")
    args = parser.parse_args()
    
    topics_file = Path(args.topics)
    if not topics_file.exists():
        sys.exit(f"Error: Topics file {args.topics} not found.")
        
    with open(topics_file, "r") as f:
        topics = json.load(f)
        
    results = []
    for t in topics:
        slug = t.get("slug")
        title = t.get("title")
        topic_desc = t.get("topic")
        minutes = t.get("minutes", 5.0)
        
        if not slug or not title:
            print(f"Skipping invalid topic entry: {t}")
            continue
            
        metrics = run_p2r_manim(slug, title, topic_desc, minutes)
        results.append(metrics)
        
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
        
    print(f"\nExperiment complete. Results written to {args.out}")
    
    # Print summary
    successes = sum(1 for r in results if r["success"])
    print(f"Success rate: {successes}/{len(results)} ({(successes/len(results))*100:.1f}%)")

if __name__ == "__main__":
    main()
