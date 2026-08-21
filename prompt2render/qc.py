"""Quality gates. `prompt2render check --strict` is what says the video is shippable.

The gate that matters most is caption drift, and it is the reason this module
exists at all: it re-runs the aligner against the **shipped** audio and
compares the result to the **shipped** captions. Every other measurement in
the pipeline is taken from something upstream of the final file. This one is
independent, and it is the only honest definition of "sync is correct".
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
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

#: The audio measurements every audio gate needs, as one filter chain. astats,
#: silencedetect and loudnorm are all analysers -- they pass the samples
#: through untouched and report to the log -- so chaining them measures the
#: same signal each would have measured alone. That matters because the three
#: gates used to be three full decodes of the finished file.
AUDIO_CHAIN = ("astats=measure_perchannel=none,"
               "silencedetect=n=-45dB:d=1.5")

#: Same idea on the video side: blackdetect and freezedetect both pass frames
#: through, so one decode answers both gates instead of two.
VIDEO_CHAIN = ("blackdetect=d=0.05:pix_th=0.05,"
               "freezedetect=n=-60dB:d=14")

_ASTAT_PATTERNS = (("clipped", r"Number of clipped samples:\s*(\d+)"),
                   ("peak_db", r"Peak level dB:\s*(-?[\d.inf]+)"),
                   ("noise_db", r"Noise floor dB:\s*(-?[\d.inf]+)"))


def _log_of(proc) -> str:
    return (proc.stderr or "") + (proc.stdout or "")


def _floats(text: str, pat: str) -> list[float]:
    return [float(m) for m in re.findall(pat, text)]


def analyse_audio(path: Path, lufs: float) -> dict:
    """Every audio measurement `prompt2render check` needs, in one pass over the file.

    loudnorm joins the same chain when this ffmpeg supports `stats_file`
    (8.x does; it is what prompt2render/voice.py's mastering already relies on). Where
    it does not, the loudness measurement falls back to its own pass and only
    that one gate pays for it.
    """
    with tempfile.TemporaryDirectory(prefix="prompt2render-qc-a") as td:
        stats = Path(td) / "ln.json"
        chain = (f"{AUDIO_CHAIN},loudnorm=I={lufs}:TP={cfg.TRUE_PEAK}:"
                 f"LRA={cfg.LRA}:print_format=json:"
                 f"stats_file={cfg.filter_path(stats)}")
        proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
                            "-i", str(path), "-map", "0:a:0",
                            "-af", chain, "-f", "null", "-"])
        text, loud = _log_of(proc), None
        if proc.returncode == 0 and stats.exists():
            try:
                raw = stats.read_text(encoding="utf-8")
                loud = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
            except (OSError, ValueError):
                loud = None
        if proc.returncode != 0:
            # Almost certainly an ffmpeg without loudnorm's stats_file. Retry
            # the analysers that definitely exist, and let the loudness gate
            # measure on its own.
            proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v",
                                "info", "-i", str(path), "-map", "0:a:0",
                                "-af", AUDIO_CHAIN, "-f", "null", "-"])
            text = _log_of(proc)

    out: dict = {"loudness": loud,
                 "silences": _floats(text, r"silence_duration:\s*([\d.]+)")}
    for key, pat in _ASTAT_PATTERNS:
        if m := re.search(pat, text):
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass
    return out


def analyse_video(path: Path) -> dict:
    """Black-frame and frozen-picture detection, in one pass over the file."""
    proc = cfg.try_run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
                        "-i", str(path), "-vf", VIDEO_CHAIN, "-f", "null", "-"])
    text = _log_of(proc)
    return {"black": _floats(text, r"black_duration:\s*([\d.]+)"),
            "freeze": _floats(text, r"freeze_duration:\s*([\d.]+)")}


# ---------------------------------------------------------------- gates ----

def _audit_section(proj: Path, stem: str) -> tuple[list[str], int, int]:
    """(fails, warn count, still count) for one section's layout.

    The audit is a pure function of the scene module and the drawing kit, and
    `prompt2render stills` already ran it and recorded the verdict beside the frames it
    produced. When both inputs are untouched since then, re-executing the
    module and re-rasterising every frame recomputes a value that provably
    cannot have changed -- and on a full-length video that was minutes of
    matplotlib for an answer already sitting on disk. Anything stale, missing
    or unreadable falls through to the real thing.
    """
    scene = stills.scene_path(proj, stem)
    outdir = stills.stills_dir(proj, stem)
    if stills.is_current(scene, outdir):
        rec = stills.audit_record(outdir)
        if rec is not None:
            return [], len(rec.get("warnings", [])), int(rec.get("stills", 0))

    from . import scenekit as k
    fails, warns, n = [], 0, 0
    mod = stills.load(scene)
    for i, item in enumerate(mod.states()):
        name, cue, fn, opts = stills._unpack(item, i)
        steps = stills._steps_for(fn, opts)
        for step in range(steps):
            fig, ax = k.canvas()
            fn(ax, step) if stills._takes_step(fn) else fn(ax)
            for p in k.audit(fig, ax, f"{stem}/{name}"):
                if p.level == "fail":
                    fails.append(str(p))
                else:
                    warns += 1
            k.close(fig)
            n += 1
    return fails, warns, n


def _gate_layout(g: Gates, proj: Path, script: Script) -> None:
    stems = [s.stem for s in script.sections
             if stills.scene_path(proj, s.stem).exists()]
    fails: list[str] = []
    warns = n = 0
    for stem in stems:
        f, w, c = _audit_section(proj, stem)
        fails += f
        warns += w
        n += c
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


def _drift_for_section(sec, proj: Path, o: dict, work: Path, wav: Path,
                       model: Path) -> list[float]:
    """One section's alignment deltas against its shipped captions."""
    # align.transcribe() writes a fixed "words.srt" into whatever workdir
    # it's given -- fine for the single call transcribe_programme() makes,
    # but concurrent sections sharing one `work` dir would race on that
    # same filename (two threads unlink/write it at once). Each section
    # gets its own subdirectory instead.
    sub = work / f"_{sec.stem}"
    sub.mkdir(exist_ok=True)
    part = sub / f"{sec.stem}.wav"
    align._slice(wav, o["start"], o["dur"], part)
    asr = align.transcribe(part, model, sub)
    deltas: list[float] = []
    if asr:
        sents = textseg.sentences(sec.narration)
        fresh, conf = align.reconcile(sents, align._asr_tokens(asr), o["dur"])
        if conf >= align.CONF_FLOOR:
            shipped = align.load(proj, sec.stem)["sentences"]
            for a, b in zip(shipped, fresh):
                deltas.append(abs(a["start"] - b["start"]))
    cfg.say(f"caption drift: section {sec.stem} checked")
    return deltas


def _drift_cache_path(proj: Path) -> Path:
    return proj / "build" / "qc" / "drift_cache.json"


def _final_sig(final: Path, model_name: str) -> str:
    st = final.stat()
    raw = f"{st.st_size}|{st.st_mtime_ns}|{model_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def caption_drift(proj: Path, script: Script, final: Path, model: Path,
                  jobs: int | None = None) -> dict:
    """Independently re-align the shipped audio, compare to the shipped captions.

    Each section's re-transcription is a fully independent whisper pass over
    its own audio slice, so this is parallelized the same way `prompt2render encode`
    is: a thread pool per section (each blocks on its own ffmpeg/whisper
    subprocess, releasing the GIL while waiting), with `deltas` aggregated
    only in the main thread as futures complete -- no lock needed, and it's
    what keeps the p95/max maths correct regardless of finishing order.

    Cached by (final.mp4's size+mtime, ASR model name): `prompt2render check` and the
    harness's `verifier_audio` plugin both call this -- independently re-transcribing
    the same shipped video is wasted minutes if both ever run against one build.
    A false cache miss (final.mp4 touched without changing) just costs a
    recompute; nothing here is safety-critical to invalidate eagerly on.
    """
    sig = _final_sig(final, model.name)
    cache_path = _drift_cache_path(proj)
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("sig") == sig:
                return cached["result"]
        except (OSError, ValueError):
            pass

    amap = voice.audio_map(proj)
    n = max(1, jobs or cfg.env_int("P2R_QC_JOBS", 3))
    n = min(n, len(script.sections) or 1, os.cpu_count() or n)

    deltas: list[float] = []
    with tempfile.TemporaryDirectory(prefix="prompt2render-qc-") as td:
        work = Path(td)
        wav = work / "final.wav"
        cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(final),
                 "-map", "0:a:0", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(_drift_for_section, sec, proj,
                                   amap["sections"][sec.stem], work, wav, model)
                      for sec in script.sections]
            for fut in as_completed(futures):
                deltas.extend(fut.result())

    if not deltas:
        result = {"status": SKIP, "detail": "alignment produced nothing to compare"}
    else:
        deltas.sort()
        p95 = deltas[int(len(deltas) * 0.95)]
        mx = deltas[-1]
        detail = f"p95 {p95*1000:.0f} ms, max {mx*1000:.0f} ms over {len(deltas)} sentences"
        if p95 <= 0.250 and mx <= 0.500:
            status = PASS
        elif p95 <= 0.400:
            status = WARN
        else:
            status = FAIL
        result = {"status": status, "detail": detail}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"sig": sig, "result": result}, indent=2),
                          encoding="utf-8")
    return result


def _gate_caption_drift(g: Gates, proj: Path, script: Script,
                        final: Path, jobs: int | None = None) -> None:
    """The decisive gate: re-align the shipped audio, compare to the shipped SRT."""
    model = asrmodel.available()
    if model is None:
        # WARN, not SKIP: this is "the only honest definition of sync is
        # correct" per the module docstring above, so a build can't quietly
        # certify shippable with the one independent check unrun. SKIP is
        # for gates with genuinely nothing to check (no plan, no scenes
        # yet) -- this one has something to check and just didn't.
        g.add(WARN, "caption drift", "no ASR model — cannot verify sync "
              "independently; run `prompt2render models --asr base.en` to enable "
              "this gate")
        return
    result = caption_drift(proj, script, final, model, jobs)
    g.add(result["status"], "caption drift", result["detail"])


def _gate_loudness(g: Gates, final: Path, target: float,
                   measured: dict | None = None) -> None:
    m = measured or voice.loudness_of(final)
    i, tp = float(m["input_i"]), float(m["input_tp"])
    detail = f"{i:.1f} LUFS, true peak {tp:.1f} dBTP (target {target:g})"
    if abs(i - target) <= 1.0 and tp <= -1.0:
        g.add(PASS, "loudness", detail)
    elif abs(i - target) <= 2.0 and tp <= -0.5:
        g.add(WARN, "loudness", detail)
    else:
        g.add(FAIL, "loudness", detail)


def _gate_clipping(g: Gates, final: Path, s: dict) -> None:
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


def _gate_dead_air(g: Gates, starts: list[float]) -> None:
    long = [d for d in starts if d > 2.5]
    if long:
        g.add(FAIL, "dead air", f"{len(long)} gap(s) over 2.5s "
                                f"(longest {max(long):.1f}s)")
    elif starts:
        g.add(PASS, "dead air", f"{len(starts)} pause(s) over 1.5s, "
                                f"longest {max(starts):.1f}s")
    else:
        g.add(PASS, "dead air", "none over 1.5s")


def _gate_black(g: Gates, hits: list[float]) -> None:
    # pix_th must sit below scenekit.BG's own luma (~6.5% for #0d1117) or
    # every sparse, mostly-background state -- a title card, a closing
    # teaser -- reads as "black" on nothing but its dark theme, not because
    # anything is actually missing. 0.05/d=0.05 is empirically the tightest
    # band that still catches the real fade from (0,0,0) at the open (a
    # single 0.1s hit, verified against a shipped render) while clearing
    # every dark-but-populated state.
    #
    # A dip to black is intentional only at the opening fade.
    if len(hits) > 1:
        g.add(WARN, "black frames", f"{len(hits)} black stretches")
    else:
        g.add(PASS, "black frames", f"{len(hits)} (opening fade)")


def _gate_freeze(g: Gates, hits: list[float]) -> None:
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
    # One ffprobe per section, all in flight together: each is a separate
    # process that spends its time reading the file, not competing for CPU.
    have = [(sec, proj / "sections" / f"{sec.stem}.mp4")
            for sec in script.sections
            if (proj / "sections" / f"{sec.stem}.mp4").exists()]
    counts = cfg.parallel(lambda t: cfg.frame_count(t[1]), have,
                          cfg.probe_jobs(), "framecount")
    bad = []
    for (sec, _), got in zip(have, counts):
        want = round(amap["sections"][sec.stem]["dur"] * cfg.FPS)
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
    clips = [proj / r["clip"] for r in plan["clips"]]
    clips = [p for p in clips if p.exists()]
    seen = {tuple(sorted(v.items()))
            for v in cfg.parallel(cfg.video_params, clips,
                                  cfg.probe_jobs(), "vparams")}
    if len(seen) <= 1:
        g.add(PASS, "concat safety", "one encoder profile across all clips")
    else:
        g.add(FAIL, "concat safety", f"{len(seen)} different encoder profiles")


# --------------------------------------------------------------- driver ----

def _run_gate(name: str, fn, *a, **kw) -> None:
    # check() used to run all ~13 gates back-to-back with zero printed
    # output between them -- on the caption-drift gate alone that's tens of
    # minutes of a stage that looks hung. This is the only signal `prompt2render check`
    # gives between gates; the caption-drift gate adds its own per-section
    # progress on top (see _drift_for_section).
    cfg.say(f"gate: {name}")
    fn(*a, **kw)


def check(proj: Path, script: Script, strict: bool = False) -> int:
    cfg.need("ffmpeg", "ffprobe")
    final = proj / "out" / "final.mp4"
    g = Gates()

    _run_gate("layout", _gate_layout, g, proj, script)
    _run_gate("alignment", _gate_alignment, g, proj, script)
    _run_gate("captions", _gate_captions, g, proj, script)
    _run_gate("pacing", _gate_pacing, g, proj)
    _run_gate("concat safety", _gate_concat, g, proj)

    if not final.exists():
        g.add(SKIP, "final.mp4", "not built yet — run `prompt2render finish`")
    else:
        amap = voice.audio_map(proj)
        target = amap.get("lufs_target", cfg.LUFS)

        # Six of the seven remaining gates used to be six separate full
        # decodes of final.mp4, run back to back. They are now two -- one
        # audio chain, one video chain -- and those two run at the same time
        # as each other, because one reads the audio stream and the other the
        # video stream and neither needs the other's answer.
        cfg.say("gate: measuring final.mp4 (one audio pass, one video pass)")
        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(analyse_audio, final, target)
            fv = pool.submit(analyse_video, final)
            a, v = fa.result(), fv.result()

        _run_gate("a/v sync", _gate_av_sync, g, proj, script, final)
        _run_gate("loudness", _gate_loudness, g, final, target, a.get("loudness"))
        _run_gate("clipping", _gate_clipping, g, final, a)
        _run_gate("dead air", _gate_dead_air, g, a["silences"])
        _run_gate("black frames", _gate_black, g, v["black"])
        _run_gate("frozen picture", _gate_freeze, g, v["freeze"])
        _run_gate("caption drift", _gate_caption_drift, g, proj, script, final)

    g.show()
    (proj / "out").mkdir(exist_ok=True)
    (proj / "out" / "qc.json").write_text(
        json.dumps({"gates": g.rows}, indent=2), encoding="utf-8")

    warns = sum(1 for r in g.rows if r["status"] == WARN)
    if g.failed:
        print("\n[prompt2render] not shippable — fix the FAILs above.")
        return 1
    if strict and warns:
        print(f"\n[prompt2render] {warns} warning(s), and --strict was asked for.")
        return 1
    print(f"\n[prompt2render] shippable{f' ({warns} warning(s))' if warns else ''}.")
    return 0
