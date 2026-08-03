"""Quality gates. `fdx check --strict` is what says the video is shippable.

The gate that matters most is caption drift, and it is the reason this module
exists at all: it re-runs the aligner against the **shipped** audio and
compares the result to the **shipped** captions. Every other measurement in
the pipeline is taken from something upstream of the final file. This one is
independent, and it is the only honest definition of "sync is correct".
"""
from __future__ import annotations

import json
import re
import statistics
import tempfile
from pathlib import Path

from . import align, asrmodel, captions, cfg, stills, textseg, timeline, voice
from .project import Script

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
_MARK = {PASS: " pass ", WARN: " warn ", FAIL: " FAIL ", SKIP: " skip "}


class Gates:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, status, name, detail="", **extra):
        self.rows.append({"status": status, "gate": name,
                          "detail": detail, **extra})

    @property
    def failed(self) -> bool:
        return any(r["status"] == FAIL for r in self.rows)

    def show(self) -> None:
        w = max(len(r["gate"]) for r in self.rows)
        for r in self.rows:
            print(f"[{_MARK[r['status']]}] {r['gate'].ljust(w)}  {r['detail']}")


# ------------------------------------------------------------- measures ----

def _astats(path: Path) -> dict:
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
                        "-i", str(path), "-map", "0:a:0",
                        "-af", "astats=measure_perchannel=none", "-f", "null", "-"])
    text = (proc.stderr or "") + (proc.stdout or "")
    out = {}
    for key, pat in (("clipped", r"Number of clipped samples:\s*(\d+)"),
                     ("peak_db", r"Peak level dB:\s*(-?[\d.inf]+)"),
                     ("noise_db", r"Noise floor dB:\s*(-?[\d.inf]+)")):
        if m := re.search(pat, text):
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass
    return out


def _detect(path: Path, filt: str, pat: str) -> list[float]:
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
                        "-i", str(path), "-af" if filt.startswith(("silence",))
                        else "-vf", filt, "-f", "null", "-"])
    text = (proc.stderr or "") + (proc.stdout or "")
    return [float(m) for m in re.findall(pat, text)]


# ---------------------------------------------------------------- gates ----

def _gate_layout(g: Gates, proj: Path, script: Script) -> None:
    import matplotlib.pyplot as plt
    from . import scenekit as k
    fails, warns, n = [], 0, 0
    for sec in script.sections:
        scene = stills.scene_path(proj, sec.stem)
        if not scene.exists():
            continue
        mod = stills.load(scene)
        for i, item in enumerate(mod.states()):
            name, cue, fn, opts = stills._unpack(item, i)
            steps = stills._steps_for(fn, opts)
            for step in range(steps):
                fig, ax = k.canvas()
                fn(ax, step) if steps > 1 else fn(ax)
                for p in k.audit(fig, ax, f"{sec.stem}/{name}"):
                    if p.level == "fail":
                        fails.append(str(p))
                    else:
                        warns += 1
                plt.close(fig)
                n += 1
    if not n:
        g.add(SKIP, "layout", "no scene modules")
    elif fails:
        g.add(FAIL, "layout", f"{len(fails)} of {n} stills fail: {fails[0][:90]}")
    else:
        g.add(PASS, "layout", f"{n} stills clean ({warns} warnings)")


def _gate_alignment(g: Gates, proj: Path, script: Script) -> None:
    worst, sources = 1.0, {}
    for sec in script.sections:
        d = align.load(proj, sec.stem)
        sources[sec.stem] = d["source"]
        worst = min(worst, d.get("confidence", 0.0))
    kinds = set(sources.values())
    if "proportional" in kinds:
        g.add(FAIL, "alignment", f"proportional timing in "
              f"{[s for s, v in sources.items() if v == 'proportional']}")
    elif kinds <= {"exact", "exact+asr"}:
        g.add(PASS, "alignment", f"{', '.join(sorted(kinds))} "
                                 f"(min confidence {worst:.2f})")
    else:
        g.add(WARN, "alignment", f"{', '.join(sorted(kinds))} "
                                 f"(min confidence {worst:.2f})")


def _gate_caption_drift(g: Gates, proj: Path, script: Script,
                        final: Path) -> None:
    """The decisive gate: re-align the shipped audio, compare to the shipped SRT."""
    model = asrmodel.available()
    if model is None:
        g.add(SKIP, "caption drift", "no ASR model — cannot verify independently")
        return
    amap = voice.audio_map(proj)
    deltas: list[float] = []
    with tempfile.TemporaryDirectory(prefix="fdx-qc-") as td:
        work = Path(td)
        wav = work / "final.wav"
        cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(final),
                 "-map", "0:a:0", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
        for sec in script.sections:
            o = amap["sections"][sec.stem]
            part = work / f"{sec.stem}.wav"
            align._slice(wav, o["start"], o["dur"], part)
            asr = align.transcribe(part, model, work)
            if not asr:
                continue
            sents = textseg.sentences(sec.narration)
            fresh, conf = align.reconcile(sents, align._asr_tokens(asr), o["dur"])
            if conf < align.CONF_FLOOR:
                continue
            shipped = align.load(proj, sec.stem)["sentences"]
            for a, b in zip(shipped, fresh):
                deltas.append(abs(a["start"] - b["start"]))
    if not deltas:
        g.add(SKIP, "caption drift", "alignment produced nothing to compare")
        return
    deltas.sort()
    p95 = deltas[int(len(deltas) * 0.95)]
    mx = deltas[-1]
    detail = f"p95 {p95*1000:.0f} ms, max {mx*1000:.0f} ms over {len(deltas)} sentences"
    if p95 <= 0.250 and mx <= 0.500:
        g.add(PASS, "caption drift", detail)
    elif p95 <= 0.400:
        g.add(WARN, "caption drift", detail)
    else:
        g.add(FAIL, "caption drift", detail)


def _gate_loudness(g: Gates, final: Path, target: float) -> None:
    m = voice.loudness_of(final)
    i, tp = float(m["input_i"]), float(m["input_tp"])
    detail = f"{i:.1f} LUFS, true peak {tp:.1f} dBTP (target {target:g})"
    if abs(i - target) <= 1.0 and tp <= -1.0:
        g.add(PASS, "loudness", detail)
    elif abs(i - target) <= 2.0 and tp <= -0.5:
        g.add(WARN, "loudness", detail)
    else:
        g.add(FAIL, "loudness", detail)


def _gate_clipping(g: Gates, final: Path) -> None:
    s = _astats(final)
    clipped = s.get("clipped", 0)
    noise = s.get("noise_db", -99)
    detail = (f"{clipped:.0f} clipped samples, peak {s.get('peak_db', 0):.1f} dB, "
              f"noise floor {noise:.0f} dB")
    if clipped > 0:
        g.add(FAIL, "clipping", detail)
    elif noise > -55:
        g.add(WARN, "clipping", detail)
    else:
        g.add(PASS, "clipping", detail)


def _gate_dead_air(g: Gates, final: Path) -> None:
    starts = _detect(final, "silencedetect=n=-45dB:d=1.5",
                     r"silence_duration:\s*([\d.]+)")
    long = [d for d in starts if d > 2.5]
    if long:
        g.add(FAIL, "dead air", f"{len(long)} gap(s) over 2.5s "
                                f"(longest {max(long):.1f}s)")
    elif starts:
        g.add(PASS, "dead air", f"{len(starts)} pause(s) over 1.5s, "
                                f"longest {max(starts):.1f}s")
    else:
        g.add(PASS, "dead air", "none over 1.5s")


def _gate_black(g: Gates, final: Path) -> None:
    hits = _detect(final, "blackdetect=d=0.10:pix_th=0.10",
                   r"black_duration:\s*([\d.]+)")
    # A dip to black is intentional only at the opening fade.
    if len(hits) > 1:
        g.add(WARN, "black frames", f"{len(hits)} black stretches")
    else:
        g.add(PASS, "black frames", f"{len(hits)} (opening fade)")


def _gate_freeze(g: Gates, final: Path) -> None:
    hits = _detect(final, "freezedetect=n=-60dB:d=14",
                   r"freeze_duration:\s*([\d.]+)")
    if hits:
        g.add(WARN, "frozen picture", f"{len(hits)} still(s) held over 14s "
                                      f"(longest {max(hits):.0f}s)")
    else:
        g.add(PASS, "frozen picture", "no still held over 14s")


def _gate_av_sync(g: Gates, proj: Path, script: Script, final: Path) -> None:
    info = cfg.probe(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    dv, da = float(v.get("duration") or 0), float(a.get("duration") or 0)
    delta = abs(dv - da)
    detail = f"video {dv:.3f}s, audio {da:.3f}s, delta {delta*1000:.0f} ms"
    if delta <= 1 / cfg.FPS:
        g.add(PASS, "a/v length", detail)
    elif delta <= 0.1:
        g.add(WARN, "a/v length", detail)
    else:
        g.add(FAIL, "a/v length", detail)

    amap = voice.audio_map(proj)
    bad = []
    for sec in script.sections:
        p = proj / "sections" / f"{sec.stem}.mp4"
        if not p.exists():
            continue
        want = round(amap["sections"][sec.stem]["dur"] * cfg.FPS)
        got = cfg.frame_count(p)
        if got != want:
            bad.append(f"{sec.stem}: {got}!={want}")
    g.add(FAIL if bad else PASS, "per-section sync",
          ", ".join(bad) if bad else f"all {len(script.sections)} sections exact")


def _gate_captions(g: Gates, proj: Path, script: Script) -> None:
    cards = captions.cards_for(proj, script)
    long_line = [c for c in cards
                 if any(len(l) > cfg.CAPTION_LINE for l in c["text"].split("\n"))]
    short = [c for c in cards if c["end"] - c["start"] < cfg.CAPTION_MIN_S - 0.01]
    fast = [c for c in cards
            if len(c["text"]) / max(c["end"] - c["start"], 0.1) > cfg.CAPTION_CPS * 1.2]
    problems = []
    if long_line:
        problems.append(f"{len(long_line)} over {cfg.CAPTION_LINE} chars/line")
    if short:
        problems.append(f"{len(short)} under {cfg.CAPTION_MIN_S}s")
    if fast:
        problems.append(f"{len(fast)} over {cfg.CAPTION_CPS:.0f} cps")
    g.add(WARN if problems else PASS, "captions",
          "; ".join(problems) if problems else f"{len(cards)} cards within limits")


def _gate_pacing(g: Gates, proj: Path) -> None:
    plan = timeline.load(proj)
    shots = [c["seconds"] for c in plan["clips"]]
    if not shots:
        g.add(SKIP, "pacing", "no plan")
        return
    mean = statistics.mean(shots)
    detail = (f"mean shot {mean:.1f}s, p95 {plan['pacing']['p95_shot_s']}s, "
              f"{len(shots)} shots")
    g.add(PASS if 3.0 <= mean <= 9.0 else WARN, "pacing", detail)


def _gate_concat(g: Gates, proj: Path) -> None:
    plan = timeline.load(proj)
    seen, ref = set(), None
    for r in plan["clips"]:
        p = proj / r["clip"]
        if not p.exists():
            continue
        params = tuple(sorted(cfg.video_params(p).items()))
        seen.add(params)
        ref = ref or params
    if len(seen) <= 1:
        g.add(PASS, "concat safety", "one encoder profile across all clips")
    else:
        g.add(FAIL, "concat safety", f"{len(seen)} different encoder profiles")


# --------------------------------------------------------------- driver ----

def check(proj: Path, script: Script, strict: bool = False) -> int:
    cfg.need("ffmpeg", "ffprobe")
    final = proj / "out" / "final.mp4"
    g = Gates()

    _gate_layout(g, proj, script)
    _gate_alignment(g, proj, script)
    _gate_captions(g, proj, script)
    _gate_pacing(g, proj)
    _gate_concat(g, proj)

    if not final.exists():
        g.add(SKIP, "final.mp4", "not built yet — run `fdx finish`")
    else:
        amap = voice.audio_map(proj)
        _gate_av_sync(g, proj, script, final)
        _gate_loudness(g, final, amap.get("lufs_target", cfg.LUFS))
        _gate_clipping(g, final)
        _gate_dead_air(g, final)
        _gate_black(g, final)
        _gate_freeze(g, final)
        _gate_caption_drift(g, proj, script, final)

    g.show()
    (proj / "out").mkdir(exist_ok=True)
    (proj / "out" / "qc.json").write_text(
        json.dumps({"gates": g.rows}, indent=2), encoding="utf-8")

    warns = sum(1 for r in g.rows if r["status"] == WARN)
    if g.failed:
        print("\n[fdx] not shippable — fix the FAILs above.")
        return 1
    if strict and warns:
        print(f"\n[fdx] {warns} warning(s), and --strict was asked for.")
        return 1
    print(f"\n[fdx] shippable{f' ({warns} warning(s))' if warns else ''}.")
    return 0
