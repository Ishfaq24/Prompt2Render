"""Stage 1 of the Prompt2Render migration: golden-baseline regression harness.

See docs/MIGRATION_INVENTORY.md for the migration this supports. `prompt2render scenes`
is the pipeline's one non-deterministic, external-API stage (Gemini); every
stage after it — stills, plan, encode, finish, check — is pure local
computation over files already on disk. So the baseline freezes a real
project's script/voice/align/scenes output as a fixture and re-runs only the
deterministic tail, fingerprinting the results instead of the raw video
bytes (ffmpeg's bitstream isn't guaranteed byte-reproducible even when the
pipeline's *behavior* is unchanged).

Usage:
    python tools/golden_baseline.py record [--slug hash-tables]
    python tools/golden_baseline.py verify [--slug hash-tables]

`record` runs the deterministic tail against the frozen fixture and writes
tests/golden/<slug>.baseline.json. `verify` re-runs it into a fresh scratch
copy and diffs the result against that file — this is the regression gate
later migration stages (the plugin wrap, repair_router, etc.) should run to
prove they haven't changed pipeline behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROJECTS = ROOT / "projects"
GOLDEN_DIR = ROOT / "tests" / "golden"
PYTHON = sys.executable
ENTRY = ROOT / "prompt2render.py"

# Only these are frozen fixture inputs; everything else in the work copy is
# produced fresh by the stages under test.
FROZEN = [
    "script.md",
    "build/voice",
    "build/align",
    "build/scenes",
    "build/audio_map.json",
    "build/master.wav",
    "build/master.m4a",
]
PRUNE_NAMES = {"__pycache__"}


def work_slug(slug: str) -> str:
    return f"_baseline_{slug}"


def _prune_pycache(root: Path) -> None:
    for p in list(root.rglob("__pycache__")):
        shutil.rmtree(p, ignore_errors=True)


def make_fixture(slug: str) -> Path:
    src = PROJECTS / slug
    if not src.exists():
        sys.exit(f"no such project: {src}")
    dst = PROJECTS / work_slug(slug)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for rel in FROZEN:
        s = src / rel
        if not s.exists():
            continue
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    _prune_pycache(dst)
    return dst


def run_stage(*args: str) -> None:
    cmd = [PYTHON, str(ENTRY), *args]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.returncode not in (0,):
        sys.exit(
            f"stage failed: {' '.join(args)} (exit {r.returncode})\n"
            f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
        )


def run_pipeline_tail(wslug: str) -> None:
    run_stage("stills", wslug, "--force")
    run_stage("plan", wslug)
    # cmd_encode exits 7 when more passes are needed (resumable design);
    # loop until it reports 0 left or gives up.
    for _ in range(10):
        cmd = [PYTHON, str(ENTRY), "encode", wslug, "--all"]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            break
        if r.returncode != 7:
            sys.exit(f"encode failed (exit {r.returncode})\n{r.stdout}\n{r.stderr}")
    else:
        sys.exit("encode: did not converge after 10 passes")
    run_stage("finish", wslug)
    # `check` exits nonzero on a failing gate; the baseline still wants the
    # qc.json it wrote, so run it directly instead of via run_stage.
    subprocess.run([PYTHON, str(ENTRY), "check", wslug, "--strict"], cwd=ROOT)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def ffprobe_stats(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    fmt = data.get("format", {})
    streams = []
    for s in data.get("streams", []):
        entry = {"codec_type": s.get("codec_type"), "codec_name": s.get("codec_name")}
        if s.get("codec_type") == "video":
            entry.update(
                width=s.get("width"),
                height=s.get("height"),
                r_frame_rate=s.get("r_frame_rate"),
                nb_frames=s.get("nb_frames"),
                pix_fmt=s.get("pix_fmt"),
            )
        elif s.get("codec_type") == "audio":
            entry.update(
                sample_rate=s.get("sample_rate"),
                channels=s.get("channels"),
            )
        streams.append(entry)
    return {
        "duration": round(float(fmt.get("duration", 0)), 3),
        "streams": streams,
    }


# JSON keys known to carry wall-clock/host-specific noise, stripped before
# fingerprinting rather than fingerprinted verbatim.
VOLATILE_KEYS = {"generated_at", "timestamp", "host", "elapsed_s", "elapsed_ms"}


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def fingerprint(d: Path) -> dict:
    fp: dict = {"json": {}, "png_hashes": {}, "video_stats": {}}

    for jf in sorted((d / "build" / "scenes").glob("*/manifest.json")):
        fp["json"][str(jf.relative_to(d))] = _strip_volatile(json.loads(jf.read_text()))
    for jf in sorted((d / "build" / "scenes").glob("*/audit.json")):
        fp["json"][str(jf.relative_to(d))] = _strip_volatile(json.loads(jf.read_text()))
    plan = d / "build" / "plan.json"
    if plan.exists():
        fp["json"]["build/plan.json"] = _strip_volatile(json.loads(plan.read_text()))
    qc = d / "out" / "qc.json"
    if qc.exists():
        fp["json"]["out/qc.json"] = _strip_volatile(json.loads(qc.read_text()))
    captions = d / "out" / "captions.srt"
    if captions.exists():
        fp["json"]["out/captions.srt"] = captions.read_text(encoding="utf-8")

    for png in sorted((d / "build" / "scenes").glob("*/*.png")):
        fp["png_hashes"][str(png.relative_to(d))] = sha256(png)

    for mp4 in sorted((d / "build" / "clips").glob("*.mp4")):
        fp["video_stats"][str(mp4.relative_to(d))] = ffprobe_stats(mp4)
    final = d / "out" / "final.mp4"
    if final.exists():
        fp["video_stats"]["out/final.mp4"] = ffprobe_stats(final)

    return fp


def diff_fingerprints(golden: dict, current: dict) -> list[str]:
    problems = []
    for section in ("json", "png_hashes", "video_stats"):
        g, c = golden.get(section, {}), current.get(section, {})
        for key in sorted(set(g) - set(c)):
            problems.append(f"{section}: missing in current run: {key}")
        for key in sorted(set(c) - set(g)):
            problems.append(f"{section}: new/unexpected in current run: {key}")
        for key in sorted(set(g) & set(c)):
            if g[key] != c[key]:
                problems.append(f"{section}: changed: {key}")
    return problems


def cmd_record(slug: str, keep: bool) -> None:
    d = make_fixture(slug)
    run_pipeline_tail(work_slug(slug))
    fp = fingerprint(d)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out = GOLDEN_DIR / f"{slug}.baseline.json"
    out.write_text(json.dumps(fp, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out} ({len(fp['json'])} json, {len(fp['png_hashes'])} pngs, "
          f"{len(fp['video_stats'])} videos)")
    if not keep:
        shutil.rmtree(d, ignore_errors=True)


def cmd_verify(slug: str, keep: bool) -> int:
    golden_path = GOLDEN_DIR / f"{slug}.baseline.json"
    if not golden_path.exists():
        sys.exit(f"no golden baseline recorded yet: {golden_path} — run `record` first")
    golden = json.loads(golden_path.read_text())

    d = make_fixture(slug)
    run_pipeline_tail(work_slug(slug))
    current = fingerprint(d)
    if not keep:
        shutil.rmtree(d, ignore_errors=True)

    problems = diff_fingerprints(golden, current)
    if problems:
        print(f"FAIL — {len(problems)} mismatch(es) vs {golden_path}:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"PASS — current run matches {golden_path}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["record", "verify"])
    ap.add_argument("--slug", default="hash-tables")
    ap.add_argument("--keep", action="store_true",
                     help="keep the scratch project copy instead of deleting it")
    a = ap.parse_args()

    if a.mode == "record":
        cmd_record(a.slug, a.keep)
    else:
        sys.exit(cmd_verify(a.slug, a.keep))


if __name__ == "__main__":
    main()
