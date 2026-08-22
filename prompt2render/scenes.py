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

from . import align, cfg, llm, stills
from .project import Script

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
  k.compare(ax, a, b, x, y, op="<", winner=None, size=40, label_a=None, label_b=None)
        -> two boxed values side by side with a comparator glyph between them.
           winner: None | "left" | "right" -- outlines that side and stamps a
           checkmark on it; the other side stays neutral, never k.BAD (losing
           a comparison is an outcome, not an error). Returns (left_x, right_x).
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
          col_w=[5.0,3.0], highlight_row=1, highlight_cells=[(0,1)])
        -> about 0.78 per row plus header. highlight_cells is a list of
           (row, col) pairs for highlighting individual cells (e.g. a DP
           table's current cell and the specific cells it depends on),
           independent of highlight_row.
  k.rectangle(ax, x, y, w, h, facecolor=k.ZERO, edgecolor=k.DIM, lw=2.0)
        -> a raw rectangle for building custom shapes dynamically.
  k.curves(ax, y=4.6, w=9.0, h=4.2, show=("linear","log"))
        -> linear vs logarithmic on shared axes. Needs the whole w x h box.
  k.hanoi(ax, [[3,2,1], [], []], x=8.0, y=5.0, w=9.0, h=4.0)
        -> Tower of Hanoi puzzle state. First list is left peg, last is right peg.
  k.tree(ax, (10, (5, 2, 7), (15, None, 20)), x=8.0, y=7.0, dx=3.0, dy=1.5, active_node=5)
        -> Binary tree. Nodes are values or (val, left, right) tuples.
  k.grid(ax, [[1,2],[3,4]], x=8.0, y=5.0, cell_w=1.2, cell_h=1.2, highlight=[(0,1)])
        -> 2D matrix/grid (DP tables, mazes, graphs). highlight is a list of (row, col).
  k.block(ax, "ALU", x, y, w=2.6, h=1.4, active=False, size=24)
        -> a labeled functional-unit box for datapath/block diagrams (cache
           mapping, pipelining, hazards, addressing modes, DMA, fetch-decode-
           execute). active=True outlines it ACCENT -- the unit doing work in
           this step. Returns {"left","right","top","bottom","center"}: edge
           anchor points to hand to k.bus() instead of guessing coordinates.
  k.bus(ax, p1, p2, label=None, active=False)
        -> a right-angle wire between two k.block() anchors (e.g.
           rf["right"], alu["left"]). active=True makes it the signal path
           actually carrying data this step, thicker and ACCENT-colored.

DYNAMIC COMPOSITION FOR COMPLEX TOPICS:
  * For complex, novel topics (like Tower of Hanoi, Neural Networks, or Space-filling curves), DO NOT just look for a single built-in function. 
  * Instead, use standard Python loops, conditionals, and coordinate math to compose complex visuals out of generic primitives (k.block, k.circle, k.arrow, k.label, k.grid).
  * Example: To draw a custom stack of items, use a `for` loop to calculate the `y` coordinate and draw a `k.block` for each item.
  * Example: To draw a graph, calculate `(x, y)` for each node, draw `k.circle` for nodes, and `k.arrow` between them.
  * You are writing a Python script; use the full power of Python to dynamically adapt to the topic's requirements.
  * IMPORTANT: The user prefers JIOHotsatr coloring. When using custom colors, prefer vibrant blues ("#0000ff"), reds ("#ff0000"), and greens ("#00ff00").

LAYOUT RULES (these matter more than cleverness):
  * EVERY k. CALL OWNS AN EXCLUSIVE REGION OF THE FRAME. Two of them may
    never share space. This is checked against the real drawn geometry --
    the boxes, circles, panels and rules, not just the text -- so a diagram
    laid over another is always caught and always sent back. Arrows, strikes,
    braces and buses are the exception: they are meant to touch what they
    connect.
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


def build_prompt(script: Script, sec, sents: list[dict],
                 include_reveal: bool = True) -> str:
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
    {REVEAL_DOC if include_reveal else ""}

    Write a module with exactly this shape and nothing else:

        def states():
            \"\"\"Return a list of (name, cue_index, draw_fn[, opts]).\"\"\"
            def s01(ax):
                ...
            return [("s01", 0, s01), ("s02", 3, s02, {{"steps": 2}}), ...]

    Rules:
      * `cue_index` is the index of the sentence the frame appears ON. Indices
        must start at 0 and STRICTLY INCREASE. You may skip sentences, but you may NEVER go backward.
        The maximum valid cue_index for this section is {len(sents) - 1}.
      * PACING IS A HARD REQUIREMENT. Use the timestamps: no frame may sit for
        longer than 12 seconds. Subtract consecutive cue times to check
        yourself. Roughly {max(7, int(total // 9))} states for this section,
        plus reveal steps.
      * Each draw function draws one complete frame from scratch. Nothing is
        carried between frames.
      * Every frame carries a k.title(...) under 52 characters.
      * Use real, correct numbers, consistent frame to frame. A wrong value is
        worse than a plain frame.
      * INTENTIONAL RULE DEMONSTRATION: If the narration explicitly talks about an illegal move (e.g., placing a large disk on a small disk in Tower of Hanoi), you MUST actually draw the physically illegal state to show what NOT to do. For Hanoi, this means passing a list like `[1, 2]` to `k.hanoi` so disk 2 is visibly on top of disk 1. You MUST also clearly mark it as illegal (e.g., use `k.title(ax, "ILLEGAL MOVE", color=k.BAD)` or `k.badge(ax, x, y, "X", color=k.BAD)`). Do NOT just draw a legal state and label it illegal.
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

    prompt = build_prompt(script, sec, sents)
    # extra_feedback: repair_router's harness-level cycle (prompt2render/harness/plugins/repair_router)
    # seeds diagnostics from *its own* prior repair attempts here — separate from this loop's own
    # internal `feedback`, which is still exactly the same reject-and-retry text as before.
    feedback = extra_feedback

    attempt = 1                  # content attempts
    total_attempt = 1            # across every model, for the final message
    while True:
        try:
            code = llm.complete(
                prompt + feedback, 
                max_tokens=16000, 
                label=f"section {sec.stem} (attempt {attempt}/{retries + 1})"
            )
        except Exception as e:
            sys.exit(f"[prompt2render] section {sec.stem}: LLM call failed — {e}")
            
        code = code or ""
        if not code.strip():
            sys.exit(f"[prompt2render] section {sec.stem}: empty completion — "
                     "lower the state count or raise the token budget")
        
        # Defensive cue repair: if the LLM emitted out-of-order cues, sort them.
        # This prevents stills.py from rejecting the code solely because a cue index went backward.
        raw_code = strip_fences(code)
        import re
        
        def fix_cues(match):
            inner = match.group(1)
            # Find all tuples: ("s01", 0, s01) or ("s02", 3, s02, {"steps": 2})
            # We look for the integer right after the first string.
            tuples = re.findall(r'(\(\s*["\'][^"\']+["\']\s*,\s*)(\d+)(\s*,[^)]+\))', inner)
            if not tuples:
                return match.group(0)
                
            fixed_inner = inner
            prev_cue = -1
            max_allowed = len(sents) - 1
            
            for prefix, cue_str, suffix in tuples:
                cue = int(cue_str)
                
                # 1. Enforce strictly increasing
                if cue <= prev_cue:
                    cue = prev_cue + 1
                    
                # 2. Enforce max bounds (clamp to max_allowed)
                if cue > max_allowed:
                    cue = max_allowed
                    
                # If we clamped and it's no longer strictly increasing because
                # multiple states are bunched at the very end, we have to accept
                # that stills.py might reject it, or we can just let it be equal 
                # at the max bound and let stills.py fail it with a clear message.
                # Actually, stills.py requires strictly increasing. So if we hit the ceiling:
                if cue <= prev_cue:
                    cue = prev_cue + 1 # We must increase, even if it breaks the ceiling
                    
                if cue != int(cue_str):
                    # Replace just this specific occurrence in the string
                    old_tuple = f"{prefix}{cue_str}{suffix}"
                    new_tuple = f"{prefix}{cue}{suffix}"
                    fixed_inner = fixed_inner.replace(old_tuple, new_tuple, 1)
                    
                prev_cue = cue
                    
            return f"return [{fixed_inner}]"

        # Apply the fix if we find the return list
        raw_code = re.sub(r"return\s+\[(.*?)\]", fix_cues, raw_code, flags=re.DOTALL)
            
        dst.write_text(raw_code, encoding="utf-8")

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
            feedback_msg = "\n\nYour previous answer was rejected. Fix it and return the whole corrected module.\n\nPROBLEM:\n" + err
            if "cue indices must increase" in err:
                feedback_msg += "\n\nCRITICAL FIX: You emitted a cue index that was smaller than or equal to the previous state's cue index. Look at your `return [...]` list at the bottom. The second element of each tuple (the cue index) MUST strictly increase: e.g., 0, 2, 5, 8. Fix the numbers so they go up."
            elif "but the section only has sentences" in err:
                feedback_msg += f"\n\nCRITICAL FIX: You emitted a cue index that is too large. This section only has {len(sents)} sentences (indices 0 to {len(sents)-1}). You MUST NOT use a cue index larger than {len(sents)-1}."
            elif "overlaps" in err or "share space" in err or "different horizontal bands" in err:
                feedback_msg += "\n\nCRITICAL FIX: You have elements overlapping or sharing the same space on the screen. The canvas is 16 units wide and 9 units tall. You MUST change the `y` coordinates to put elements in different horizontal bands, OR split the content into two completely separate states."
                
            feedback = extra_feedback + feedback_msg
            # The rejected code already shows whether this section wants
            # progressive reveal (the {"steps": N} opts dict) — REVEAL_DOC's
            # ~280 tokens of explanation are dead weight on every retry that
            # doesn't use it, resent unchanged on top of the same API_DOC
            # every attempt already pays for.
            if "steps" not in code:
                prompt = build_prompt(script, sec, sents, include_reveal=False)

            if attempt < retries + 1:
                attempt += 1
                total_attempt += 1
                continue
            
            # Since llm.complete() handles quota rotation transparently, if we run out of 
            # content retries here, we just fail the section. We don't try to outsmart 
            # the model rotation for content errors anymore.
            sys.exit(f"[prompt2render] section {sec.stem}: still failing after "
                     f"{total_attempt} total attempts — {err}")

        # Usage reporting is omitted because we abstracted it behind llm.complete
        # which returns the raw string, not the response object.
        cfg.say(f"section {sec.stem}: accepted — {len(man)} stills")
        return dst


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
        dst = stills.scene_path(proj, sec.stem)
        # dst.exists() alone isn't "done": generate() writes the .py file
        # before the audit runs, so a section that exhausted its retries
        # (raising SystemExit, which used to abort the whole run) leaves a
        # rejected module on disk. is_current() requires the manifest and
        # audit.json render() only writes once the audit actually passed.
        if stills.is_current(dst, stills.stills_dir(proj, sec.stem)):
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
