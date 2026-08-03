"""Execute a generated scene module and write its stills.

    python tools/render_scene.py <scene.py> <outdir> [--check]

--check runs every draw function into a throwaway figure and validates the
result without writing PNGs, which is what the generator uses to decide whether
the model's code is acceptable.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import scenekit as k  # noqa: E402


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("scene_mod", path)
    mod = importlib.util.module_from_spec(spec)
    mod.k = k                      # the kit is injected, not imported
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("outdir")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--max-cue", type=int, default=None)
    a = ap.parse_args()

    mod = load(pathlib.Path(a.scene))
    if not hasattr(mod, "states"):
        raise SystemExit("scene module defines no states()")
    sts = mod.states()
    if not isinstance(sts, list) or not sts:
        raise SystemExit("states() must return a non-empty list")

    outdir = pathlib.Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    manifest = []
    prev_cue = -1
    for i, item in enumerate(sts):
        if not (isinstance(item, (list, tuple)) and len(item) == 3):
            raise SystemExit(f"state {i} is not a (name, cue_index, fn) triple")
        name, cue, fn = item
        cue = int(cue)
        if i == 0 and cue != 0:
            raise SystemExit(
                f"first state must cue on sentence 0, got {cue} — the section "
                f"would open on a blank screen")
        if cue <= prev_cue:
            raise SystemExit(
                f"state {name} cues on sentence {cue}, which is not after the "
                f"previous state's {prev_cue}; cue indices must increase")
        if a.max_cue is not None and cue > a.max_cue:
            raise SystemExit(
                f"state {name} cues on sentence {cue} but the section only has "
                f"sentences 0..{a.max_cue}")
        prev_cue = cue
        fig, ax = k.canvas()
        fn(ax)                      # a raised exception here fails the check
        png = outdir / f"{i:03d}_{name}.png"
        if a.check:
            import matplotlib.pyplot as plt
            plt.close(fig)
        else:
            k.save(fig, png)
        manifest.append({"i": i, "name": str(name), "cue": cue,
                         "png": str(png)})

    if not a.check:
        (outdir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"{len(manifest)} states, cues "
          f"{[m['cue'] for m in manifest]}")


if __name__ == "__main__":
    main()
