"""Ask gemini-3.6-flash to storyboard one section against scenekit.

This is the Coder role from Code2Video, reduced to the part that survives
without manimpango: the model writes Python that calls a fixed, small drawing
API, and we execute it. A small API means the model has few ways to be wrong,
and every mistake surfaces as an exception we can feed straight back to it.

    python tools/gen_scenes.py <slug> <section-index> [--retries 3]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fdx import cfg  # noqa: E402
from fdx.project import parse_script  # noqa: E402

MODEL = os.environ.get("FDX_SCENE_MODEL", "gemini-3.6-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

API_DOC = '''
You may call ONLY these functions from the module `k` (already imported).
The canvas is 16 units wide and 9 units tall. x=0 is the left edge, y=0 the
bottom. Colours available: k.FG k.DIM k.ONE k.GOOD k.BAD k.WARN k.ACCENT.

  fig, ax = k.canvas()
  k.title(ax, text, y=8.1, size=46, color=k.FG)
  k.caption(ax, text, y=0.85, size=30, color=k.DIM)
  k.label(ax, x, y, text, size=28, color=k.FG, ha="center", va="center", mono=False, weight="normal")
  k.bits(ax, "10011011", x, y, size=40, highlight=[0,3], hcolor=k.WARN, labels=None, dim=False)
        -> draws boxed bits, MSB first; returns list of bit centre x values
  k.bit_brace(ax, x_from, x_to, y, text, color=k.DIM, size=22, below=True)
  k.arrow(ax, x1, y1, x2, y2, color=k.ACCENT, lw=3.0)
  k.strike(ax, x1, x2, y, color=k.BAD)
  k.badge(ax, x, y, "✓", k.GOOD, 60)
  k.addition(ax, top, bottom, result, x, y, carry=None, ok=None, size=40)
        -> a column sum; top/bottom/result are bit strings; occupies y-2.2 .. y+2.9
  k.number_line(ax, lo, hi, y, x0=1.4, x1=14.6, ticks=[...], marks={val:(text,colour)})
  k.dial(ax, n_bits, cx, cy, r, pointer=None, highlight_signed=False, size=20, label_mode="signed")
        -> the wrap-around odometer; use n_bits=4, r about 2.6
  k.register(ax, "10011011", x, y, drop_carry=False, note=None)
        -> bits inside a register outline; drop_carry shows the carry falling off

  k.array(ax, [2,5,8,12,16,23,38], y=5.0, lo=None, hi=None, mid=None,
          found=None, dead=[0,1], target=None, bracket=None, idx=True)
        -> a sorted array with lo/hi arrows below and mid above. `dead` greys
           out eliminated indices. `bracket` labels the live lo..hi span.
           Occupies y-2.2 .. y+2.6. Returns index -> x.
  k.predicate_strip(ax, [0,0,0,1,1,1], y=5.0, labels=("no","yes"), note=None)
        -> the false..false,true..true strip with the boundary marked.
           Occupies y-2.0 .. y+2.0.
  k.code(ax, ["line one", "line two"], y=5.0, highlight=[0], title_text=None)
        -> a monospace block; it shrinks its own font to fit the frame.
           Height is about 0.65 per line. Keep lines under 52 characters.
  k.table(ax, [("1,000","10"),("1,000,000","20")], headers=("size","steps"),
          y=5.0, col_w=[5.0,3.0], highlight_row=1)
        -> Height is about 0.78 per row plus a header row.
  k.curves(ax, y=4.6, w=9.0, h=4.2, show=("linear","log"))
        -> linear vs logarithmic on shared axes. Needs the whole w x h box.

  k.save(fig, path)

LAYOUT RULES (these matter more than cleverness):
  * The title occupies y=7.6..8.6. Never draw anything else above y=7.4.
  * k.addition centred at y needs the whole band y-2.2 .. y+2.9 to itself.
  * k.dial with r=2.6 needs a 7.4x7.4 box around (cx, cy).
  * Never place two elements in the same horizontal band. If a state feels
    crowded, split it into two states instead.
  * A caption at y=0.85 is always safe.
'''


def build_prompt(script, sec, cues):
    # Give the model the clock, not just the words. Without timings it cannot
    # tell that two adjacent cues are 30 seconds apart, and it leaves frames
    # sitting on screen long past the point they stop being interesting.
    numbered = "\n".join(
        f"  [{i}] t={c['start']:6.1f}s  {c['text']}" for i, c in enumerate(cues))
    total = cues[-1]["end"] if cues else 0.0
    return textwrap.dedent(f"""
    You are the Coder agent for an educational video pipeline. Write Python that
    renders the still frames for ONE section of a video about
    "{script.title}" for an audience of {script.meta.get('audience','undergraduates')}.

    SECTION {sec.index}: {sec.title}

    ANIMATION BRIEF (what the visuals must show):
    {sec.anim}

    The narration has already been recorded. It runs for {total:.0f} seconds.
    These are its sentences, in order, with the time each one is spoken and the
    index you must use to say when a frame appears:

{numbered}

    {API_DOC}

    Write a module with exactly this shape and nothing else:

        def states():
            \"\"\"Return a list of (name, cue_index, draw_fn).\"\"\"
            def s01(ax):
                ...
            ...
            return [("s01", 0, s01), ("s02", 3, s02), ...]

    Rules:
      * `cue_index` is the index of the sentence the frame must appear ON. The
        frame stays on screen until the next state's cue. Indices must start at
        0 and strictly increase.
      * PACING IS A HARD REQUIREMENT. Use the timestamps: no frame may stay on
        screen longer than 12 seconds, and none should change faster than
        every 4 seconds. Subtract consecutive cue times to check yourself. If a
        gap would exceed 12 seconds, add an intermediate state that reveals the
        next piece of the picture. For this section that means roughly
        {max(7, int(total // 9))} states.
      * Each draw_fn takes `ax` only and draws one complete frame from scratch.
        Do not rely on state carried between frames.
      * States build: reveal one new element at a time so the viewer sees the
        argument being constructed, not a finished diagram dropped in.
      * Every frame carries a k.title(...) under 52 characters.
      * Use real, correct numbers and keep them consistent frame to frame. A
        wrong value is worse than a plain frame.
      * LAYOUT IS THE THING THAT USUALLY FAILS. Two elements in the same
        horizontal band will overlap and ruin the frame. Give each element its
        own band, and if a state feels crowded, split it into two states.
      * k.curves fills its whole w x h box. NEVER draw a k.table, k.array or
        k.code inside that box. If a frame wants both a chart and a table,
        either put them in separate states, or shrink the chart (w=6.5) and
        place it left of centre with the table to the right.
      * Pass `bracket` a plain string, never a tuple.
      * No imports, no file IO, no prints. `k` is already available.

    Output ONLY the Python code, no prose, no markdown fences.
    """).strip()


def call_gemini(prompt, max_tokens=16000):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("[gen] GEMINI_API_KEY not set (it lives in .env)")
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        # Gemini 3.x spends completion budget on thinking before it emits code.
        # The drawing API is small and fully specified, so there is little to
        # reason about -- capping this keeps a call inside a minute and stops
        # thinking from eating the whole token budget.
        "reasoning_effort": os.environ.get("FDX_REASONING", "low"),
    }
    proc = subprocess.run(
        ["curl", "-sS", ENDPOINT, "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {key}", "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        sys.exit(f"[gen] curl failed: {proc.stderr[-500:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.exit(f"[gen] non-JSON reply: {proc.stdout[:400]}")
    if isinstance(data, list):          # some errors come back as a list
        data = data[0] if data else {}
    if "error" in data:
        sys.exit(f"[gen] api error: {str(data['error'])[:400]}")
    choices = data.get("choices") or []
    if not choices:
        sys.exit(f"[gen] no choices in reply: {json.dumps(data)[:400]}")
    msg = choices[0].get("message", {}).get("content")
    if not msg:
        # Hitting the token ceiling mid-thought returns an empty message.
        fin = choices[0].get("finish_reason")
        sys.exit(f"[gen] empty completion (finish_reason={fin}); "
                 f"raise --max-tokens or lower the state count")
    return msg, data.get("usage", {})


def strip_fences(code: str) -> str:
    code = code.strip()
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", code, re.S)
    return m.group(1) if m else code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("index", type=int)
    ap.add_argument("--states", type=int, default=8)
    ap.add_argument("--retries", type=int, default=2)
    a = ap.parse_args()

    cfg.load_env()
    proj = cfg.project_dir(a.slug)
    script = parse_script(proj / "script.md")
    sec = next(s for s in script.sections if s.index == a.index)

    align = proj / "build" / "align" / f"{sec.stem}.json"
    if not align.exists():
        sys.exit(f"[gen] no measured timings at {align} — "
                 f"run tools/narrate_aligned.py first")
    cues = json.loads(align.read_text(encoding="utf-8"))

    outdir = proj / "build" / "scenes"
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / f"scene_{sec.stem}.py"

    prompt = build_prompt(script, sec, cues)
    feedback = ""
    for attempt in range(1, a.retries + 2):
        cfg.say(f"section {sec.stem}: asking {MODEL} (attempt {attempt})")
        code, usage = call_gemini(prompt + feedback)
        code = strip_fences(code)
        dst.write_text(code, encoding="utf-8")

        # Execute it against the kit. Any exception becomes the next prompt.
        probe = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "render_scene.py"),
             str(dst), str(outdir / sec.stem), "--check",
             "--max-cue", str(len(cues) - 1)],
            capture_output=True, text=True)
        if probe.returncode == 0:
            cfg.say(f"section {sec.stem}: OK  ({usage.get('total_tokens','?')} tokens)")
            print(probe.stdout.strip())
            return
        err = (probe.stderr or probe.stdout)[-1200:]
        cfg.say(f"section {sec.stem}: rejected — {err.splitlines()[-1][:120]}")
        feedback = ("\n\nYour previous answer failed to run. Fix it and return "
                    "the whole corrected module.\n\nERROR:\n" + err)
    sys.exit(f"[gen] section {sec.stem} still failing after {a.retries + 1} tries")


if __name__ == "__main__":
    main()
