"""Work out when each still is on screen, and for exactly how many frames.

The old planner (tools/build_video.py cmd_plan) had a latent bug worth naming,
because it explains the shape of this one: it bumped starts forward to keep
them increasing, then clamped them backward to fit the section, and never
reconciled the two. On a dense section that yields a start past the one after
it, `frames` goes to zero or negative, and `-frames:v 0` writes a zero-byte
clip that breaks the concat much later, somewhere else entirely.

So the fitting pass here is explicit: push forward, pull back, and if the two
still disagree, *drop a reveal sub-step* and try again. Reveals are the
compressible thing; states are not. Nothing is ever silently merged.

Two smaller decisions that matter:

* Stills cue on the word, not the sentence, when the state names an anchor.
* Every start is pulled `lead_ms` earlier. A cut that lands just before the
  word reads as tight; one that lands after it reads as sloppy. 120 ms is
  free and it is the difference between "edited" and "generated".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import align, cfg, stills, textseg, voice
from .project import Script

MIN_STATE_FRAMES = 45          # 1.5 s — below this a cut reads as a twitch
MIN_REVEAL_FRAMES = 33         # 1.1 s
LONG_STILL_S = 12.0            # above this the picture has died on screen
SHORT_STILL_S = 1.5


def _word_starts(sents: list[dict]) -> list[tuple[float, str]]:
    out = []
    for s in sents:
        for w in s.get("words") or []:
            out.append((w["s"], w["w"]))
    return out


def _find_anchor(phrase: str, sents: list[dict], after: float) -> float | None:
    """Time of the first word of `phrase`, searching at or after `after`."""
    want = textseg.norm_tokens(phrase)
    if not want:
        return None
    words = [(w["s"], textseg.normalise_token(w["w"]))
             for s in sents for w in (s.get("words") or [])]
    flat = []
    for t, norm in words:
        for piece in (norm.split() or [""]):
            if piece:
                flat.append((t, piece))
    n = len(want)
    for i in range(len(flat) - n + 1):
        if flat[i][0] < after - 0.001:
            continue
        if [p for _, p in flat[i:i + n]] == want:
            return flat[i][0]
    return None


def _state_starts(manifest: list[dict], sents: list[dict],
                  dur: float) -> list[float]:
    """One start time per *state* (ignoring reveal sub-steps)."""
    heads = [m for m in manifest if m["step"] == 0]
    starts: list[float] = []
    for m in heads:
        cue = min(m["cue"], len(sents) - 1) if sents else 0
        base = sents[cue]["start"] if sents else 0.0
        if m.get("anchor"):
            hit = _find_anchor(m["anchor"], sents, base)
            if hit is not None:
                base = hit
            else:
                cfg.warn(f"anchor {m['anchor']!r} not found in the narration — "
                         f"falling back to the sentence start")
        starts.append(min(max(base, 0.0), dur))
    return starts


def _expand(manifest: list[dict], state_starts: list[float], sents: list[dict],
            dur: float, drop: set[int]) -> list[dict]:
    """Flatten states and their reveal sub-steps into one timed still list."""
    heads = [m for m in manifest if m["step"] == 0]
    by_state: dict[int, list[dict]] = {}
    for m in manifest:
        by_state.setdefault(m["cue"], []).append(m)

    words = _word_starts(sents)
    out: list[dict] = []
    for si, head in enumerate(heads):
        group = sorted(by_state[head["cue"]], key=lambda m: m["step"])
        group = [g for g in group if g["step"] == 0 or g["i"] not in drop]
        begin = state_starts[si]
        end = state_starts[si + 1] if si + 1 < len(state_starts) else dur
        span = max(end - begin, 0.5)

        for gi, m in enumerate(group):
            if gi == 0:
                t = begin
            else:
                ideal = begin + span * gi / len(group)
                # Snap the reveal onto a real word start; an element that
                # appears mid-word looks like a glitch.
                cands = [w for w, _ in words if w > out[-1]["t"] + 0.4]
                t = min(cands, key=lambda w: abs(w - ideal)) if cands else ideal
            out.append({**m, "t": min(max(t, 0.0), dur)})
    return out


def _fit(items: list[dict], total_frames: int) -> list[int] | None:
    """Frame counts, or None if these stills cannot be made to fit."""
    n = len(items)
    minf = [MIN_STATE_FRAMES if it["kind"] == "state" else MIN_REVEAL_FRAMES
            for it in items]
    if sum(minf) > total_frames:
        return None

    s = [round(it["t"] * cfg.FPS) for it in items]
    s[0] = 0
    for i in range(1, n):                       # push forward
        s[i] = max(s[i], s[i - 1] + minf[i - 1])
    for i in range(n - 1, 0, -1):               # pull back
        s[i] = min(s[i], total_frames - sum(minf[i:]))
    if any(s[i] <= s[i - 1] for i in range(1, n)) or s[0] != 0:
        return None

    frames = [s[i + 1] - s[i] for i in range(n - 1)]
    frames.append(total_frames - s[-1])
    if any(f < 1 for f in frames) or sum(frames) != total_frames:
        return None
    return frames


def _plan_section(proj: Path, sec, dur: float, motion: str,
                  lead: float) -> tuple[list[dict], list[str]]:
    man = stills.manifest(proj, sec.stem)
    data = align.load(proj, sec.stem)
    sents = data["sentences"]
    total_frames = round(dur * cfg.FPS)

    if motion != "dissolve+reveal":
        man = [m for m in man if m["step"] == 0]

    state_starts = [max(0.0, t - lead) for t in _state_starts(man, sents, dur)]
    for i in range(1, len(state_starts)):       # keep them ordered before fitting
        state_starts[i] = max(state_starts[i], state_starts[i - 1])

    drop: set[int] = set()
    while True:
        items = _expand(man, state_starts, sents, dur, drop)
        frames = _fit(items, total_frames)
        if frames is not None:
            break
        reveals = [it["i"] for it in items if it["kind"] == "reveal"]
        if reveals:
            # Reveals are the compressible thing. Drop the last one and retry.
            drop.add(reveals[-1])
            continue
        sys.exit(
            f"[prompt2render] section {sec.stem}: {len(items)} states need at least "
            f"{sum(MIN_STATE_FRAMES for _ in items)/cfg.FPS:.1f}s but the "
            f"narration is only {dur:.1f}s — the scene has too many states "
            f"for what is said. Regenerate it with fewer.")

    if drop:
        cfg.say(f"  dropped {len(drop)} reveal step(s) to fit the narration")

    out, notes = [], []
    for idx, (it, f) in enumerate(zip(items, frames)):
        secs = f / cfg.FPS
        if secs > LONG_STILL_S:
            notes.append(f"state {it['name']} holds {secs:.1f}s — add reveal steps")
        if secs < SHORT_STILL_S:
            notes.append(f"state {it['name']} flashes by in {secs:.1f}s")
        out.append({
            "section": sec.stem, "i": it["i"], "name": it["name"],
            "kind": it["kind"], "step": it["step"],
            # Relative to the project dir: the old plan.json still holds
            # absolute paths from a different host, which made it useless
            # anywhere but where it was written.
            "png": f"build/scenes/{sec.stem}/{it['png']}",
            "prev_png": (f"build/scenes/{sec.stem}/{items[idx-1]['png']}"
                         if idx > 0 else ""),
            "frames": f, "seconds": round(secs, 3),
            "cue": {"sentence": it["cue"], "t": round(it["t"], 3)},
            "clip": f"build/clips/{sec.stem}_{it['i']:03d}.mp4",
        })
    return out, notes


def build(proj: Path, script: Script, motion: str | None = None,
          lead_ms: int | None = None) -> Path:
    import os
    motion = motion or os.environ.get("P2R_MOTION", "dissolve+reveal")
    lead = (lead_ms if lead_ms is not None
            else cfg.env_int("P2R_VISUAL_LEAD_MS", cfg.VISUAL_LEAD_MS)) / 1000

    amap = voice.audio_map(proj)
    plan, notes, shots = [], [], []
    for sec in script.sections:
        dur = amap["sections"][sec.stem]["dur"]
        rows, n = _plan_section(proj, sec, dur, motion, lead)
        # The first still of a section dissolves from the last still of the
        # previous one, so a chapter change is a transition rather than a cut.
        if plan and rows:
            rows[0]["prev_png"] = plan[-1]["png"]
            rows[0]["kind"] = "section"
        plan.extend(rows)
        notes.extend(n)
        shots.extend(r["seconds"] for r in rows)
        cfg.say(f"section {sec.stem}: {len(rows)} stills over {dur:.1f}s "
                f"({sum(r['frames'] for r in rows)} frames)")

    shots.sort()
    mean = sum(shots) / len(shots) if shots else 0
    p95 = shots[int(len(shots) * 0.95)] if shots else 0
    dst = proj / "build" / "plan.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({
        "fps": cfg.FPS, "motion": motion, "lead_ms": round(lead * 1000),
        "pacing": {"mean_shot_s": round(mean, 2), "p95_shot_s": round(p95, 2),
                   "notes": notes},
        "clips": plan,
    }, indent=2), encoding="utf-8")

    total = sum(r["frames"] for r in plan)
    cfg.say(f"plan: {len(plan)} clips, {total} frames, {total/cfg.FPS/60:.2f} min"
            f"  (mean shot {mean:.1f}s)")
    for n in notes[:6]:
        cfg.warn(n)
    return dst


def load(proj: Path) -> dict:
    p = proj / "build" / "plan.json"
    if not p.exists():
        sys.exit("[prompt2render] no build/plan.json — run `prompt2render plan`")
    return json.loads(p.read_text(encoding="utf-8"))
