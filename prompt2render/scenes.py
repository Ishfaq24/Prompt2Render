"""Ask the model to storyboard one section against scenekit.

This is the Coder role from Code2Video, reduced to a small fixed drawing API:
few ways to be wrong, and every mistake surfaces as something we can feed
straight back.

What is new here is the Critic. Upstream Code2Video has one, but it works by
uploading rendered video for a vision model to review — which the AI Studio
endpoint will not accept, which is why layout refinement was off, which is why
the paper's own raters scored element layout 60/100. The insight is that a
vision model was never needed: matplotlib knows exactly where every glyph
landed. `scenekit.audit` turns that into prose the model can act on, at zero
extra API cost, and `stills.render(--check)` raises it as the failure the
retry loop already knew how to handle.
"""
from __future__ import annotations

import json
import os
import re
import sys
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import align, cfg, stills
from .project import Script

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"

#: Sections are storyboarded concurrently (see default_jobs), but the *render*
#: that judges each answer is matplotlib, and matplotlib shares one FreeType
#: object per font across the process — two threads measuring glyphs at once
#: is a data race, and the symptom would be an audit failure that is not
#: reproducible. Rendering is a couple of seconds against a call of tens, so
#: serialising just this part costs almost nothing and removes the hazard.
_RENDER_LOCK = threading.Lock()

API_DOC = '''
You may call ONLY these functions from the module `k` (already imported).
The canvas is 16 units wide and 9 units tall. x=0 is the left edge, y=0 the
bottom. Colours available: k.FG k.DIM k.ONE k.GOOD k.BAD k.WARN k.ACCENT.

  k.title(ax, text, y=8.1, size=46, color=k.FG)
  k.caption(ax, text, y=0.85, size=30, color=k.DIM)
  k.label(ax, x, y, text, size=28, color=k.FG, ha="center", va="center", mono=False, weight="normal")
  k.bits(ax, "10011011", x, y, size=40, highlight=[0,3], hcolor=k.WARN, labels=None, dim=False)
        -> draws boxed bits, MSB first; returns list of bit centre x values
  k.bit_brace(ax, x_from, x_to, y, text, color=k.DIM, size=22, below=True)
  k.arrow(ax, x1, y1, x2, y2, color=k.ACCENT, lw=3.0)
  k.strike(ax, x1, x2, y, color=k.BAD)
  k.badge(ax, x, y, "OK", k.GOOD, 60)
  k.addition(ax, top, bottom, result, x, y, carry=None, ok=None, size=40)
        -> a column sum; top/bottom/result are bit strings; occupies y-2.2 .. y+2.9
  k.number_line(ax, lo, hi, y, x0=1.4, x1=14.6, ticks=[...], marks={val:(text,colour)})
  k.dial(ax, n_bits, cx, cy, r, pointer=None, highlight_signed=False, size=20, label_mode="signed")
        -> the wrap-around odometer; use n_bits=4, r about 2.6
  k.register(ax, "10011011", x, y, drop_carry=False, note=None)
  k.array(ax, [2,5,8,12,16,23,38], y=5.0, lo=None, hi=None, mid=None,
          found=None, dead=[0,1], target=None, bracket=None, idx=True)
        -> a sorted array with lo/hi arrows below and mid above. `dead` greys
           out eliminated indices. `bracket` labels the live lo..hi span.
           Occupies y-2.2 .. y+2.6. Returns index -> x.
  k.predicate_strip(ax, [0,0,0,1,1,1], y=5.0, labels=("no","yes"), note=None)
        -> the false..false,true..true strip with the boundary marked.
           Occupies y-2.0 .. y+2.0.
  k.code(ax, ["line one", "line two"], y=5.0, highlight=[0], title_text=None)
        -> a monospace block; it shrinks its own font to fit. Keep lines
           under 52 characters. Height is about 0.65 per line.
  k.table(ax, [("1,000","10")], headers=("size","steps"), y=5.0,
          col_w=[5.0,3.0], highlight_row=1)   -> about 0.78 per row plus header
  k.curves(ax, y=4.6, w=9.0, h=4.2, show=("linear","log"))
        -> linear vs logarithmic on shared axes. Needs the whole w x h box.

LAYOUT RULES (these matter more than cleverness):
  * EVERY k. CALL OWNS AN EXCLUSIVE REGION OF THE FRAME. Two of them may
    never share space. This is checked against the real drawn geometry --
    the boxes, circles, panels and rules, not just the text -- so a diagram
    laid over another is always caught and always sent back. Arrows, strikes
    and braces are the exception: they are meant to touch what they point at.
  * The title occupies y=7.6..8.6. Never draw anything else above y=7.4.
  * k.addition centred at y needs the whole band y-2.2 .. y+2.9 to itself.
  * k.dial with r=2.6 needs a 7.4x7.4 box around (cx, cy). With
    label_mode="signed" it needs a further 1.0 in every direction, which at
    cy=4.3 already reaches the title -- drop cy, or drop the outer labels.
  * k.code, k.table and k.curves are opaque panels: nothing else may be
    drawn inside their footprint, and k.curves fills its whole w x h box.
  * Never place two elements in the same horizontal band. If a state feels
    crowded, split it into two states instead. Two states always beat one
    crowded one.
  * A caption at y=0.85 is always safe.
  * Nothing may cross the frame edge. Keep every element within x=0.4..15.6
    and y=0.4..8.6. This too is measured on the drawn geometry, so an element
    that is *nearly* inside still fails.

COLOR RULES (measured, not eyeballed — k.GOOD vs k.BAD is a near-collision for
red-green colorblind viewers, about 8% of men, so color alone never carries
the point):
  * k.GOOD/k.BAD/k.WARN mean state (correct/wrong/caution). Never repurpose
    them as arbitrary identity colors for two things that are just different,
    not right-vs-wrong (use k.ONE and k.ACCENT for that instead, e.g. lo vs
    hi pointers).
  * Every time k.GOOD or k.BAD marks something, pair it with a second signal:
    a symbol (checkmark/cross), a text label, or position (e.g. above vs
    below a line) — never color as the only distinguishing cue between a good
    thing and a bad thing sitting in the same frame.
  * k.badge already does this (✓/✗ plus color) — prefer it over hand-rolled
    green/red text for a verdict.
'''

REVEAL_DOC = '''
PROGRESSIVE REVEAL — use this, it is what makes the video look constructed
rather than like a slideshow.

A state may declare `steps`, and its draw function then takes (ax, step) with
step running 0..steps-1. Draw the same frame each time, but include an element
only once the step has reached it:

    def s04(ax, step):
        k.title(ax, "Look at the middle element")
        k.array(ax, arr, y=4.5, lo=0, hi=15,
                mid=7 if step >= 1 else None,
                bracket="target is > 45" if step >= 2 else None)
        if step >= 2:
            k.caption(ax, "so the whole left half is dead")

    return [("s01", 0, s01), ("s04", 12, s04, {"steps": 3, "anchor": "the middle element"})]

  * `anchor` is optional: a short exact phrase from the narration. The frame
    will be cut to land on that word rather than on the sentence start. Copy
    the phrase verbatim from the sentences listed above.
  * Prefer 2-4 steps on any state that would otherwise sit still for more than
    8 seconds. This is cheaper and better than inventing a new diagram.
  * Step 0 must already be a sensible frame on its own.
'''


def _keys() -> list[str]:
    """GEMINI_API_KEY, plus any GEMINI_API_KEY_BACKUP* for failover.

    Gemini's free tier caps requests *per day per model*, and the 429 it
    returns names a retry-after of tens of seconds — misleading for a quota
    that will not clear until tomorrow. A second key on a separate quota is
    the only thing that actually unblocks a run in progress.
    """
    keys = [os.environ.get("GEMINI_API_KEY", "")]
    for name, val in sorted(os.environ.items()):
        if name.startswith("GEMINI_API_KEY_BACKUP") and val:
            keys.append(val)
    keys = [k for k in keys if k]
    if not keys:
        sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
    return keys


def _client(key: str):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[prompt2render] openai not installed — pip install -r requirements.txt")
    # The SDK rather than curl: the key stops appearing in process listings,
    # and retries and timeouts come for free.
    return OpenAI(api_key=key, base_url=ENDPOINT, timeout=300.0, max_retries=2)


def build_prompt(script: Script, sec, sents: list[dict]) -> str:
    # Give the model the clock, not just the words. Without timings it cannot
    # tell that two adjacent cues are 30 seconds apart, and it leaves frames
    # sitting on screen long past the point they stop being interesting.
    numbered = "\n".join(
        f"  [{i}] t={s['start']:6.1f}s  {s['text']}" for i, s in enumerate(sents))
    total = sents[-1]["end"] if sents else 0.0
    return textwrap.dedent(f"""
    You are the Coder agent for an educational video pipeline. Write Python that
    renders the still frames for ONE section of a video about
    "{script.title}" for an audience of {script.meta.get('audience','undergraduates')}.

    SECTION {sec.index}: {sec.title}

    ANIMATION BRIEF (what the visuals must show):
    {sec.anim}

    The narration is already recorded and measured. It runs {total:.0f} seconds.
    These are its sentences, with the time each is spoken and the index you must
    use to say when a frame appears:

{numbered}

    {API_DOC}
    {REVEAL_DOC}

    Write a module with exactly this shape and nothing else:

        def states():
            \"\"\"Return a list of (name, cue_index, draw_fn[, opts]).\"\"\"
            def s01(ax):
                ...
            return [("s01", 0, s01), ("s02", 3, s02, {{"steps": 2}}), ...]

    Rules:
      * `cue_index` is the index of the sentence the frame appears ON. Indices
        must start at 0 and strictly increase.
      * PACING IS A HARD REQUIREMENT. Use the timestamps: no frame may sit for
        longer than 12 seconds. Subtract consecutive cue times to check
        yourself. Roughly {max(7, int(total // 9))} states for this section,
        plus reveal steps.
      * Each draw function draws one complete frame from scratch. Nothing is
        carried between frames.
      * Every frame carries a k.title(...) under 52 characters.
      * Use real, correct numbers, consistent frame to frame. A wrong value is
        worse than a plain frame.
      * LAYOUT IS THE THING THAT USUALLY FAILS. Two elements in the same
        horizontal band will overlap and ruin the frame.
      * k.curves fills its whole w x h box. Never draw a k.table, k.array or
        k.code inside that box.
      * Pass `bracket` a plain string, never a tuple.
      * No imports, no file IO, no prints. `k` is already available.

    Output ONLY the Python code, no prose, no markdown fences.
    """).strip()


def strip_fences(code: str) -> str:
    code = code.strip()
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", code, re.S)
    return m.group(1) if m else code


def generate(proj: Path, script: Script, index: int, retries: int = 3,
            extra_feedback: str = "") -> Path:
    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")

    data = align.load(proj, sec.stem)
    sents = data["sentences"]
    if not sents:
        sys.exit(f"[prompt2render] section {sec.stem} has no alignment — run `prompt2render align`")

    outdir = proj / "build" / "scenes"
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / f"scene_{sec.stem}.py"

    keys = _keys()
    key_i = 0
    client = _client(keys[key_i])
    model = os.environ.get("P2R_SCENE_MODEL", "gemini-3.6-flash")
    prompt = build_prompt(script, sec, sents)
    # extra_feedback: repair_router's harness-level cycle (prompt2render/harness/plugins/repair_router)
    # seeds diagnostics from *its own* prior repair attempts here — separate from this loop's own
    # internal `feedback`, which is still exactly the same reject-and-retry text as before.
    feedback = extra_feedback

    attempt = 1
    while attempt <= retries + 1:
        cfg.say(f"section {sec.stem}: asking {model} (attempt {attempt}"
                + (f", key {key_i + 1}/{len(keys)}" if len(keys) > 1 else "") + ")")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt + feedback}],
                max_tokens=16000,
                # Gemini 3.x spends completion budget thinking before it emits
                # code. The drawing API is small and fully specified, so there
                # is little to reason about; capping this keeps a call inside
                # a minute and stops thinking eating the whole token budget.
                extra_body={"reasoning_effort": os.environ.get("P2R_REASONING", "low")},
            )
        except Exception as e:                    # noqa: BLE001
            # A 429 is an account-level quota, not a content problem — it does
            # not deserve one of the content-retry attempts above, and
            # retrying the same key just burns the SDK's own retry budget on
            # a wall that will not move. Rotate to the next key if there is
            # one; only count this against `attempt` once every key is spent.
            if type(e).__name__ != "RateLimitError":
                raise
            if key_i + 1 < len(keys):
                key_i += 1
                cfg.warn(f"section {sec.stem}: key {key_i}/{len(keys)} "
                         f"rate-limited, switching to the next key")
                client = _client(keys[key_i])
                continue
            sys.exit(f"[prompt2render] section {sec.stem}: all {len(keys)} Gemini "
                     f"key(s) are rate-limited — {e}")
        choice = resp.choices[0] if resp.choices else None
        code = (choice.message.content if choice else "") or ""
        if not code.strip():
            fin = choice.finish_reason if choice else "?"
            sys.exit(f"[prompt2render] empty completion (finish_reason={fin}) — "
                     "lower the state count or raise the token budget")
        dst.write_text(strip_fences(code), encoding="utf-8")

        try:
            # Render for real, into a staging directory that is only swapped
            # in once the audit passes. A rejected attempt is discarded
            # exactly as before; an accepted one has already produced this
            # section's PNGs, so `prompt2render stills` finds them current and skips.
            # The old `check=True` path drew every frame, threw the pixels
            # away, and left the stills stage to draw all of them again.
            with _RENDER_LOCK:
                man = stills.render_into(dst, outdir / sec.stem,
                                         max_cue=len(sents) - 1)
        except SystemExit as e:
            err = str(e)[-1500:]
            first = err.splitlines()[0][:110] if err.splitlines() else err[:110]
            cfg.say(f"section {sec.stem}: rejected — {first}")
            # A stack trace tells it the code crashed. An audit failure tells
            # it *where two things collided, in pixels*. Both go back verbatim.
            feedback = extra_feedback + (
                        "\n\nYour previous answer was rejected. Fix it and "
                        "return the whole corrected module.\n\nPROBLEM:\n" + err)
            attempt += 1
            continue

        used = getattr(resp, "usage", None)
        cfg.say(f"section {sec.stem}: accepted — {len(man)} stills"
                + (f", {used.total_tokens} tokens" if used else ""))
        return dst

    sys.exit(f"[prompt2render] section {sec.stem} still failing after {retries + 1} tries")


def default_jobs(n: int) -> int:
    """How many sections to storyboard at once.

    Almost all of this stage is spent waiting on Gemini, so concurrency here
    is close to free wall-clock: five sections that each take 40 s serially
    finish in about 40 s together. Threads rather than processes — the SDK
    releases the GIL on the socket, and each call needs its own client anyway.

    Capped low on purpose. The free tier meters requests per minute as well as
    per day, and firing a whole script at it at once is the fastest way to
    turn a working run into a wall of 429s.
    """
    want = cfg.env_int("P2R_SCENE_JOBS", 0)
    if want > 0:
        return max(1, min(want, n or 1))
    return max(1, min(3, n or 1))


def generate_all(proj: Path, script: Script, index: int | None = None,
                 retries: int = 3, jobs: int | None = None) -> None:
    todo = []
    for sec in script.sections:
        if index is not None and sec.index != index:
            continue
        dst = proj / "build" / "scenes" / f"scene_{sec.stem}.py"
        if dst.exists():
            cfg.say(f"section {sec.stem}: scene already written, skipping "
                    "(delete it to regenerate)")
            continue
        todo.append(sec)

    if not todo:
        return
    n = jobs or default_jobs(len(todo))
    if n <= 1 or len(todo) == 1:
        for sec in todo:
            generate(proj, script, sec.index, retries)
        return

    cfg.say(f"storyboarding {len(todo)} sections, {n} at a time")
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(generate, proj, script, sec.index, retries)
                   for sec in todo]
        try:
            for fut in as_completed(futures):
                fut.result()
        except BaseException:
            # One section that cannot be storyboarded stops the stage, same
            # as the serial loop did -- the rest would only be wasted spend.
            for f in futures:
                f.cancel()
            raise
