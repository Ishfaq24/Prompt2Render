"""Execute a generated scene module and write its stills.

The `states()` contract, extended for progressive reveal:

    def states():
        def s01(ax):                      # 3-tuple: one still, as before
            ...
        def s04(ax, step):                # 4-tuple: `steps` stills
            k.title(ax, "Look at the middle element")
            k.array(ax, arr, mid=7 if step >= 1 else None,
                    bracket="target is > 45" if step >= 2 else None)
        return [("s01", 0, s01),
                ("s04", 12, s04, {"steps": 3, "anchor": "the middle element"})]

Three-tuples stay valid, so the scene modules already on disk keep working.
The reveal is what turns a slideshow into something constructed: instead of
cutting to a whole new frame, elements arrive as the words that name them are
spoken.

`--check` renders into a throwaway figure and runs the layout audit without
writing PNGs. That is what the generator uses to decide whether the model's
code is acceptable — and, unlike a stack trace, an audit failure is something
the model can actually act on.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import traceback
from pathlib import Path

import matplotlib.pyplot as plt

from . import cfg, scenekit as k


def load(path: Path):
    spec = importlib.util.spec_from_file_location("fdx_scene_mod", path)
    mod = importlib.util.module_from_spec(spec)
    mod.k = k                      # the kit is injected, not imported
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        raise
    except Exception:
        # A stray `import k`, a typo, anything that blows up at module scope —
        # this is exactly the kind of mistake the generator's retry loop
        # should see and fix, not a reason to crash the whole batch.
        raise SystemExit("scene module failed to load:\n"
                         + traceback.format_exc(limit=6))
    return mod


def _unpack(item, i: int) -> tuple[str, int, object, dict]:
    if not isinstance(item, (list, tuple)) or len(item) not in (3, 4):
        raise SystemExit(f"state {i} is not a (name, cue, fn) triple "
                         f"or (name, cue, fn, opts) quad")
    name, cue, fn = item[0], int(item[1]), item[2]
    opts = dict(item[3]) if len(item) == 4 and item[3] else {}
    if not callable(fn):
        raise SystemExit(f"state {name}: the third element must be a function")
    return str(name), cue, fn, opts


def _steps_for(fn, opts: dict) -> int:
    """How many stills this state renders."""
    takes_step = len(inspect.signature(fn).parameters) >= 2
    n = int(opts.get("steps", 1))
    if not takes_step:
        if n > 1:
            raise SystemExit(
                f"a state declares steps={n} but its draw function takes only "
                f"(ax) — it must take (ax, step) to reveal anything")
        return 1
    return max(n, 1)


def render(scene: Path, outdir: Path, max_cue: int | None = None,
           check: bool = False, strict: bool = True) -> list[dict]:
    mod = load(scene)
    if not hasattr(mod, "states"):
        raise SystemExit("scene module defines no states()")
    sts = mod.states()
    if not isinstance(sts, list) or not sts:
        raise SystemExit("states() must return a non-empty list")

    outdir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    problems: list[str] = []
    prev_cue = -1

    for i, item in enumerate(sts):
        name, cue, fn, opts = _unpack(item, i)
        if i == 0 and cue != 0:
            raise SystemExit(
                f"first state must cue on sentence 0, got {cue} — the section "
                f"would open on a blank screen")
        if cue <= prev_cue:
            raise SystemExit(
                f"state {name} cues on sentence {cue}, which is not after the "
                f"previous state's {prev_cue}; cue indices must increase")
        if max_cue is not None and cue > max_cue:
            raise SystemExit(
                f"state {name} cues on sentence {cue} but the section only has "
                f"sentences 0..{max_cue}")
        prev_cue = cue

        n_steps = _steps_for(fn, opts)
        for step in range(n_steps):
            fig, ax = k.canvas()
            try:
                if n_steps > 1 or len(inspect.signature(fn).parameters) >= 2:
                    fn(ax, step)
                else:
                    fn(ax)
            except SystemExit:
                raise
            except Exception:
                plt.close(fig)
                where = name if n_steps == 1 else f"{name} step {step}"
                raise SystemExit(f"state {where} raised while drawing:\n"
                                 + traceback.format_exc(limit=6))

            for p in k.audit(fig, ax, name if n_steps == 1
                             else f"{name} step {step}"):
                if p.level == "fail" or not strict:
                    problems.append(str(p))

            suffix = f"_s{step}" if n_steps > 1 else ""
            png = outdir / f"{len(manifest):03d}_{name}{suffix}.png"
            if check:
                plt.close(fig)
            else:
                k.save(fig, png)

            manifest.append({
                "i": len(manifest), "name": name, "cue": cue,
                "step": step, "steps": n_steps,
                "kind": "state" if step == 0 else "reveal",
                "anchor": opts.get("anchor", ""),
                "png": png.name,
            })

    fails = [p for p in problems if p.startswith("FAIL")]
    if fails:
        # Raised, not printed, so the generator's retry loop receives it as
        # the model-facing error text.
        raise SystemExit("layout audit failed:\n  " + "\n  ".join(fails))
    for p in problems:
        cfg.warn(p)

    if not check:
        (outdir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def scene_path(proj: Path, stem: str) -> Path:
    return proj / "build" / "scenes" / f"scene_{stem}.py"


def stills_dir(proj: Path, stem: str) -> Path:
    return proj / "build" / "scenes" / stem


def manifest(proj: Path, stem: str) -> list[dict]:
    p = stills_dir(proj, stem) / "manifest.json"
    if not p.exists():
        sys.exit(f"[fdx] no stills for section {stem} — run `fdx stills`")
    return json.loads(p.read_text(encoding="utf-8"))
