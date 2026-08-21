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
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import cfg, scenekit as k


def load(path: Path):
    spec = importlib.util.spec_from_file_location("prompt2render_scene_mod", path)
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


def _takes_step(fn) -> bool:
    """Does this draw function want a `step` argument?

    `inspect.signature()` is not cheap and render() used to call it twice per
    *step* — once in _steps_for and again in the draw loop. Cached on the
    function object, which is exactly as long-lived as the answer is valid.
    """
    got = getattr(fn, "_p2r_takes_step", None)
    if got is None:
        got = len(inspect.signature(fn).parameters) >= 2
        try:
            fn._p2r_takes_step = got
        except (AttributeError, TypeError):      # a builtin or a slotted callable
            pass
    return got


def _steps_for(fn, opts: dict) -> int:
    """How many stills this state renders."""
    takes_step = _takes_step(fn)
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
    try:
        sts = mod.states()
    except SystemExit:
        raise
    except Exception:
        # Same reasoning as load(): a mistake inside states() itself (e.g. an
        # import placed inside the function instead of module scope) should
        # go back to the generator's retry loop, not crash the whole batch.
        raise SystemExit("states() raised while building the state list:\n"
                         + traceback.format_exc(limit=6))
    if not isinstance(sts, list) or not sts:
        raise SystemExit("states() must return a non-empty list")

    outdir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    problems: list[str] = []
    # Warnings are kept whatever `strict` says, so the recorded verdict can
    # answer `prompt2render check`'s layout gate (which counts them) without a re-render.
    warnings: list[str] = []
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
        wants_step = _takes_step(fn)
        for step in range(n_steps):
            fig, ax = k.canvas()
            try:
                if wants_step:
                    fn(ax, step)
                else:
                    fn(ax)
            except SystemExit:
                raise
            except Exception:
                k.close(fig)
                where = name if n_steps == 1 else f"{name} step {step}"
                raise SystemExit(f"state {where} raised while drawing:\n"
                                 + traceback.format_exc(limit=6))

            for p in k.audit(fig, ax, name if n_steps == 1
                             else f"{name} step {step}"):
                if p.level != "fail":
                    warnings.append(str(p))
                if p.level == "fail" or not strict:
                    problems.append(str(p))

            suffix = f"_s{step}" if n_steps > 1 else ""
            png = outdir / f"{len(manifest):03d}_{name}{suffix}.png"
            if check:
                k.close(fig)
            else:
                # k.save reuses the rasterisation audit() just did rather
                # than rendering the frame a second time.
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
        # The audit verdict is recorded next to the frames it describes. It is
        # a pure function of (this scene module, this scenekit), both of which
        # is_current() checks, so `prompt2render check`'s layout gate can read the answer
        # instead of re-executing every module and re-rendering every frame to
        # recompute a value that cannot have changed.
        (outdir / "audit.json").write_text(json.dumps(
            {"stills": len(manifest), "warnings": warnings}, indent=2),
            encoding="utf-8")
        (outdir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def render_into(scene: Path, outdir: Path, max_cue: int | None = None,
                strict: bool = True) -> list[dict]:
    """Render a section for real, and only call it done if the audit passes.

    Used by `prompt2render scenes`, which needs to know whether a generated module is
    acceptable before it accepts it. The old flow answered that with a
    `check=True` render — every frame drawn, measured, and then thrown away,
    leaving `prompt2render stills` to draw all of them again. Drawing them once and
    keeping the pixels means an accepted section is already finished.

    Commitment is the manifest, not the PNG files. render() writes
    manifest.json and audit.json only after the audit passes, and is_current()
    requires both plus every PNG they name — so a rejected attempt leaves
    loose frames that nothing downstream will read, and the next attempt
    overwrites them. That is deliberately not a directory swap: renaming a
    directory over an existing one is not portable (it fails outright on a
    non-empty target on POSIX, and behaves differently again on network
    mounts), and this needs no atomicity that the manifest does not give.
    """
    man = render(scene, outdir, max_cue=max_cue, check=False, strict=strict)
    keep = {e["png"] for e in man} | {"manifest.json", "audit.json"}
    for stray in outdir.glob("*.png"):
        if stray.name not in keep:
            stray.unlink(missing_ok=True)     # left by a rejected attempt
    return man


def is_current(scene: Path, outdir: Path) -> bool:
    """Are this section's stills already rendered from *this* scene module?

    Compared against the drawing kit as well as the module: a change to
    scenekit.py changes every frame it draws, and silently serving stale PNGs
    after one would be the worst kind of caching bug.
    """
    man = outdir / "manifest.json"
    if not man.exists() or not (outdir / "audit.json").exists() \
            or not scene.exists():
        return False
    try:
        stamp = man.stat().st_mtime
        if stamp < scene.stat().st_mtime:
            return False
        if stamp < Path(k.__file__).stat().st_mtime:
            return False
        entries = json.loads(man.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(entries) and all((outdir / e["png"]).exists() for e in entries)


def audit_record(outdir: Path) -> dict | None:
    """The recorded layout verdict for a section, if one was written."""
    p = outdir / "audit.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _render_job(args: tuple) -> tuple[str, int]:
    """Pool worker. Top-level and tuple-argued so it pickles on Windows."""
    stem, scene, outdir, max_cue, check, strict = args
    if check:
        return stem, len(render(Path(scene), Path(outdir), max_cue=max_cue,
                               check=True, strict=strict))
    return stem, len(render_into(Path(scene), Path(outdir), max_cue=max_cue,
                                 strict=strict))


def default_jobs(n_sections: int) -> int:
    """Sections to render at once.

    Rendering is pure CPU inside matplotlib, so this scales with cores rather
    than with I/O. Processes, not threads: FreeType's shared font objects are
    not safe to drive from two threads at once, and a generated scene module
    is arbitrary code that is better off in its own interpreter anyway.
    """
    want = cfg.env_int("P2R_STILLS_JOBS", 0)
    if want > 0:
        return max(1, min(want, n_sections or 1))
    return max(1, min(4, os.cpu_count() or 1, n_sections or 1))


def render_many(jobs: list[tuple], workers: int | None = None,
                check: bool = False) -> dict[str, int]:
    """Render several sections, in parallel when there is more than one.

    `jobs` is a list of (stem, scene, outdir, max_cue). A single section stays
    in this process: spawning an interpreter to re-import matplotlib costs
    more than it saves.
    """
    if not jobs:
        return {}
    n = workers or default_jobs(len(jobs))
    payload = [(stem, str(scene), str(outdir), max_cue, check, True)
               for stem, scene, outdir, max_cue in jobs]
    if n <= 1 or len(payload) == 1:
        return dict(_render_job(p) for p in payload)

    cfg.say(f"rendering {len(payload)} sections, {n} at a time")
    out: dict[str, int] = {}
    with ProcessPoolExecutor(max_workers=n) as pool:
        futures = {pool.submit(_render_job, p): p[0] for p in payload}
        try:
            for fut in as_completed(futures):
                stem, count = fut.result()
                out[stem] = count
                cfg.say(f"section {stem}: {count} stills")
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    return out


def scene_path(proj: Path, stem: str) -> Path:
    return proj / "build" / "scenes" / f"scene_{stem}.py"


def stills_dir(proj: Path, stem: str) -> Path:
    return proj / "build" / "scenes" / stem


def manifest(proj: Path, stem: str) -> list[dict]:
    p = stills_dir(proj, stem) / "manifest.json"
    if not p.exists():
        sys.exit(f"[prompt2render] no stills for section {stem} — run `prompt2render stills`")
    return json.loads(p.read_text(encoding="utf-8"))
