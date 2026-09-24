"""Prompt2Render dual-renderer scene generator.

MATPLOTLIB backend: existing Scenekit state generation.
MANIM backend: true Scene/construct generation with real self.play() animation.
The public generate() API routes each section to the selected backend.

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

import ast
import hashlib
import json
import os
import re
import shutil
import sys
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import align, cfg, llm, manimver, stills
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
        -> Tower of Hanoi puzzle state with EXACTLY THREE pegs. The lists are
           bottom-to-top: a legal peg is descending, e.g. [3,2,1]. A larger
           disk on a smaller disk is only allowed in an explicitly labelled
           illegal/invalid demonstration.
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
  k.draw_asset(ax, asset_id, x, y, width=2.5, height=None)
        -> draw an external SVG/vector asset from the catalog (e.g. 'cpu_core',
           'register_file', 'alu_unit', 'bus_line', 'storage_db') at canvas
           coordinates (x, y) with specified width. Automatically registers
           accurate bounding box for layout audit.
  k.animate_asset(ax, asset_id, x, y, start_time=0.0, duration=2.0, scale=1.0)
        -> register an animated vector asset (e.g. Lottie JSON 'packet_stream',
           'server_rack_pulse') on canvas with start time and duration in seconds.
           Composited over video frames during encode.

DYNAMIC COMPOSITION FOR COMPLEX TOPICS:
  * For complex, novel topics (like Tower of Hanoi, Neural Networks, or Space-filling curves), DO NOT just look for a single built-in function. 
  * Instead, use standard Python loops, conditionals, and coordinate math to compose complex visuals out of generic primitives (k.block, k.circle, k.arrow, k.label, k.grid).
  * Example: To draw a custom stack of items, use a `for` loop to calculate the `y` coordinate and draw a `k.block` for each item.
  * Example: To draw a graph, calculate `(x, y)` for each node, draw `k.circle` for nodes, and `k.arrow` between them.
  * You are writing a Python script; use the full power of Python to dynamically adapt to the topic's requirements.
  * IMPORTANT COLOR POLICY: Do not hard-code arbitrary RGB/hex colors in generated
    scene code. Prefer the semantic scenekit palette (`k.FG`, `k.DIM`, `k.ONE`,
    `k.GOOD`, `k.BAD`, `k.WARN`, `k.ACCENT`). Use `k.ONE` and `k.ACCENT` for
    neutral distinctions, and reserve `k.GOOD`, `k.BAD`, and `k.WARN` for
    correct/wrong/caution states as specified below. If a custom color is truly
    necessary and no palette color is appropriate, keep it minimal and explain
    the semantic reason in the scene code.

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
      * LAYOUT ZONES: You MUST use these strict horizontal zones to keep scenes consistent:
          - y=7.6..8.6: Title Zone (already enforced)
          - y=4.0..7.0: Primary Visualization Zone (Arrays, Trees, Code, Main Data)
          - y=1.5..3.5: Secondary Visualization Zone (Pointers, Variables, Comparisons)
          - y=0.85: Caption Zone (always safe)
      * Never place two elements in the same horizontal band unless they are small and widely separated on the x-axis. If a state feels crowded, split it into two states.
      * DENSITY CEILING & COGNITIVE LOAD: Keep each frame clean and uncluttered. Never place more than 8 visual primitives in a single state/step. If a diagram has multiple sub-components or labels, distribute them across progressive reveal steps (e.g. `steps=2` or `steps=3`) or split them into sequential states.
      * When a frame contains more than one major visual, assign one explicit
        zone to each and leave a visible gap. Do not solve an overlap by merely
        changing colors, font sizes, or z-order; move, resize, or split the
        visual.
      * GHOST STATES: To show movement or transitions, you can draw the previous state of an element with `alpha=0.3` and the new state with `alpha=1.0`, connected by an arrow.
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


def stage_external_assets_for_section(proj: Path, sec) -> tuple[str, str]:
    """Retrieve external realistic assets or curated catalog diagrams for a scene section.

    Priority hierarchy:
      1. Local project assets (`projects/<proj>/assets/`)
      2. Curated domain vector/diagram catalog (`prompt2render/assets/catalog/`)
      3. External verified stock assets (Pixabay, Unsplash, Pexels) with relevance gating
    """
    if os.environ.get("P2R_DISABLE_EXTERNAL_ASSETS", "").strip().lower() in ("1", "true", "yes"):
        return "", ""
    if getattr(sec, "assets", True) is False:
        return "", ""

    try:
        from .project import parse_script
        script_file = proj / "script.md"
        if script_file.exists():
            s_parsed = parse_script(script_file)
            if s_parsed.meta.get("assets") is False or str(s_parsed.meta.get("assets", "")).lower() in ("false", "0", "no", "off"):
                return "", ""
    except Exception:
        pass

    import shutil

    anim_text = getattr(sec, "anim", "") or ""
    narr_text = getattr(sec, "narration", "") or ""
    combined_text = f"{anim_text} {narr_text}".lower()

    build_assets = proj / "build" / "assets"
    build_assets.mkdir(parents=True, exist_ok=True)

    matplot_hints: list[str] = []
    manim_hints: list[str] = []

    # -------------------------------------------------------------------------
    # Tier 1: Local project assets in proj / "assets"
    # -------------------------------------------------------------------------
    local_assets_dir = proj / "assets"
    if local_assets_dir.is_dir():
        for p in sorted(local_assets_dir.glob("*.*")):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
                stem_words = p.stem.lower().replace("_", " ").replace("-", " ").split()
                if any(w in combined_text for w in stem_words if len(w) > 2):
                    staged_name = f"{sec.stem}_{p.name}"
                    staged_file = build_assets / staged_name
                    try:
                        shutil.copyfile(p, staged_file)
                        abs_staged = staged_file.resolve().as_posix()
                        rel_staged = f"assets/{staged_name}"
                        if p.suffix.lower() == ".svg":
                            manim_hints.append(
                                f"- Vector Diagram '{abs_staged}': Realistic diagram of {p.stem.replace('_', ' ').title()}.\n"
                                f"  Display with:\n"
                                f"    diag = SVGMobject(r'{abs_staged}').scale_to_fit_width(6.0).move_to(ORIGIN)\n"
                                f"    self.play(FadeIn(diag))"
                            )
                        else:
                            manim_hints.append(
                                f"- Visual Asset '{abs_staged}': Reference graphic of {p.stem.replace('_', ' ').title()}.\n"
                                f"  Display with:\n"
                                f"    img = ImageMobject(r'{abs_staged}').scale_to_fit_width(5.5).to_edge(LEFT)\n"
                                f"    self.play(FadeIn(img))"
                            )
                        matplot_hints.append(
                            f"- Asset '{rel_staged}': Reference graphic.\n"
                            f"  Draw with: k.draw_asset(ax, '{rel_staged}', x=5.0, y=4.5, width=6.5, height=4.2)"
                        )
                        break
                    except Exception:
                        pass

    # -------------------------------------------------------------------------
    # Tier 2: Built-in curated catalog (heart_anatomy, coronary_artery, etc.)
    # -------------------------------------------------------------------------
    if not manim_hints:
        try:
            from .assets.loader import load_catalog
            from .harness.plugins.retriever_asset_rag import match_assets
            catalog = load_catalog()
            matched_defs = match_assets(combined_text, catalog, max_matches=1, mode="hybrid")
            if matched_defs:
                asset_def = matched_defs[0]
                f_path = asset_def.resolved_file_path()
                if f_path and f_path.is_file():
                    staged_name = f"{sec.stem}_{f_path.name}"
                    staged_file = build_assets / staged_name
                    try:
                        shutil.copyfile(f_path, staged_file)
                        abs_staged = staged_file.resolve().as_posix()
                        rel_staged = f"assets/{staged_name}"
                        if f_path.suffix.lower() == ".svg":
                            manim_hints.append(
                                f"- Vector Asset '{abs_staged}': Realistic anatomical/scientific diagram of {asset_def.name}.\n"
                                f"  Display with:\n"
                                f"    diag = SVGMobject(r'{abs_staged}').scale_to_fit_width(5.5).to_edge(LEFT)\n"
                                f"    self.play(FadeIn(diag))"
                            )
                        else:
                            manim_hints.append(
                                f"- Visual Asset '{abs_staged}': Graphic of {asset_def.name}.\n"
                                f"  Display with:\n"
                                f"    img = ImageMobject(r'{abs_staged}').scale_to_fit_width(5.5).to_edge(LEFT)\n"
                                f"    self.play(FadeIn(img))"
                            )
                        matplot_hints.append(
                            f"- Asset '{rel_staged}': {asset_def.name}.\n"
                            f"  Draw with: k.draw_asset(ax, '{rel_staged}', x=5.0, y=4.5, width=6.5, height=4.2)"
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Tier 3: External stock providers with strict semantic relevance gating
    # -------------------------------------------------------------------------
    rend = select_renderer(sec)
    is_manim = is_manim_renderer(rend) or rend in {"manim", "manim_3d"}
    wants_photo = any(tag in anim_text.lower() for tag in ["[photo]", "[stock]", "[image]", "[asset]", "photo", "photograph"])

    if not manim_hints and not matplot_hints and (not is_manim or wants_photo):
        try:
            from .assets.providers import get_available_providers, search_all_providers
            from .assets.cache import AssetCache
            from .assets.preprocessor import prepare_scene_asset
            from .assets.relevance import is_asset_relevant
            from .harness.plugins.retriever_external_asset import _extract_asset_queries

            providers = get_available_providers(allow_mock_fallback=False)
            queries = _extract_asset_queries(anim_text, narr_text)

            cache = AssetCache()
            hits = []

            if providers and queries:
                for q_info in queries:
                    q = q_info["query"]
                    t = q_info.get("type", "photo")
                    found = search_all_providers(query=q, providers=providers, limit_per_provider=3, asset_type=t)
                    for f in found:
                        is_rel, score, reason = is_asset_relevant(f, f"{anim_text} {narr_text}")
                        if not is_rel:
                            continue
                        if f.id not in {h[0].id for h in hits}:
                            hits.append((f, q_info.get("role", "card")))
                    if len(hits) >= 2:
                        break

            for hit, role in hits:
                try:
                    prov = next((p for p in providers if p.name == hit.provider), providers[0])
                    cached_raw = cache.fetch_or_download(hit, prov)
                    staged_name = f"{sec.stem}_{hit.provider}_{hit.id.split('_', 1)[-1]}.png"
                    staged_file = build_assets / staged_name

                    prepare_scene_asset(
                        cached_raw,
                        staged_file,
                        role=role,
                        target_width=1920 if role == "background" else 960,
                        target_height=1080 if role == "background" else 540,
                    )

                    rel_staged = f"assets/{staged_name}"
                    matplot_hints.append(
                        f"- Asset '{rel_staged}': Real-world photo of {hit.title} by {hit.author} ({hit.provider.title()}).\n"
                        f"  Draw with: k.draw_asset(ax, '{rel_staged}', x=5.0, y=4.5, width=6.5, height=4.2)"
                    )
                    abs_staged = staged_file.resolve().as_posix()
                    manim_hints.append(
                        f"- Asset '{abs_staged}': Real-world photo of {hit.title} by {hit.author} ({hit.provider.title()}).\n"
                        f"  Display with:\n"
                        f"    img = ImageMobject(r'{abs_staged}').scale_to_fit_width(5.5).to_edge(LEFT)\n"
                        f"    self.play(FadeIn(img))"
                    )
                except Exception:
                    continue
        except Exception:
            pass

    mat_block = ""
    if matplot_hints:
        mat_block = (
            "AVAILABLE REAL-WORLD ASSETS (Staged on disk — incorporate into scene visuals for realism):\n"
            + "\n".join(matplot_hints)
            + "\nUse k.draw_asset(ax, '<path>', ...) to ground the explanation in real-world photography!\n"
        )

    manim_block = ""
    if manim_hints:
        manim_block = (
            "VISUAL ASSET INTEGRATION (Staged verified reference asset):\n"
            "Incorporate the following verified reference asset into your scene to anchor the explanation:\n"
            + "\n".join(manim_hints)
            + "\nRECOMMENDED LAYOUT PATTERN:\n"
            "  * Place the visual asset in a dedicated anchor zone (e.g. LEFT * 3.2 + UP * 0.2) and place the dynamic animations / equations in the opposite zone (e.g. RIGHT * 3.2 + UP * 0.2) or use SplitStage.\n"
            "  * For ImageMobjects, frame with a styled subtle border: border = SurroundingRectangle(img, color='#388BFD', buff=0.05, stroke_width=2)\n"
            "  * Keep the visual asset clearly separated from the bottom caption safe zone (y < -3.0).\n"
        )

    return mat_block, manim_block


def build_prompt(script: Script, sec, sents: list[dict],
                 include_reveal: bool = True, previous_context: str = "",
                 asset_hint: str = "", trace_hint: str = "") -> str:
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
    
    {previous_context}

    {asset_hint}

    {trace_hint}

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
      * COLOR DISCIPLINE: use only the documented semantic palette (`k.FG`,
        `k.DIM`, `k.ONE`, `k.GOOD`, `k.BAD`, `k.WARN`, `k.ACCENT`) unless a
        documented primitive requires another value. Never hard-code arbitrary
        hex/RGB colors merely for visual preference; color must communicate
        semantic state, not decoration.
      * INTENTIONAL RULE DEMONSTRATION: If the narration explicitly explains an illegal move or anti-pattern for the topic, you MUST actually draw the physically illegal state to show what NOT to do. You MUST also clearly mark it as illegal (e.g., use `k.title(ax, "ILLEGAL MOVE", color=k.BAD)` or `k.badge(ax, x, y, "X", color=k.BAD)`). Do NOT just draw a legal state and label it illegal.
      * CONTINUITY: If this is not the first section, you MUST maintain the same coordinates (`x`, `y`) for persistent data structures (like the main array or tree) that were used in the previous section. Do not let the main visualization jump up and down between scenes.
      * LAYOUT IS THE THING THAT USUALLY FAILS. Two elements in the same
        horizontal band will overlap and ruin the frame.
      * k.curves fills its whole w x h box. Never draw a k.table, k.array or
        k.code inside that box.
      * Pass `bracket` a plain string, never a tuple.
      * No imports, no file IO, no prints. `k` is already available.
      * PRE-FLIGHT CONTRACT: use only the documented k.* signatures and valid
        literal data. k.hanoi accepts exactly three peg lists; never pass four
        pegs or another variant. k.grid must be rectangular, k.table rows must
        have equal widths, and array/pointer indices must stay inside the data.
        If a topic needs a different structure, compose it from the generic
        primitives instead of inventing an undocumented k.* call.

    Output ONLY the Python code, no prose, no markdown fences.
    """).strip()


def sanitize_python_source(code: str) -> str:
    """Normalize unicode typographical characters that break Python parsing."""
    if not isinstance(code, str):
        return ""
    # Strip BOM
    code = code.lstrip("\ufeff")
    # Replace smart quotes and apostrophes
    code = code.replace("\u201c", '"').replace("\u201d", '"')
    code = code.replace("\u2018", "'").replace("\u2019", "'")
    # Replace em-dash, en-dash, minus sign with ascii dash
    code = code.replace("\u2014", "-").replace("\u2013", "-").replace("\u2212", "-")
    # Replace non-breaking spaces
    code = code.replace("\u00a0", " ").replace("\u202f", " ")
    return code


def strip_fences(code: str) -> str:
    code = sanitize_python_source(code).strip()
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", code, re.S)
    if m:
        return sanitize_python_source(m.group(1)).strip()
    m_loose = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", code, re.S)
    return sanitize_python_source(m_loose.group(1)).strip() if m_loose else code


_LITERAL_MISSING = object()
_ALLOWED_PRIMITIVES = {
    "title", "caption", "label", "bits", "bit_brace", "arrow", "strike",
    "badge", "compare", "addition", "number_line", "dial", "register",
    "array", "predicate_strip", "code", "table", "rectangle", "curves",
    "hanoi", "tree", "grid", "block", "bus", "circle", "draw_asset",
    "animate_asset",
}


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, MemoryError, RecursionError):
        return _LITERAL_MISSING


def _argument(node: ast.Call, position: int, name: str):
    """Get a positional or keyword argument without executing model code."""
    if len(node.args) > position:
        return node.args[position]
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _source_value(node):
    value = _literal(node)
    if value is not _LITERAL_MISSING:
        return value
    try:
        return ast.unparse(node)
    except Exception:
        return "<dynamic>"


def trace_scene_source(code: str) -> dict:
    """Return a JSON-serializable trace of documented ``k.*`` calls.

    The trace is static by design: generated code is untrusted model output and
    must not be executed merely to inspect it. Literal arguments are preserved as
    values; dynamic expressions are represented by their source text.
    """
    tree = ast.parse(code)
    calls = []
    primitive_counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "k"):
            continue
        primitive = node.func.attr
        primitive_counts[primitive] = primitive_counts.get(primitive, 0) + 1
        fn = _containing_function(tree, node)
        calls.append({
            "line": node.lineno,
            "state": fn.name if fn is not None else "<module>",
            "primitive": primitive,
            "args": [_source_value(arg) for arg in node.args],
            "keywords": {kw.arg: _source_value(kw.value) for kw in node.keywords if kw.arg},
        })
    calls.sort(key=lambda item: item["line"])
    states = [node.name for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "states"]
    return {"states_functions": states, "primitive_counts": primitive_counts, "calls": calls}


def _containing_function(tree: ast.AST, target: ast.AST) -> ast.FunctionDef | None:
    """Return the generated state function containing target, if any."""
    for fn in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        if any(child is target for child in ast.walk(fn)):
            return fn
    return None


def _has_intent_marker(fn: ast.FunctionDef | None) -> bool:
    if fn is None:
        return False
    markers = ("illegal", "invalid", "not allowed", "not valid", "wrong", "anti-pattern", "bad move")
    text = " ".join(str(n.value).lower() for n in ast.walk(fn)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str))
    return any(marker in text for marker in markers)


#: Environments where a bare '&' is a legitimate column/alignment separator
#: rather than a LaTeX special character that needs escaping.
_LATEX_AMPERSAND_ENVIRONMENTS = (
    "align", "align*", "alignat", "alignat*", "eqnarray", "eqnarray*",
    "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "array",
    "tabular", "cases", "aligned",
)


def _check_latex_string(text: str, func_name: str, lineno: int) -> list[str]:
    """Flag raw LaTeX special characters that reliably crash the compiler.

    This is deliberately narrow: it only flags '&', '%', and '#' when they
    appear unescaped outside an environment that legitimately uses '&' as a
    separator, plus unbalanced (unescaped) braces. It does not attempt to
    validate LaTeX syntax in general.
    """
    errors: list[str] = []

    raw_math_glyphs = "".join(char for char in text if ord(char) > 127)
    if raw_math_glyphs:
        errors.append(
            f"{func_name}() contains raw Unicode math glyph(s) "
            f"{raw_math_glyphs!r} (line {lineno}); use ASCII LaTeX commands "
            "such as \\rangle and \\langle instead"
        )

    if re.search(r"\\text\{[^{}\n]*\^\\[A-Za-z]+", text):
        errors.append(
            f"{func_name}() uses math superscript syntax inside \\text{{}} "
            f"(line {lineno}); move it outside \\text{{}} or write the "
            "word in text mode"
        )

    has_tabular_env = any(
        f"begin{{{env}}}" in text for env in _LATEX_AMPERSAND_ENVIRONMENTS
    )

    for match in re.finditer(r"(\\*)([&%#])", text):
        backslashes, char = match.groups()
        if len(backslashes) % 2 == 1:
            # An odd number of backslashes means this occurrence is escaped
            # (e.g. r"\&"); an even number (including zero) means the
            # backslashes themselves are literal and the special character
            # that follows is still raw.
            continue
        if char == "&" and has_tabular_env:
            continue
        errors.append(
            f"{func_name}() contains an unescaped '{char}' (line {lineno}); "
            f"use '\\{char}' or LaTeX will fail to compile"
        )

    # Brace balance, ignoring escaped braces (\{ \}), which are literal glyphs.
    unescaped = re.sub(r"\\[{}]", "", text)
    if unescaped.count("{") != unescaped.count("}"):
        errors.append(
            f"{func_name}() has unbalanced braces (line {lineno}); "
            "LaTeX will fail to compile"
        )

    return errors


#: Mobject/VMobject instance methods whose real signature takes no **kwargs,
#: so a keyword-argument mismatch caught via inspect.signature() will match
#: Manim's own runtime TypeError exactly. Methods that accept **kwargs (e.g.
#: scale, arrange, rotate) are deliberately excluded — checking them would
#: never catch anything since **kwargs swallows any name.
_MANIM_NO_KWARGS_METHODS = (
    "next_to",
    "move_to",
    "to_edge",
    "align_to",
    "set_color",
    "become",
    "shift",
)


def _manim_module():
    """Best-effort lazy import of the installed manim package.

    Returns ``None`` when manim is not installed rather than raising, so
    SceneKit-only installs are unaffected.
    """
    try:
        import manim
        return manim
    except Exception:
        return None


def _bound_names(tree: ast.AST) -> set[str]:
    """Collect every name bound anywhere in the module.

    Deliberately flat (whole-module, not scope-aware): the goal is only to
    avoid false positives on legitimately-defined names, not to reproduce
    real Python scoping. Missing a scope violation is fine; flagging a name
    the code actually defines is not.
    """
    bound: set[str] = set()

    def add_target(target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            bound.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                add_target(elt)
        elif isinstance(target, ast.Starred):
            add_target(target.value)

    def add_args(args: ast.arguments) -> None:
        for arglist in (args.posonlyargs, args.args, args.kwonlyargs):
            for arg in arglist:
                bound.add(arg.arg)
        if args.vararg:
            bound.add(args.vararg.arg)
        if args.kwarg:
            bound.add(args.kwarg.arg)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import,)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                add_target(target)
        elif isinstance(node, ast.AnnAssign):
            add_target(node.target)
        elif isinstance(node, getattr(ast, "NamedExpr", ())):
            add_target(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            add_target(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars:
                    add_target(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                bound.add(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(node.name)
            add_args(node.args)
        elif isinstance(node, ast.Lambda):
            add_args(node.args)
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.comprehension):
            add_target(node.target)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)

    return bound


def _check_undefined_manim_names(tree: ast.AST) -> list[str]:
    """Flag identifiers that are neither imported, assigned, nor a builtin.

    Generated Manim code routinely hallucinates plausible-looking but
    nonexistent identifiers (``RED_M``, ``BLUE_L``, ``ease_out_sine``) that
    only surface as a ``NameError`` mid-render, after minutes of animation
    have already played. Catching them statically costs nothing and needs
    no LLM round-trip.
    """
    manim = _manim_module()
    if manim is None:
        return []

    import builtins as _builtins
    try:
        from .assets import mobjects as _mobjects
        mobjects_names = set(dir(_mobjects))
    except Exception:
        mobjects_names = set()

    known = set(dir(manim)) | set(dir(_builtins)) | mobjects_names | {"__name__", "__file__", "CENTER", "CYAN", "MAGENTA", "AMBER", "LIME", "VIOLET", "INDIGO"}
    known |= _bound_names(tree)

    errors: list[str] = []
    seen: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in known:
                continue
            key = (node.id, node.lineno)
            if key in seen:
                continue
            seen.add(key)
            errors.append(
                f"'{node.id}' is not defined (line {node.lineno}); "
                "this looks like a hallucinated manim/numpy identifier — "
                "use a real one or define it"
            )

    return errors


def _check_manim_kwarg_signatures(tree: ast.AST) -> list[str]:
    """Validate keyword arguments against the real installed Manim classes.

    Two shapes are checked, both via ``inspect.signature`` against the
    actual installed manim package so the result matches Manim's own
    ``TypeError`` exactly:

    1. Direct construction, ``ClassName(kw=...)``, when ``ClassName``
       resolves to a manim class whose ``__init__`` has no ``**kwargs``.
    2. A call to one of ``_MANIM_NO_KWARGS_METHODS`` on any object — nearly
       every Mobject subclass inherits these methods unmodified, so checking
       against the base ``Mobject`` implementation is safe without tracking
       the receiver's inferred type.
    """
    manim = _manim_module()
    if manim is None:
        return []

    import inspect

    errors: list[str] = []

    mobject_cls = getattr(manim, "Mobject", None)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        keywords = [kw.arg for kw in node.keywords if kw.arg is not None]
        if not keywords:
            continue

        target = None
        label = None

        if isinstance(node.func, ast.Name):
            candidate = getattr(manim, node.func.id, None)
            if inspect.isclass(candidate):
                target = candidate
                label = node.func.id
        elif isinstance(node.func, ast.Attribute):
            if mobject_cls is not None and node.func.attr in _MANIM_NO_KWARGS_METHODS:
                target = getattr(mobject_cls, node.func.attr, None)
                label = node.func.attr

        if target is None:
            continue

        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            continue

        params = sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            continue

        for kw in keywords:
            if kw not in params:
                errors.append(
                    f"{label}() does not accept '{kw}=' — not a valid "
                    f"argument in the installed manim {getattr(manim, '__version__', '')} "
                    f"(line {node.lineno})"
                )

    return errors


def _check_play_raw_mobject(tree: ast.AST) -> list[str]:
    """Flag a bare Mobject constructed directly inside ``self.play(...)``.

    ``self.play()`` takes Animations, not Mobjects — ``self.play(Circle())``
    fails with "X cannot be converted to an animation" only once Manim is
    already mid-render. A model that reaches for e.g. ``SurroundingRectangle``
    to highlight something and forgets to wrap it in ``Create(...)``/
    ``Indicate(...)``/etc. produces exactly this, and since the object
    resolves fine syntactically the generic checks above don't catch it.
    Checked against the real installed manim classes so it only fires on an
    actual Mobject (never on legitimate Animation calls like ``FadeIn``).
    """
    manim = _manim_module()
    if manim is None:
        return []

    import inspect

    mobject_cls = getattr(manim, "Mobject", None)
    animation_cls = getattr(manim, "Animation", None)
    if mobject_cls is None or animation_cls is None:
        return []

    errors: list[str] = []

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "play"
        ):
            continue

        for arg in node.args:
            if not (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)):
                continue
            candidate = getattr(manim, arg.func.id, None)
            if not inspect.isclass(candidate):
                continue
            if (
                issubclass(candidate, mobject_cls)
                and not issubclass(candidate, animation_cls)
            ):
                errors.append(
                    f"self.play() was passed {arg.func.id}(...) directly — "
                    f"{arg.func.id} is a Mobject, not an Animation; wrap it "
                    f"(e.g. Create({arg.func.id}(...)), Indicate(...), "
                    f".animate) (line {arg.lineno})"
                )

    return errors


#: Actionable fix hints for the most common hallucinated MathTex methods.
_MATHTEX_METHOD_FIX_HINTS = {
    "get_parts_by_tex": (
        "it is a Tex method, not available on MathTex; select subparts of a "
        "MathTex with get_part_by_tex(...), or build the pieces as separate "
        "MathTex mobjects combined in a VGroup"
    ),
}


def _check_manim_math_tex_method_calls(tree: ast.AST) -> list[str]:
    """Flag calls to methods that do not exist on MathTex objects.

    Calling a missing attribute on a Mobject does not raise
    ``AttributeError`` at runtime: ``Mobject.__getattr__`` converts it into
    a property getter, so ``vec.get_parts_by_tex("0")`` crashes mid-render
    with the cryptic ``getter() takes 1 positional argument but 2 were
    given``. Checking the called name against the installed MathTex class
    catches the hallucination statically.

    Receiver inference is deliberately conservative: only direct
    ``MathTex(...)`` chains and simple ``name = MathTex(...)`` assignments
    are treated as MathTex receivers, which is the shape these
    hallucinations take in generated scenes.
    """

    manim = _manim_module()
    if manim is None:
        return []

    mathtex_cls = getattr(manim, "MathTex", None)
    if mathtex_cls is None:
        return []

    mathtex_names: set[str] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            func = node.value.func
            fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)

            if fname == "MathTex":
                mathtex_names.add(node.targets[0].id)

    def receiver_is_mathtex(value: ast.AST) -> bool:
        if isinstance(value, ast.Call):
            func = value.func
            fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            return fname == "MathTex"

        if isinstance(value, ast.Name):
            return value.id in mathtex_names

        return False

    errors: list[str] = []
    seen: set[tuple[str, int]] = set()

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
        ):
            continue

        method = node.func.attr

        if not receiver_is_mathtex(node.func.value):
            continue

        if method not in _MATHTEX_METHOD_FIX_HINTS and hasattr(mathtex_cls, method):
            continue

        key = (method, node.lineno)
        if key in seen:
            continue
        seen.add(key)

        hint = _MATHTEX_METHOD_FIX_HINTS.get(
            method,
            "the method does not exist on MathTex in the installed manim; "
            "use a real MathTex/VMobject API instead",
        )
        errors.append(
            f"MathTex.{method}() does not exist in the installed manim — "
            f"{hint} (line {node.lineno})"
        )

    return errors


def validate_manim_source(code: str) -> list[str]:
    """Validate generated Manim code before rendering.

    Catches known Manim API incompatibilities (see manimver.py for the
    version this build targets), invalid imports, and structural mistakes
    without running the code.
    """
    errors: list[str] = []
    import ast
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error at line {exc.lineno}: {exc.msg}"]

    has_scene_class = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            has_scene_class = True
            
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # Only allow from manim import * or import math/numpy or prompt2render helper modules
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").strip()
                if mod == "manim" or mod.startswith("manim.") or mod.startswith("prompt2render") or mod in {"math", "numpy", "random"}:
                    continue
            if isinstance(node, ast.Import):
                if any(alias.name in {"manim", "math", "numpy", "random"} or alias.name.startswith("manim.") or alias.name.startswith("prompt2render") for alias in node.names):
                    continue
            errors.append(f"imports other than 'manim', 'math', or 'numpy' are not allowed (line {node.lineno})")
            
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in {"print", "open", "exec", "eval"}:
                errors.append(f"{func_name}() is not allowed in a scene module (line {node.lineno})")

            # Scenekit's `k.*` primitives (matplotlib backend) have no
            # meaning against real Manim -- catches a model reverting to
            # the wrong backend's API mid-generation.
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "k"
            ):
                errors.append(f"Scenekit k.{node.func.attr}() found in Manim mode (line {node.lineno})")


            # Known-bad kwargs, independent of the exact installed Manim
            # version (see manimver.py). Worded against "the supported
            # Manim" rather than a bare version literal so this stays
            # accurate whichever release P2R_MANIM_VERSION declares.
            _target = manimver.target_version()
            if func_name in {"get_x_label", "get_y_label"}:
                for kw in node.keywords:
                    if kw.arg in {"font_size", "direction"}:
                        errors.append(f"Axes.{func_name}() does not accept '{kw.arg}' in Manim {_target} (line {node.lineno})")

            if func_name == "move_to":
                for kw in node.keywords:
                    if kw.arg == "corner":
                        errors.append(f"move_to() does not accept 'corner=' in Manim {_target}; use align_to() or next_to() (line {node.lineno})")

            if func_name == "Code":
                for kw in node.keywords:
                    if kw.arg == "theme":
                        errors.append(f"Code() does not accept 'theme=' in Manim {_target} (line {node.lineno})")
                    if kw.arg == "insert_line_numbers":
                        errors.append(f"Code() expects 'add_line_numbers=', not 'insert_line_numbers=' (line {node.lineno})")
                    if kw.arg == "code":
                        errors.append(f"Code() expects 'code_string=', not 'code=', in Manim {_target} (line {node.lineno})")
                    if kw.arg == "style":
                        errors.append(f"Code() expects 'formatter_style=', not 'style=', in Manim {_target} (line {node.lineno})")
                    if kw.arg == "font_size":
                        errors.append(f"Code() no longer accepts 'font_size=' directly in Manim {_target}; pass it inside paragraph_config={{'font_size': ...}} (line {node.lineno})")

            if func_name in {"MobjectTable", "Table", "IntegerTable", "DecimalTable", "MathTable"}:
                for kw in node.keywords:
                    if kw.arg in {"row_height", "col_widths", "include_background"}:
                        errors.append(f"{func_name}() does not accept '{kw.arg}=' in Manim {_target} (line {node.lineno})")

            if func_name == "set_shadow":
                errors.append(f"set_shadow() is deprecated and causes rendering errors (line {node.lineno})")
                
            if func_name in {"SurroundingRectangle", "BackgroundRectangle", "always_redraw"}:
                for arg in node.args:
                    # Catch common coordinate generators like n2p, number_to_point, c2p, coords_to_point, get_center
                    for child in ast.walk(arg):
                        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                            if child.func.attr in {"n2p", "number_to_point", "c2p", "coords_to_point", "get_center"}:
                                errors.append(f"{func_name}() requires a Mobject, but was passed coordinates from {child.func.attr}() (line {node.lineno})")
                                break
                
            # Prevent scalar interpolation in put_start_and_end_on / move_to inside lambda/UpdateFromAlphaFunc.
            # Manim requires 3D coordinate arrays, not a single float. Search recursively because
            # the bad expression is often nested inside number_line.number_to_point(alpha * PI).
            if func_name in {"put_start_and_end_on", "move_to"}:
                for arg in node.args:
                    for child in ast.walk(arg):
                        if (isinstance(child, ast.BinOp) and isinstance(child.op, ast.Mult)
                                and isinstance(child.left, ast.Name) and child.left.id == "alpha"
                                and isinstance(child.right, ast.Name) and child.right.id == "PI"):
                            errors.append(f"{func_name}() contains scalar alpha * PI where a 3D coordinate array is required (line {node.lineno})")
                            break
            
            # Catch known invalid kwargs across all Mobject constructors to prevent 
            # generic "unexpected keyword argument" crashes at runtime.
            if func_name in {"Text", "MathTex", "Tex", "VGroup", "Line", "Arrow", "Circle", "Square", "Rectangle", "Dot"}:
                for kw in node.keywords:
                    if kw.arg in {"include_background", "row_height", "col_widths", "corner", "alignment", "word_wrap_width", "multiline", "stroke_dash_array"}:
                        errors.append(f"{func_name}() does not accept '{kw.arg}=' in Manim {_target} (line {node.lineno})")

            _INVALID_VMOBJECT_METHODS = {
                "lighten", "darken", "glow", "pulse", "resize", 
                "set_color_by_gradient", "highlight", "set_shadow"
            }
            if func_name in _INVALID_VMOBJECT_METHODS:
                errors.append(
                    f"Mobject does not have a '.{func_name}()' method in Manim {_target}. "
                    f"Use .set_opacity(), .set_color(), or color interpolation instead (line {node.lineno})"
                )

            if (
                func_name == "set_stroke"
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "animate"
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id in {"Circle", "Line", "Arrow", "Square", "Rectangle", "Dot"}
            ):
                errors.append(
                    f"{node.func.value.value.id}.animate is a class property; "
                    f"use an instance name before .animate.set_stroke() (line {node.lineno})"
                )

            # Text-only kwargs hallucinated onto MathTex/Tex. MathTex/Tex
            # render through LaTeX: weight/slant/font and the t2* maps are
            # properties of the Pango-backed Text mobject only. Passing them
            # crashes deep inside Mobject.__init__ with
            # "unexpected keyword argument 'weight'" -- caught here for free.
            if func_name in {"MathTex", "Tex"}:
                for kw in node.keywords:
                    if kw.arg in {"weight", "slant", "font", "line_spacing",
                                  "disable_ligatures", "t2c", "t2w", "t2s", "t2g"}:
                        errors.append(
                            f"{func_name}() does not accept '{kw.arg}=' — that is a "
                            "Text-only option; remove it (bold/italic emphasis is not "
                            f"available on {func_name}; use color or size instead) "
                            f"(line {node.lineno})"
                        )

            # MathTex/Tex hand the string straight to LaTeX. A raw, unescaped
            # '&', '%', or '#' outside a tabular/align environment is a
            # column separator / comment / macro-parameter character to
            # LaTeX, not a literal glyph, and reliably crashes the compiler
            # (this is exactly what took down section 06's j-invariant label:
            # r"\text{Modular identities & } j\text{-invariant...}"). Catch
            # it statically instead of paying for a failed Manim subprocess.
            if func_name in {"MathTex", "Tex"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        errors.extend(
                            _check_latex_string(arg.value, func_name, node.lineno)
                        )

    if not has_scene_class:
        errors.append("module must define a Scene class")
        
    # We want to encourage the LLM to use self.wait() to align animations with cues.
    # We can't statically prove the exact duration sum without a complex interpreter, 
    # but we can at least ensure they didn't completely ignore the wait instruction.
    has_wait = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "wait":
                has_wait = True
                if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in {0, 0.0}:
                    errors.append(f"self.wait(0) is invalid in Manim; omit the wait call when gap is 0 (line {node.lineno})")
                
    if has_scene_class and not has_wait:
        errors.append("module does not contain any self.wait() calls; you MUST use self.wait() to align animations with narration cues")

    # Exactly one Scene-inheriting class, each implementing construct(self)
    # and driving its animation through self.play() -- stricter than the
    # generic has_scene_class check above (which only requires *some* class
    # to exist), consolidated in from the formerly-separate
    # _validate_manim_source so every Manim generation path is checked by
    # the same rules (previously only verifier_execution used this
    # function; scenes._generate_manim's own retry loop used a private,
    # looser-in-some-ways/stricter-in-others duplicate -- SS15/F15).
    allowed_scene_bases = {
        "Scene",
        "ThreeDScene",
        "MovingCameraScene",
        "LinearTransformationScene",
        "SpecialThreeDScene",
    }
    scene_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and base.id in allowed_scene_bases)
            or (isinstance(base, ast.Attribute) and base.attr in allowed_scene_bases)
            for base in node.bases
        )
    ]

    if not scene_classes:
        errors.append("no class inheriting from Scene was generated")
    elif len(scene_classes) != 1:
        errors.append("generate exactly one main Scene subclass")

    for cls in scene_classes:
        if not any(
            isinstance(member, ast.FunctionDef) and member.name == "construct"
            for member in cls.body
        ):
            errors.append(f"{cls.name} must implement construct(self)")

    if scene_classes and not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "play"
        for node in ast.walk(tree)
    ):
        errors.append("scene contains no self.play() calls")

    if re.search(r"^\s*def\s+states\s*\(", code, re.MULTILINE):
        errors.append("states() is forbidden in Manim mode")

    # General, introspection-backed checks against the actually-installed
    # manim package. These catch hallucinated identifiers and invalid
    # keyword arguments that the hand-curated checks above don't enumerate,
    # using the real API surface instead of a fixed blocklist.
    errors.extend(_check_undefined_manim_names(tree))
    errors.extend(_check_manim_kwarg_signatures(tree))
    errors.extend(_check_play_raw_mobject(tree))
    errors.extend(_check_manim_math_tex_method_calls(tree))

    return list(dict.fromkeys(errors))


def validate_scene_source(code: str, max_cue: int | None = None) -> list[str]:
    """Validate generated source before it reaches Matplotlib.

    This is deliberately structural and topic-agnostic. It catches impossible API
    inputs, malformed table/grid data, invalid pointer indices, forbidden imports,
    and unsupported primitive calls. It does not pretend to prove arbitrary domain
    correctness; explicit topic profiles or the semantic reviewer remain responsible
    for claims that cannot be inferred from the drawing API alone.
    """
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error at line {exc.lineno}: {exc.msg}"]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append(f"imports are not allowed (line {node.lineno})")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"print", "open", "exec", "eval"}:
            errors.append(f"{node.func.id}() is not allowed in a scene module (line {node.lineno})")
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "k"):
            continue

        method = node.func.attr
        if method not in _ALLOWED_PRIMITIVES:
            errors.append(f"unsupported k.{method} primitive (line {node.lineno})")
            continue

        # All checks below only apply when the model supplied literal data. Dynamic
        # expressions are left for the real renderer and its exact audit.
        if method == "hanoi":
            state_node = _argument(node, 1, "state")
            state = _literal(state_node) if state_node is not None else _LITERAL_MISSING
            if state is not _LITERAL_MISSING:
                if not isinstance(state, list) or len(state) != 3:
                    errors.append("k.hanoi supports exactly three pegs: [left, middle, right]")
                elif any(not isinstance(peg, list) for peg in state):
                    errors.append("k.hanoi state must be a list of three peg lists")
                else:
                    disks = [d for peg in state for d in peg]
                    if any(not isinstance(d, (int, float)) or isinstance(d, bool) or d <= 0 for d in disks):
                        errors.append("k.hanoi disk sizes must be positive numbers")
                    elif len(set(disks)) != len(disks):
                        errors.append("k.hanoi cannot draw duplicate disk sizes")
                    elif any(peg[i] < peg[i + 1] for peg in state for i in range(len(peg) - 1)) and not _has_intent_marker(_containing_function(tree, node)):
                        errors.append("k.hanoi shows a larger disk on a smaller disk without an explicit illegal/invalid label")
        elif method == "grid":
            data_node = _argument(node, 1, "data")
            data = _literal(data_node) if data_node is not None else _LITERAL_MISSING
            if data is not _LITERAL_MISSING and isinstance(data, list) and data:
                if any(not isinstance(row, list) for row in data):
                    errors.append("k.grid data must be a list of row lists")
                elif len({len(row) for row in data}) > 1:
                    errors.append("k.grid rows must all have the same number of columns")
        elif method == "table":
            rows_node = _argument(node, 1, "rows")
            rows = _literal(rows_node) if rows_node is not None else _LITERAL_MISSING
            if rows is not _LITERAL_MISSING and isinstance(rows, list) and rows:
                widths = [len(row) for row in rows if isinstance(row, (list, tuple))]
                if len(widths) != len(rows):
                    errors.append("k.table rows must be lists or tuples")
                elif len(set(widths)) > 1:
                    errors.append("k.table rows must all have the same number of columns")
        elif method == "array":
            values_node = _argument(node, 1, "values")
            values = _literal(values_node) if values_node is not None else _LITERAL_MISSING
            if values is not _LITERAL_MISSING and not isinstance(values, (list, tuple)):
                errors.append("k.array values must be a list or tuple")
            for name, pos in (("lo", 5), ("hi", 6), ("mid", 7), ("found", 8)):
                arg_node = _argument(node, pos, name)
                value = _literal(arg_node) if arg_node is not None else _LITERAL_MISSING
                if isinstance(value, int) and not isinstance(value, bool) and isinstance(values, (list, tuple)) and not (-1 <= value < len(values)):
                    errors.append(f"k.array {name} index {value} is outside 0..{len(values)-1}")
        elif method == "predicate_strip":
            flags_node = _argument(node, 1, "flags")
            flags = _literal(flags_node) if flags_node is not None else _LITERAL_MISSING
            if flags is not _LITERAL_MISSING and isinstance(flags, list):
                if any(v not in (0, 1, False, True) for v in flags):
                    errors.append("k.predicate_strip flags must contain only 0/1 or False/True")
        elif method == "block":
            for name, pos in (("w", 4), ("h", 5)):
                if len(node.args) > pos:
                    value = _literal(node.args[pos])
                    if isinstance(value, (int, float)) and value <= 0:
                        errors.append(f"k.block {name} must be positive")

    # Cue validation is kept here so invalid generated code is rejected before a
    # Matplotlib render and before a retry can be polluted by a stale PNG directory.
    states_fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "states"), None)
    if states_fn is not None and max_cue is not None:
        return_values = [n for n in ast.walk(states_fn) if isinstance(n, ast.Return)]
        for ret in return_values:
            items = ret.value.elts if isinstance(ret.value, (ast.List, ast.Tuple)) else []
            previous = -1
            for item in items:
                if not isinstance(item, (ast.Tuple, ast.List)) or len(item.elts) < 3:
                    continue
                cue = _literal(item.elts[1])
                if isinstance(cue, int):
                    if cue <= previous:
                        errors.append(f"cue indices must strictly increase; found {cue} after {previous}")
                    if cue < 0 or cue > max_cue:
                        errors.append(f"cue index {cue} is outside valid range 0..{max_cue}")
                    previous = cue
    return list(dict.fromkeys(errors))



# ---------------------------------------------------------------------------
# DUAL RENDERER
# ---------------------------------------------------------------------------

MANIM_API_DOC_TEMPLATE = r"""
REAL MANIM BACKEND — PRODUCTION CONTRACT

Generate REAL Manim Community Edition __MANIM_VERSION__ Python. Do not use
APIs introduced after v__MANIM_VERSION__. This backend does NOT use Scenekit
and does NOT generate def states().

Required:
    from manim import *
    from prompt2render.assets.mobjects import (
        FlowStage, SplitStage, HeroFocusStage, BenchmarkStage,
        ServerNode, ClientCluster, DatabaseNode, ConfigCodeCard, MetricBadge,
        ArrayGrid, FormulaCard, KeyBadge, MemoryBankMobject, BinaryTreeMobject
    )
    class SceneXX(Scene):
        def construct(self):
            ...

Allowed imports:
    from manim import *
    from prompt2render.assets.mobjects import *
    import math
    import numpy as np

UNIVERSAL SPATIAL LAYOUT STAGES (USE THESE TO PREVENT ALL OVERLAPS):
Choose the single best Stage for the section's educational purpose:

1. FlowStage(nodes=[...], direction=RIGHT, buff=0.6)
   -> Connects sequential process nodes (e.g. Client -> DNS Resolver -> Root Server -> Auth Server, or Client -> SSH Handshake -> Server).
   -> Automatically spaces nodes horizontally across canvas and draws connecting arrows.
   -> Send packet: `dot, target = stage.pulse_signal(0, 1); self.play(dot.animate.move_to(target))`

2. SplitStage(left=..., right=..., left_title="", right_title="", divider=True)
   -> Side-by-side comparison: left half (x=-3.4) and right half (x=+3.4) mathematically isolated.
   -> Perfect for Code vs Output, Public vs Private, Old vs New, or Theory vs Calculation.

3. HeroFocusStage(hero=..., badges=[...], title="")
   -> Centers a complex main visualization (Array, Tree, Server, Formula) and auto-positions peripheral badges safely below it.

4. BenchmarkStage(cards=[...], title="Performance Metrics")
   -> Neatly arranges 2-4 KPI/Metric cards in a horizontal comparison row.

CROSS-DOMAIN COMPONENT WIDGETS:
  * ServerNode(name="DNS Resolver", subtext="Recursive Cache", status="active")
    -> Glassmorphic server card with status dot ("active", "warning", "error", "idle").
  * ClientCluster(count=3, label="Web Clients", color="#00F0FF")
    -> Clean group of client user nodes.
  * DatabaseNode(name="Zone File", width=2.0, height=1.8, color="#A855F7")
    -> Multi-tier database storage cylinder with disk partitions.
  * ConfigCodeCard(code_lines=["..."], title="config.conf", width=5.5)
    -> Polished code terminal window with traffic-light header dots.
  * MetricBadge(label="RTT", value="12ms", status="good")
    -> Pill-shaped status badge.
  * ArrayGrid(values=[12, 24, 48, 96], active_index=1)
    -> Algorithm array with highlighted cell box.
  * FormulaCard(steps=["252 = 105 * 2 + 42", "105 = 42 * 2 + 21", "42 = 21 * 2 + 0"], title="Euclidean GCD", highlight_step=1)
    -> Step-by-step mathematical calculation box with term highlighting.
  * KeyBadge(key_type="PUBLIC KEY", name="id_ed25519.pub", is_private=False)
    -> Cryptographic public/private key badge.

CINEMATIC AESTHETICS & DESIGN TOKENS:
  * Background canvas: Use deep obsidian dark theme (`config.background_color = "#0B0F19"`).
  * Color harmony palette:
    - Primary Accent (Cyan): "#00F0FF" or BLUE_C
    - Highlight / Packets (Amber): "#FFB703" or YELLOW_C
    - Math / Storage (Purple): "#A855F7" or PURPLE_B
    - Success / Verified (Emerald): "#10B981" or GREEN_B
    - Warning / Overload (Coral/Red): "#EF4444" or RED_B

  * Typography & Legibility Hierarchy:
    - Main Scene Title: font_size=22 to 26, weight=BOLD, color=WHITE.
    - Subtitles / Category Tags: font_size=13 to 14, weight=BOLD, color=CYAN.
    - Section Headings / Card Titles: font_size=16 to 18, weight=BOLD, color=WHITE.
    - Body Labels / Metrics: font_size=12 to 14, weight=MEDIUM.
    - Subtitle / Narration Captions: Use CaptionDock(narration_text) for bottom caption bar.
    - Always use clean modern sans-serif fonts; never manually set serif fonts.

CANVAS & 4-SLOT LAYOUT CONTRACT:
  * 16:9 landscape, designed for 1920x1080 (Manim units ≈14.22 x 8).
  * 4 CANONICAL SLOTS:
    1. Title Band: y in [3.1, 3.8] -> Use title.to_edge(UP, buff=0.35).
    2. Hero Stage: y in [-1.6, 2.8] -> Place your FlowStage, SplitStage, or HeroFocusStage here.
    3. Caption Buffer: y in [-3.8, -2.6] -> Dedicated subtitle area (e.g. DOWN * 3.15).
  * TEXT & CAPTION TRANSITIONS:
    - NEVER use Transform(text_a, text_b) on sentences or different text! In Manim, transforming different text morphs letter outlines and causes letters to explode and scatter across the screen.
    - ALWAYS use FadeOut(caption, shift=UP*0.1) and FadeIn(new_caption, shift=UP*0.1) or ReplacementTransform for caption updates.
    - For EQUATION morphing between related formulas: use TransformMatchingTex(eq1, eq2, run_time=1.2) — this correctly matches like terms.
    - REDUNDANCY PRINCIPLE: Do NOT put giant multi-line narration paragraphs on screen — subtitles are already handled. Use concise callout cards, step labels, and mathematical/anatomical terms.
  * OBJECT PERSISTENCE: Do NOT wipe the screen (FadeOut all) between sentences. Keep persistent diagrams alive and update their state cleanly.

ANIMATION VOCABULARY — match the animation type to the semantic event:

  FIRST APPEARANCE (elements drawing themselves onto the screen):
    - Geometric shape:     Create(shape, run_time=0.8)
    - Text/label:          Write(text, run_time=0.8)
    - Data flow in:        FadeIn(mob, shift=UP*0.3, run_time=0.5)
    - Border then fill:    DrawBorderThenFill(shape, run_time=1.0)

  STATE CHANGE / VALUE UPDATE (element already on screen changes):
    - Highlight a cell:    Indicate(cell, scale_factor=1.3, run_time=0.4,
                               rate_func=rate_functions.there_and_back)
    - Cell value changes:  cell.animate.become(new_cell)  (after Indicate)
    - Equation transform:  TransformMatchingTex(eq1, eq2, run_time=1.2)
    - Surround/focus:      Circumscribe(node, color=YELLOW, run_time=0.6)

  PHYSICAL MOTION (elements moving across the canvas):
    - Element slides:      mob.animate.move_to(target, run_time=0.5)
    - Swap two elements:   AnimationGroup(
                               a.animate.move_to(b_pos),
                               b.animate.move_to(a_pos),
                               run_time=0.6, rate_func=rate_functions.smooth)
    - Path traversal:      MoveAlongPath(dot, path, run_time=1.0,
                               rate_func=rate_functions.ease_in_out_sine)
    - Sequential reveal:   AnimationGroup(*anims, lag_ratio=0.15)

  EMPHASIS / ATTENTION (guide viewer focus):
    - Spoken-term pulse:   Indicate(mob, run_time=0.3,
                               rate_func=rate_functions.there_and_back)
    - Final answer:        Flash(mob, color=GREEN, run_time=0.8)
    - Error/wrong state:   Wiggle(mob, run_time=0.5)
    - Camera zoom-in:      focus_on(self.camera.frame, hero, scale=0.6)

  DISMISSAL (use sparingly — prefer keeping elements on screen):
    - Remove a group:      FadeOut(group, shift=LEFT*0.5, run_time=0.4)
    - Caption update:      FadeOut(cap, run_time=0.2) then FadeIn(new_cap, run_time=0.2)

  EASING CURVES (choose the right feel for each motion type):
    rate_functions.smooth           -> default, all-purpose S-curve
    rate_functions.ease_in_out_sine -> physical element motion (swaps, slides)
    rate_functions.there_and_back   -> pulse/blink highlights (Indicate)
    rate_functions.rush_into        -> snap attention to an urgent element
    rate_functions.ease_out_bounce  -> element "landing" at its destination
    lag_ratio=0.15 in AnimationGroup -> staggered sequential reveal

STRICT ZERO-OVERLAP COLLISION RULES (MANDATORY):
  1. NEVER PLACE TRAVELING PACKETS/TEXT INSIDE SERVER/LAPTOP BOXES:
     - Packets (`Dot`, `Text`, `Badge`) must travel along wires or ABOVE boxes:
       Use `dot, target = stage.pulse_signal(src, dst)` or `node.get_top() + UP * 0.4`.
     - NEVER use `move_to(node.get_center())` for a moving packet — this collides with the node's title label!
  2. DYNAMIC AUTO-LAYOUT CONTAINERS (PREVENT OVERLAPS):
     - For vertical stacks of labels, code cards, or notes, prefer `AutoVStack(title, body, note, buff=0.3)`.
     - For horizontal card rows or metric sequences, prefer `AutoHStack(card1, card2, card3, buff=0.4)`.
     - For packaged items, use `AnnotatedCard(title="Node", body=..., badge_text="ACTIVE")`.
     - Do NOT use multiple parallel `item.next_to(anchor, DOWN)` statements on the same anchor. Chain them:
       `item2.next_to(item1, DOWN, buff=0.25)` or wrap in `VGroup(item1, item2).arrange(DOWN, buff=0.25)`.
  3. SAFE CAPTION ZONE (BOTTOM MARGIN):
     - Keep all general visual elements at y >= -2.4. Subtitles occupy y in [-3.8, -2.6].
     - Never place visual components at DOWN * 3 or y < -2.5.

TIMING & CHOREOGRAPHY:
  * Synchronize self.play() and self.wait() with the sentence timestamps provided.
  * Total scene duration must match the narration timeline.
  * Finish in the state described by the narration.

COGNITIVE ATTENTION SIGNALING (MAYER-SWELLER PRINCIPLES):
  * When key technical terms or entities are vocalized in narration, guide learner visual attention by highlighting the corresponding on-screen Mobject.
  * Use self.play(Indicate(mobject)) or self.play(Circumscribe(mobject, color=YELLOW)) synchronized with the spoken term (~150ms lead time).
  * REDUNDANCY PRINCIPLE: Never duplicate verbatim narration sentences in on-screen Text cards. Keep on-screen text to concise labels, data values, code snippets, or formulas. Full text cards overload the learner's phonological loop.

CINEMATIC CHOREOGRAPHY & NEURO-SYMBOLIC TOOLS:
  * For zooming into hero components or camera frame control, inherit from MovingCameraScene:
    - class SceneXX(MovingCameraScene):
    - Use self.play(focus_on(self.camera.frame, target, scale=0.6)) to guide the learner's focus into details.
    - Use self.play(reset_frame(self.camera.frame)) to restore the full overview.
    - Use GlowAura(target, color=YELLOW) to give key active elements a soft glowing presence.
    - Use HeroMetricBadge("COMPLEXITY", "O(log n)") for clean dashboard-style metric badges.
  * For algorithms and math, use deterministic solvers:
    - trace_sorting(arr, "bubble"), trace_binary_search(arr, target), trace_euclid_gcd(a, b)
    - compute_tree_layout(nodes, edges, root) to guarantee 100% collision-free hierarchical coordinates!
"""


def heal_manim_source(code: str) -> str:
    """Auto-heal common LLM syntax/API quirks in generated Manim Python code.
    
    Transforms common hallucinations like .lighten(0.2), .darken(0.2), undefined
    color names (CYAN, AMBER), deprecated Code() kwargs, and missing widget imports
    to valid Manim constructs without wasting an LLM round-trip.
    """
    import re

    # Auto-inject mobjects import if component widgets are referenced
    mobject_names = [
        "FlowStage",
        "SplitStage",
        "HeroFocusStage",
        "BenchmarkStage",
        "AutoVStack",
        "AutoHStack",
        "SafeCaptionZone",
        "CaptionDock",
        "AnnotatedCard",
        "ServerNode",
        "ClientCluster",
        "DatabaseNode",
        "ConfigCodeCard",
        "MetricBadge",
        "ArrayGrid",
        "FormulaCard",
        "KeyBadge",
        "MemoryBankMobject",
        "BinaryTreeMobject",
        "CoordinateGridMobject",
        "MediaCard",
        "NeuralNetworkMobject3D",
        "StackMobject",
        "QueueMobject",
        "AnimatedCurveMobject",
    ]
    used_mobjects = [name for name in mobject_names if re.search(r'\b' + name + r'\b', code)]
    if used_mobjects and "prompt2render.assets.mobjects" not in code:
        import_stmt = f"from prompt2render.assets.mobjects import {', '.join(used_mobjects)}\n"
        code = import_stmt + code

    # Auto-inject cinematic camera helpers if referenced
    cinematic_names = [
        "focus_on",
        "pan_to",
        "reset_frame",
        "subtle_drift",
        "GlowAura",
        "HeroMetricBadge",
        "orbit_3d_camera",
        "cinematic_3d_pitch_yaw",
        "create_3d_grid_plane",
    ]
    used_cinematic = [name for name in cinematic_names if re.search(r'\b' + name + r'\b', code)]
    if used_cinematic and "prompt2render.cinematic" not in code:
        import_stmt = f"from prompt2render.cinematic import {', '.join(used_cinematic)}\n"
        code = import_stmt + code

    # Auto-inject symbolic engine solvers if referenced
    symbolic_names = [
        "trace_sorting",
        "trace_binary_search",
        "trace_euclid_gcd",
        "compute_tree_layout",
        "trace_bst_insertion",
        "derive_calculus_step",
        "solve_equation_step",
    ]
    used_symbolic = [name for name in symbolic_names if re.search(r'\b' + name + r'\b', code)]
    if used_symbolic and "prompt2render.symbolic_engine" not in code:
        import_stmt = f"from prompt2render.symbolic_engine import {', '.join(used_symbolic)}\n"
        code = import_stmt + code

    # Inject common position/color constants if referenced as bare names
    aliases = {
        "CYAN": '"#00FFFF"',
        "MAGENTA": '"#FF00FF"',
        "AMBER": '"#FFBF00"',
        "LIME": '"#00FF00"',
        "VIOLET": '"#8A2BE2"',
        "INDIGO": '"#4B0082"',
        "CENTER": "ORIGIN",
    }
    for alias, val in aliases.items():
        if re.search(r'\b' + alias + r'\b', code) and not re.search(r'\b' + alias + r'\s*=', code):
            code = f"{alias} = {val}\n" + code

    # Strip .lighten(...) / .darken(...) method chains on Mobjects
    code = re.sub(r'\.(?:lighten|darken)\s*\([^)]*\)', '', code)
    # Strip .glow() / .pulse() / .resize() method chains
    code = re.sub(r'\.(?:glow|pulse|resize)\s*\([^)]*\)', '', code)
    # Strip .set_color_by_gradient(...) method chains
    code = re.sub(r'\.set_color_by_gradient\s*\([^)]*\)', '', code)
    # Fix Code(code=...) -> Code(code_string=...)
    code = re.sub(r'\bCode\(\s*code=', 'Code(code_string=', code)
    # Fix Code(..., insert_line_numbers=...) -> Code(..., add_line_numbers=...)
    code = re.sub(r'\binsert_line_numbers=', 'add_line_numbers=', code)
    # Strip invalid kwargs in Text(...)
    code = re.sub(r',?\s*alignment=[^,)]+', '', code)
    code = re.sub(r',?\s*include_background=[^,)]+', '', code)
    code = re.sub(r',?\s*word_wrap_width=[^,)]+', '', code)
    # Strip invalid or complex t2c mappings in Text(...) to prevent Manim regex crashes
    code = re.sub(r',?\s*t2c\s*=\s*\{[^}]*\}', '', code)
    # Heal Circle highlighting text -> SurroundingRectangle
    code = re.sub(
        r'Circle\s*\([^)]*?\)\.move_to\(\s*([a-zA-Z0-9_]+)\.get_center\(\)\s*\)',
        r'SurroundingRectangle(\1, color=YELLOW, buff=0.15, corner_radius=0.1)',
        code,
    )
    # Auto-wrap coordinate-returning lambda calls inside always_redraw into Dot() Mobjects
    def _fix_always_redraw_coords(m):
        inner = m.group(1).strip()
        if any(kw in inner for kw in ("c2p(", "coords_to_point(", "get_center(", "get_top(", "get_bottom(", "get_left(", "get_right(")):
            if not inner.startswith(("Dot(", "Line(", "Arrow(", "Text(", "MathTex(", "Tex(", "Circle(", "Square(", "Rectangle(", "VGroup(", "Polygon(")):
                return f"always_redraw(lambda: Dot({inner}))"
        return m.group(0)

    code = re.sub(r'always_redraw\(\s*lambda\s*:\s*([^\n\r]+?)\s*\)', _fix_always_redraw_coords, code)
    # Fix move_to(..., corner=...) -> remove corner parameter
    code = re.sub(r',?\s*corner=[^,)]+', '', code)

    # 1. SPATIAL AUTO-LAYOUT GUARD: Clamp long Text and MathTex width to prevent horizontal overflow (> 12.5 width)
    # If a Text instantiation has a literal string longer than 45 chars and doesn't scale_to_fit_width, clamp it
    def _clamp_wide_text(m):
        txt_call = m.group(0)
        content = m.group(1)
        if len(content) > 42 and "scale_to_fit_width" not in txt_call:
            return f"{txt_call}.scale_to_fit_width(12.0)"
        return txt_call

    code = re.sub(r'Text\s*\(\s*([\'"][^\'"]{43,}[\'"])[^)]*\)', _clamp_wide_text, code)

    # 2. SPATIAL AUTO-LAYOUT GUARD: Clamp non-caption elements from moving into bottom caption zone (y < -2.5)
    def _clamp_caption_trespass(m):
        var_name = m.group(1)
        x_val_str = m.group(2).strip()
        y_val_str = m.group(3).strip()
        try:
            y_val = float(y_val_str)
            if "caption" not in var_name.lower() and "sub" not in var_name.lower() and y_val < -2.5:
                # Clamp safely above caption band to y = -2.2
                return f"{var_name}.move_to(({x_val_str}, -2.2, 0))"
        except Exception:
            pass
        return m.group(0)

    code = re.sub(r'(\b\w+)\.move_to\(\s*\(\s*([^,]+?)\s*,\s*(-[2-9](?:\.\d+)?)\s*(?:,\s*[^)]*)?\)\s*\)', _clamp_caption_trespass, code)

    # 3. SPATIAL AUTO-LAYOUT GUARD: Fix duplicate sibling anchoring collision
    # If two consecutive lines anchor different targets to the SAME anchor with next_to(anchor, DOWN, buff=X)
    # e.g.:
    #   item1.next_to(box, DOWN, buff=0.2)
    #   item2.next_to(box, DOWN, buff=0.4) -> re-anchor item2.next_to(item1, DOWN, buff=0.25)
    def _fix_parallel_down_anchoring(source: str) -> str:
        lines = source.splitlines()
        anchors_seen: dict[str, str] = {} # anchor_name -> last_placed_child
        new_lines = []
        pattern = re.compile(r'^\s*([a-zA-Z0-9_]+)\.next_to\(\s*([a-zA-Z0-9_]+)\s*,\s*DOWN\b([^)]*)\)')
        for line in lines:
            m = pattern.search(line)
            if m:
                child = m.group(1)
                anchor = m.group(2)
                extra_args = m.group(3)
                if anchor in anchors_seen:
                    # Parallel placement detected! Chain to the previous child instead
                    prev_child = anchors_seen[anchor]
                    if prev_child != child:
                        indent = line[:len(line) - len(line.lstrip())]
                        line = f"{indent}{child}.next_to({prev_child}, DOWN, buff=0.3)"
                anchors_seen[anchor] = child
            new_lines.append(line)
        return "\n".join(new_lines)

    code = _fix_parallel_down_anchoring(code)

    # Heal ImageMobject paths so Manim can find staged assets regardless of working directory
    from pathlib import Path
    def _fix_image_path(m):
        raw_path = m.group(1).strip("'\"")
        p = Path(raw_path)
        if not p.is_file():
            # Search project trees for this asset file
            candidates = list(Path("projects").glob(f"*/build/assets/{p.name}"))
            if not candidates:
                candidates = list(Path("projects").glob(f"*/assets/{p.name}"))
            if candidates:
                resolved = candidates[0].resolve().as_posix()
                return f"ImageMobject('{resolved}')"
        return m.group(0)

    # 5. CAMERA SCENE PROMOTION: Auto-promote Scene -> MovingCameraScene if camera.frame or zoom helpers are used
    if re.search(r'\b(?:camera\.frame|focus_on|reset_frame)\b', code):
        if not re.search(r'\bThreeDScene\b', code):
            code = re.sub(r'\bclass\s+([A-Za-z0-9_]+)\s*\(\s*Scene\s*\)\s*:', r'class \1(MovingCameraScene):', code)

    # 6. LATEX MATH NORMALIZATION: Translate raw Unicode math & Greek glyphs to LaTeX commands
    _UNICODE_LATEX_MAP = {
        "θ": r"\theta ", "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ",
        "δ": r"\delta ", "ε": r"\epsilon ", "λ": r"\lambda ", "μ": r"\mu ",
        "π": r"\pi ", "σ": r"\sigma ", "ω": r"\omega ", "Δ": r"\Delta ",
        "Σ": r"\Sigma ", "Ω": r"\Omega ", "≤": r"\le ", "≥": r"\ge ",
        "≠": r"\ne ", "×": r"\times ", "÷": r"\div ", "→": r"\to ",
        "←": r"\leftarrow ", "⇒": r"\Rightarrow ", "⇔": r"\Leftrightarrow ",
        "∞": r"\infty ", "≈": r"\approx ", "±": r"\pm ", "∈": r"\in ",
        "∉": r"\notin ", "⊂": r"\subset ", "⊆": r"\subseteq ",
        "∪": r"\cup ", "∩": r"\cap ", "∀": r"\forall ", "∃": r"\exists ",
        "ℝ": r"\mathbb{R}", "ℤ": r"\mathbb{Z}", "ℕ": r"\mathbb{N}", "ℂ": r"\mathbb{C}",
    }

    def _fix_latex_unicode(m):
        prefix = m.group(1)
        quote = m.group(2)
        content = m.group(3)
        for uchar, repl in _UNICODE_LATEX_MAP.items():
            if uchar in content:
                content = content.replace(uchar, repl)
        return f"{prefix}{quote}{content}{quote}"

    code = re.sub(
        r'(\b(?:MathTex|Tex)\s*\(\s*r?)([\'"]{1,3})(.*?)([\'"]{1,3})',
        _fix_latex_unicode,
        code,
        flags=re.DOTALL,
    )

    return code



def _extract_semantic_scene_summary(code: str) -> str:
    """Extract a compact semantic summary of previous scene objects to reduce tokens by 70%."""
    import re
    mobjects = set(re.findall(r'(\b\w+)\s*=\s*(?:Text|MathTex|Tex|VGroup|Line|Arrow|Circle|Square|Rectangle|Dot|Axes|Table)\(', code))
    anchors = re.findall(r'(\b\w+)\.move_to\(([^)]+)\)', code)
    summary_lines = []
    if mobjects:
        summary_lines.append(f"- Defined Mobjects: {', '.join(sorted(list(mobjects))[:15])}")
    if anchors:
        summary_lines.append(f"- Coordinate Anchors: {'; '.join([f'{a[0]} at {a[1].strip()}' for a in anchors[:6]])}")
    return "\n".join(summary_lines) if summary_lines else "None."


def is_manim_renderer(rend: str) -> bool:
    """Return whether the renderer uses the Manim execution and assembly pipeline."""
    return rend in {"manim", "manim_3d", "split"}


def select_renderer(sec) -> str:
    """Select the renderer from explicit section tags, env var, or brief."""
    # Check media_type on section if set
    media_type = getattr(sec, "media_type", "auto")
    if media_type and media_type != "auto":
        media_type = media_type.strip().lower()
        if media_type in {"manim", "matplotlib", "manim_3d", "video", "split"}:
            return media_type

    explicit = getattr(sec, "renderer", None)
    if isinstance(explicit, str):
        explicit = explicit.strip().lower()
        if explicit in {"manim", "matplotlib", "manim_3d", "video", "split"}:
            return explicit

    # Env override takes priority if set
    env_default = (os.environ.get("P2R_RENDERER") or os.environ.get("P2R_DEFAULT_RENDERER", "")).strip().lower()
    if env_default in {"manim", "matplotlib"}:
        return env_default

    brief = str(getattr(sec, "anim", "") or "").lower()

    # Explicit tags in the animation brief
    if "[matplotlib]" in brief or "[scenekit]" in brief:
        return "matplotlib"
    if "[3d]" in brief or "[manim_3d]" in brief:
        return "manim_3d"
    if "[video" in brief or "[broll" in brief:
        return "video"
    if "[split]" in brief:
        return "split"
    if "[manim]" in brief:
        return "manim"

    # In --manim mode / when P2R_MANIM_VERSION is declared, default to Manim
    if os.environ.get("P2R_MANIM_VERSION") or os.environ.get("P2R_MANIM"):
        return "manim"

    # Auto-route motion-heavy topics to Manim when P2R_MOTION_ROUTING is not disabled
    if os.environ.get("P2R_MOTION_ROUTING", "1").strip().lower() not in ("0", "false", "off", "no"):
        try:
            from .topic_router import brief_suggests_motion
            if brief_suggests_motion(brief):
                cfg.say(f"section auto-routed to Manim (motion topic detected in brief)")
                return "manim"
        except Exception:
            pass

    return "matplotlib"


def build_manim_prompt(script: Script, sec, sents: list[dict],
                       previous_context: str = "", asset_hint: str = "",
                       trace_hint: str = "") -> str:
    numbered = "\n".join(
        f"  [{i}] t={s['start']:6.1f}s -> {s['end']:6.1f}s  {s['text']}"
        for i, s in enumerate(sents)
    )
    total = sents[-1]["end"] if sents else 0.0
    class_name = f"Scene{sec.stem}"
    rend = select_renderer(sec)
    is_3d = rend == "manim_3d" or "[3d]" in str(getattr(sec, "anim", "")).lower()
    base_class = "ThreeDScene" if is_3d else "Scene"
    extra_3d_doc = ""
    if is_3d:
        extra_3d_doc = textwrap.dedent(f"""
    3D ANIMATION & CAMERA SPECIFICATION (ThreeDScene):
      * The class MUST inherit from ThreeDScene:
            class {class_name}(ThreeDScene):
      * In construct(self), establish the initial 3D camera orientation:
            self.set_camera_orientation(phi=75 * DEGREES, theta=-45 * DEGREES)
      * Use 3D mathematical and geometric primitives:
            ThreeDAxes(x_range=[-4, 4], y_range=[-4, 4], z_range=[-3, 3])
            Surface(lambda u, v: np.array([u, v, f(u, v)]), u_range=[-2, 2], v_range=[-2, 2])
            Sphere(radius=0.8), Cylinder(), Cube(side_length=1.5), Dot3D(point=[1, 2, 0]), Arrow3D()
            NeuralNetworkMobject3D(layer_sizes=[...])
      * Camera moves and orbits:
            orbit_3d_camera(self, delta_theta=60, run_time=3.0)
            cinematic_3d_pitch_yaw(self, phi=70, theta=-45, zoom=1.1, run_time=2.0)
            create_3d_grid_plane(size=6.0, step=1.0)
      * On-screen 2D text, title cards, or metric badges that must NOT tilt with the 3D camera:
            self.add_fixed_in_frame_mobjects(title_group, metric_badge)
      * STABILITY CONTRACT: Never pass a scalar float where a 3D coordinate vector is required.
    """)

    manim_api_doc = MANIM_API_DOC_TEMPLATE.replace(
        "__MANIM_VERSION__", manimver.target_version()
    )

    return textwrap.dedent(f"""
    You are the senior Manim animation engineer for Prompt2Render.

    Generate ONE production-quality REAL MANIM SCENE for:
        "{script.title}"

    Audience:
        {script.meta.get('audience', 'undergraduates')}

    SECTION:
        {sec.index}: {sec.title}

    ANIMATION BRIEF:
        {sec.anim}

    PREVIOUS SECTION ANCHORS:
        {previous_context}

    {asset_hint}

    {trace_hint}

    NARRATION TIMELINE:
        Total duration: {total:.2f} seconds

    {numbered}

    {manim_api_doc}
    {extra_3d_doc}

    OUTPUT CONTRACT:
      * Output ONLY complete Python source.
      * Start with: from manim import *
      * Define exactly one main class named {class_name}.
      * It MUST inherit from {base_class} and implement construct(self).
      * Do NOT define states().
      * Do NOT use Scenekit k.* primitives.
      * Do NOT use Matplotlib.
      * The file must render directly with:
            manim -pqh scene_{sec.stem}.py {class_name}

    TIMING:
      * Map narration to an intentional visual timeline.
      * Use self.wait() for explanatory holds.
      * Use explicit run_time for important animations.
      * Keep visual event order aligned with narration.
      * Do not add unrelated animation just to fill time.

    SELF-CHECK:
      1. Every referenced object is defined.
      2. Every Manim API call is valid.
      3. Nothing important clips the frame.
      4. Labels remain attached to persistent objects.
      5. Important motion is staged rather than teleported.
      6. The final state matches the narration.
      7. The scene runs without manual editing.

    Return ONLY Python source.
    """).strip()


def _render_manim(proj: Path, src: Path, section_dir: Path,
                  class_name: str, quality: str | None = None,
                  timeout: int | None = None) -> list[Path]:
    """Render a real Manim scene through the installed Manim CLI."""
    import subprocess

    target, installed, matches = manimver.status()
    if not matches:
        sys.exit(
            f"[prompt2render] Manim version mismatch: installed "
            f"{installed or 'none'}, but this build targets {target}. "
            f"Run: pip install \"manim=={target}\" (or set "
            f"P2R_MANIM_VERSION={installed} to declare that version "
            "intentionally)."
        )

    section_dir.mkdir(parents=True, exist_ok=True)
    media_dir = section_dir / "_manim_media"
    media_dir.mkdir(parents=True, exist_ok=True)

    if quality is None:
        quality = os.environ.get("P2R_MANIM_QUALITY", "-qh")
    if quality not in {"-ql", "-qm", "-qh", "-qp"}:
        quality = "-qh"

    if timeout is None:
        timeout = int(os.environ.get("P2R_MANIM_TIMEOUT", "600"))

    cmd = [
        sys.executable,
        "-m",
        "manim",
        quality,
        "-r",
        f"{cfg.WIDTH},{cfg.HEIGHT}",
        "--disable_caching",
        "--media_dir",
        str(media_dir.resolve()),
        str(src.resolve()),
        class_name,
    ]

    repo_root = str(Path(__file__).parent.parent.resolve())
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    pypath = f"{repo_root}{os.pathsep}{current_pythonpath}" if current_pythonpath else repo_root
    env = cfg.safe_subprocess_env({"PYTHONPATH": pypath})

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(proj.resolve()),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"Manim render timed out after {timeout}s"
        )
    except FileNotFoundError:
        raise SystemExit(
            "Manim backend selected but `python -m manim` is unavailable"
        )

    if proc.returncode != 0:
        output = "\n".join(
            (proc.stdout + "\n" + proc.stderr).splitlines()[-100:]
        )
        raise SystemExit("Manim render failed:\n" + output)

    search_dirs = [
        media_dir,
        proj / "media",
        Path("media"),
        section_dir,
    ]
    videos: list[Path] = []
    for d in search_dirs:
        if d.exists():
            videos.extend([
                p for p in d.rglob(f"*{class_name}*.mp4") 
                if "partial_movie_files" not in str(p)
            ])

    if not videos:
        for d in search_dirs:
            if d.exists():
                videos.extend([
                    p for p in d.rglob("*.mp4") 
                    if "partial_movie_files" not in str(p)
                ])

    if not videos:
        raise SystemExit(f"Manim completed without producing an MP4 for {class_name}")

    videos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    target = section_dir / f"{src.stem}.mp4"
    shutil.copy2(videos[0], target)

    return sorted(media_dir.rglob("*.png"))


def render_manim_parallel(
    proj: Path,
    script: Script,
    quality: str = "-qh",
    max_workers: int | None = None,
) -> dict[str, Path]:
    """Render all Manim scenes concurrently across multi-core worker processes.
    
    Uses Cairo by default for rock-solid stability. If P2R_MANIM_OPENGL=1 is set,
    attempts experimental OpenGL rendering with automatic fallback to Cairo.
    """
    import concurrent.futures

    outdir = proj / "build" / "scenes"
    manim_dir = proj / "build" / "manim"
    sections = [s for s in script.sections if is_manim_renderer(select_renderer(s))]
    if not sections:
        return {}

    workers = max_workers or min(len(sections), (os.cpu_count() or 4))
    cfg.say(f"Rendering {len(sections)} Manim scenes in parallel ({workers} worker threads)...")

    results: dict[str, Path] = {}

    def _render_worker(sec) -> tuple[str, Path]:
        src = outdir / f"scene_{sec.stem}.py"
        if not src.exists() and (manim_dir / f"scene_{sec.stem}.py").exists():
            src = manim_dir / f"scene_{sec.stem}.py"
        if not src.exists():
            for cand in [proj / "scenes" / f"{sec.stem}.py", proj / "scenes" / f"scene_{sec.stem}.py"]:
                if cand.exists():
                    src = cand
                    break

        section_dir = outdir / sec.stem
        mp4_path = section_dir / f"scene_{sec.stem}.mp4"
        sec_cand = proj / "sections" / f"{sec.stem}.mp4"

        if mp4_path.exists() and mp4_path.stat().st_size > 1024:
            return sec.stem, mp4_path
        if sec_cand.exists() and sec_cand.stat().st_size > 1024:
            return sec.stem, sec_cand

        if src.exists():
            code = src.read_text(encoding="utf-8")
            healed = heal_manim_source(code)
            if healed != code:
                src.write_text(healed, encoding="utf-8")

        _render_manim(proj, src, section_dir, f"Scene{sec.stem}", quality=quality)
        return sec.stem, mp4_path

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_render_worker, sec): sec for sec in sections}
        for fut in concurrent.futures.as_completed(futures):
            sec = futures[fut]
            try:
                stem, mp4_path = fut.result()
                results[stem] = mp4_path
                cfg.say(f"Section {stem}: parallel render completed ({mp4_path.name})")
            except Exception as exc:
                sys.exit(f"[prompt2render] Parallel render failed on section {sec.stem}: {exc}")

    return results


def _generate_manim(proj: Path, script: Script, index: int,
                    retries: int = 0, extra_feedback: str = "",
                    dst: Path | None = None,
                    model_env: str | None = None) -> Path:
    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")

    data = align.load(proj, sec.stem)
    sents = data["sentences"]
    if not sents:
        sys.exit(
            f"[prompt2render] section {sec.stem} has no alignment — "
            "run `prompt2render align`"
        )

    outdir = proj / "build" / "scenes"
    outdir.mkdir(parents=True, exist_ok=True)
    # See _generate_matplotlib: `outdir` remains the canonical accepted
    # directory (previous-section continuity is read from it) even when the
    # new module is written to a sidecar candidate path.
    if dst is None:
        dst = outdir / f"scene_{sec.stem}.py"
    else:
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)

    section_dir = outdir / sec.stem

    previous_context = ""
    if index > 1:
        prev_sec = next(
            (s for s in script.sections if s.index == index - 1),
            None,
        )
        if prev_sec:
            prev_dst = outdir / f"scene_{prev_sec.stem}.py"
            if prev_dst.exists():
                summary = _extract_semantic_scene_summary(prev_dst.read_text(encoding='utf-8'))
                previous_context = (
                    "Previous Manim scene anchors for continuity (preserve scale/visual identity):\n"
                    f"{summary}\n"
                )

    _, manim_hint = stage_external_assets_for_section(proj, sec)
    try:
        from .topic_trace import detect_and_trace as _detect_and_trace
        _trace_hint = _detect_and_trace(
            getattr(sec, "anim", "") or "",
            " ".join(s["text"] for s in sents),
        ) or ""
        if _trace_hint:
            cfg.say(f"section {sec.stem}: injecting pre-computed algorithm trace")
    except Exception:
        _trace_hint = ""
    prompt = build_manim_prompt(
        script, sec, sents, previous_context=previous_context,
        asset_hint=manim_hint, trace_hint=_trace_hint,
    )
    feedback = extra_feedback

    configured_cap = cfg.env_int("P2R_MAX_SCENE_ATTEMPTS", 0)
    max_attempts = (
        retries + 1
        if retries > 0
        else (configured_cap if configured_cap > 0 else None)
    )

    attempt = 1
    seen = set()

    while True:
        try:
            code = llm.complete(
                prompt + feedback,
                max_tokens=20000,
                label=(
                    f"Manim section {sec.stem} "
                    f"(attempt {attempt}/{max_attempts or 'until pass'})"
                ),
                **({"model_env": model_env} if model_env else {}),
            )
        except Exception as exc:
            cfg.say(f"Manim section {sec.stem}: transient connection error ({exc}) — retrying...")
            import time
            time.sleep(2)
            if max_attempts is not None and attempt >= max_attempts:
                sys.exit(
                    f"[prompt2render] Manim section {sec.stem}: "
                    f"LLM call failed — {exc}"
                )
            attempt += 1
            continue

        raw = strip_fences(code or "").strip()
        raw = heal_manim_source(raw)
        if not raw:
            sys.exit(
                f"[prompt2render] Manim section {sec.stem}: empty completion"
            )

        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        errors = validate_manim_source(raw)

        if digest in seen:
            errors.append(
                "model returned identical failed Manim source; "
                "change the scene structure"
            )
        seen.add(digest)

        if errors:
            cfg.say(
                f"Manim section {sec.stem}: rejected — {errors[0][:120]}"
            )
            # Try source-level nudge before paying for an LLM retry
            try:
                from .manim_nudge import nudge_source
                nudged, n_fixes = nudge_source(raw)
                if n_fixes > 0 and nudged != raw:
                    cfg.say(f"Manim section {sec.stem}: auto-nudged {n_fixes} layout issues — re-validating")
                    raw = nudged
                    errors = validate_manim_source(raw)
                    if not errors:
                        cfg.say(f"Manim section {sec.stem}: nudge resolved all errors — proceeding to render")
            except Exception as _nudge_err:
                cfg.warn(f"Manim section {sec.stem}: nudge skipped ({_nudge_err})")

        if errors:
            feedback = (
                "\n\nRETURN THE COMPLETE CORRECTED MANIM MODULE.\n"
                "Do not return a patch or explanation.\n\n"
                "VALIDATION ERRORS:\n  - "
                + "\n  - ".join(errors)
                + "\n\n"
                "REAL MANIM Scene/construct() ONLY. "
                "No states(), no k.* primitives, no Matplotlib.\n"
            )
            if max_attempts is None or attempt < max_attempts:
                attempt += 1
                continue
            sys.exit(
                f"[prompt2render] Manim section {sec.stem}: "
                f"failed after {attempt} attempts — "
                + "; ".join(errors)
            )

        # Apply deterministic timing correction to prevent LLM temporal drift
        try:
            from . import timing_corrector
            total_dur = sents[-1]["end"] if sents else 0.0
            raw = timing_corrector.correct_manim_timing(raw, sents, total_dur)
        except Exception:
            pass

        dst.write_text(raw, encoding="utf-8")

        try:
            with _RENDER_LOCK:
                verify_q = os.environ.get("P2R_MANIM_VERIFY_QUALITY", "-ql")
                frames = _render_manim(
                    proj,
                    dst,
                    section_dir,
                    f"Scene{sec.stem}",
                    quality=verify_q,
                    timeout=360,
                )
        except SystemExit as exc:
            err = str(exc)
            cfg.say(
                f"Manim section {sec.stem}: render rejected — {err[:120]}"
            )
            # Try source-level nudge on overlap errors before LLM retry
            re_render_ok = False
            if any(kw in err.lower() for kw in ("overlap", "collision", "next_to", "same y")):
                try:
                    from .manim_nudge import nudge_source
                    nudged, n_fixes = nudge_source(dst.read_text(encoding="utf-8"))
                    if n_fixes > 0:
                        cfg.say(f"Manim section {sec.stem}: nudge applied {n_fixes} fixes to overlap error — re-testing render")
                        dst.write_text(nudged, encoding="utf-8")
                        with _RENDER_LOCK:
                            verify_q = os.environ.get("P2R_MANIM_VERIFY_QUALITY", "-ql")
                            frames = _render_manim(
                                proj,
                                dst,
                                section_dir,
                                f"Scene{sec.stem}",
                                quality=verify_q,
                                timeout=360,
                            )
                        re_render_ok = True
                except Exception:
                    pass
            if re_render_ok:
                cfg.say(f"Manim section {sec.stem}: nudge re-render passed — {len(frames)} rendered frames")
                return dst

            feedback = (
                "\n\nRETURN THE COMPLETE CORRECTED MANIM MODULE.\n\n"
                "RUNTIME/RENDER FAILURE:\n"
                + err
                + "\n\n"
                "Fix the actual Manim API, geometry, timing or runtime "
                "problem. Preserve the educational intent.\n"
            )
            if max_attempts is None or attempt < max_attempts:
                attempt += 1
                continue
            sys.exit(
                f"[prompt2render] Manim section {sec.stem}: "
                f"render failed after {attempt} attempts — {err}"
            )

        cfg.say(
            f"Manim section {sec.stem}: accepted — "
            f"{len(frames)} rendered frames"
        )
        return dst


def generate(proj: Path, script: Script, index: int, retries: int = 0,
             extra_feedback: str = "", dst: Path | None = None,
             model_env: str | None = None) -> Path:
    """Unified dual-renderer entry point.

    Selection:
      [MANIM]       -> true Manim Scene/construct()
      [MATPLOTLIB]  -> existing Scenekit/Matplotlib backend
      [AUTO]        -> semantic routing

    Global override:
      P2R_RENDERER=manim
      P2R_RENDERER=matplotlib
      P2R_RENDERER=auto

    ``dst`` redirects the generated module to a specific path instead of the
    canonical ``build/scenes/scene_<stem>.py``. The harness uses it to write
    repair candidates into a sidecar workspace so the currently-accepted
    scene is never overwritten by an unproven regeneration. ``None`` (the
    default) preserves the historical behaviour exactly.
    """
    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")

    configured = os.environ.get("P2R_RENDERER", "auto").strip().lower()
    renderer = (
        configured
        if configured in {"manim", "matplotlib"}
        else select_renderer(sec)
    )

    cfg.say(f"section {sec.stem}: renderer={renderer.upper()}")

    if is_manim_renderer(renderer):
        return _generate_manim(
            proj, script, index,
            retries=retries,
            extra_feedback=extra_feedback,
            dst=dst,
            model_env=model_env,
        )

    if renderer == "video":
        target = dst or stills.scene_path(proj, sec.stem)
        cfg.say(f"section {sec.stem}: video/b-roll media section, skipping code generation")
        return target

    return _generate_matplotlib(
        proj, script, index,
        retries=retries,
        extra_feedback=extra_feedback,
        dst=dst,
        model_env=model_env,
    )


def _generate_matplotlib(proj: Path, script: Script, index: int, retries: int = 0,
            extra_feedback: str = "", dst: Path | None = None,
            model_env: str | None = None) -> Path:
    sec = next((s for s in script.sections if s.index == index), None)
    if sec is None:
        sys.exit(f"[prompt2render] no section {index} in script.md")

    data = align.load(proj, sec.stem)
    sents = data["sentences"]
    if not sents:
        sys.exit(f"[prompt2render] section {sec.stem} has no alignment — run `prompt2render align`")

    outdir = proj / "build" / "scenes"
    outdir.mkdir(parents=True, exist_ok=True)
    # `outdir` stays the canonical scenes directory even when writing a
    # candidate elsewhere: it is also where the *previous* section's
    # accepted code is read from for layout continuity below, which must
    # keep pointing at accepted work.
    if dst is None:
        dst = outdir / f"scene_{sec.stem}.py"
    else:
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)

    # State-Carrying Context: Find the previous section's generated code to anchor the layout
    previous_context = ""
    if index > 1:
        prev_sec = next((s for s in script.sections if s.index == index - 1), None)
        if prev_sec:
            prev_dst = outdir / f"scene_{prev_sec.stem}.py"
            if prev_dst.exists():
                prev_code = prev_dst.read_text(encoding="utf-8")
                # Extract the actual final state function, not the first state.
                # The previous implementation used re.search(), which always
                # selected s01 and made continuity misleading.
                matches = re.findall(
                    r"def s\d+\(ax(?:,[^)]*)?\):.*?(?=\n\s*def s\d+\(|\n\s*return\s+\[)",
                    prev_code, re.DOTALL)
                if matches:
                    last_state = matches[-1].strip()[:6000]
                    previous_context = (
                        "CONTINUITY CONTEXT:\n"
                        "To prevent jarring visual jumps, you MUST maintain the exact `x` and `y` coordinates "
                        "for any persistent data structures (like arrays, trees, or grids) that were used in the previous section. "
                        "Here is the code for the final visual state of the previous section for reference:\n"
                        f"```python\n{last_state}\n```\n"
                    )

    mat_hint, _ = stage_external_assets_for_section(proj, sec)
    try:
        from .topic_trace import detect_and_trace as _detect_and_trace
        _trace_hint = _detect_and_trace(
            getattr(sec, "anim", "") or "",
            " ".join(s["text"] for s in sents),
        ) or ""
        if _trace_hint:
            cfg.say(f"section {sec.stem}: injecting pre-computed algorithm trace (matplotlib)")
    except Exception:
        _trace_hint = ""
    prompt = build_prompt(script, sec, sents, previous_context=previous_context,
                          asset_hint=mat_hint, trace_hint=_trace_hint)
    # extra_feedback: repair_router's harness-level cycle (prompt2render/harness/plugins/repair_router)
    # seeds diagnostics from *its own* prior repair attempts here — separate from this loop's own
    # internal `feedback`, which is still exactly the same reject-and-retry text as before.
    feedback = extra_feedback

    # A positive retries value preserves the old explicit cap: retries + 1
    # calls. The new default (zero) continues until validation passes. Set
    # P2R_MAX_SCENE_ATTEMPTS to a positive value when an explicit cap is desired.
    configured_cap = cfg.env_int("P2R_MAX_SCENE_ATTEMPTS", 0)
    max_attempts = retries + 1 if retries > 0 else (configured_cap if configured_cap > 0 else None)
    attempt = 1
    total_attempt = 1
    seen_digests: set[str] = set()
    while True:
        try:
            code = llm.complete(
                prompt + feedback, 
                max_tokens=16000, 
                label=f"section {sec.stem} (attempt {attempt}/{max_attempts or 'until pass'})",
                **({"model_env": model_env} if model_env else {}),
            )
        except Exception as e:
            sys.exit(f"[prompt2render] section {sec.stem}: LLM call failed — {e}")
            
        code = code or ""
        if not code.strip():
            sys.exit(f"[prompt2render] section {sec.stem}: empty completion — "
                     "lower the state count or raise the token budget")
        
        # Never silently rewrite model output. Silent cue mutation can change the
        # intended timing and can turn several out-of-range states into duplicate
        # cues. Reject the source with all deterministic diagnostics so the next
        # model attempt can repair the actual defect.
        raw_code = strip_fences(code)
        digest = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
        preflight_errors = validate_scene_source(raw_code, max_cue=len(sents) - 1)
        if digest in seen_digests:
            preflight_errors.append("model returned identical scene source after a failed attempt; change the geometry or state structure")
        seen_digests.add(digest)
        if preflight_errors:
            err = "preflight validation failed:\n  " + "\n  ".join(preflight_errors)
            first = preflight_errors[0][:110]
            cfg.say(f"section {sec.stem}: rejected — {first}")
            feedback_msg = (
                "\n\nYour previous answer was rejected before rendering. Return the whole corrected module.\n\n"
                "PRE-FLIGHT PROBLEMS:\n  - " + "\n  - ".join(preflight_errors) + "\n"
            )
            if any("hanoi" in item for item in preflight_errors):
                feedback_msg += (
                    "\nCRITICAL FIX: k.hanoi accepts exactly three peg lists in bottom-to-top order. "
                    "Do not pass four pegs. If showing an invalid move, keep three pegs, physically "
                    "place the larger disk on the smaller one, and label the state ILLEGAL or INVALID.\n"
                )
            if any("cue" in item for item in preflight_errors):
                feedback_msg += (
                    f"\nCRITICAL FIX: use cue indices 0..{len(sents) - 1}, strictly increasing. "
                    "Do not add more states than available cue positions; use progressive reveal steps "
                    "inside a state instead.\n"
                )
            feedback = extra_feedback + feedback_msg
            if max_attempts is None or attempt < max_attempts:
                attempt += 1
                total_attempt += 1
                continue
            sys.exit(f"[prompt2render] section {sec.stem}: still failing after "
                     f"{total_attempt} total attempts — {err}")

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
            err = str(e)
            first = next((line.strip() for line in err.splitlines() if line.strip()), err[:110])[:110]
            cfg.say(f"section {sec.stem}: rejected — {first}")
            # A stack trace tells it the code crashed. An audit failure tells
            # it *where two things collided, in pixels*. Both go back verbatim.
            feedback_msg = "\n\nYour previous answer was rejected. Fix it and return the whole corrected module.\n\nPROBLEM:\n" + err
            if "cue indices must increase" in err:
                feedback_msg += "\n\nCRITICAL FIX: You emitted a cue index that was smaller than or equal to the previous state's cue index. Look at your `return [...]` list at the bottom. The second element of each tuple (the cue index) MUST strictly increase: e.g., 0, 2, 5, 8. Fix the numbers so they go up."
            elif "but the section only has sentences" in err:
                feedback_msg += f"\n\nCRITICAL FIX: You emitted a cue index that is too large. This section only has {len(sents)} sentences (indices 0 to {len(sents)-1}). You MUST NOT use a cue index larger than {len(sents)-1}."
            elif "overlaps" in err or "share space" in err or "different horizontal bands" in err or "layout audit failed" in err:
                feedback_msg += (
                    "\n\nCRITICAL FIX: This is a geometry failure, not a color or z-order problem. "
                    "Use one major visual per horizontal zone, move the complete visual to a free zone, "
                    "reduce its footprint while preserving readability, or split it into separate states. "
                    "Do not repeat the rejected coordinates. The 16x9 canvas must keep a visible gap "
                    "between every non-connector primitive.\n"
                )
                if "curves" in err:
                    feedback_msg += (
                        "\nCURVES-SPECIFIC FIX: k.curves is an opaque full plot panel. Do not draw any "
                        "k.label, k.badge, k.block, k.array, or other non-connector primitive inside "
                        "its x/y/w/h footprint. Remove the external annotation, place it in the caption "
                        "or a separate secondary-zone state, and keep the curves panel by itself.\n"
                    )
            elif "supports exactly three pegs" in err or "hanoi" in err:
                feedback_msg += (
                    "\n\nCRITICAL FIX: k.hanoi supports exactly three peg lists. Replace any four-peg "
                    "state with a three-peg state or compose a different multi-column visual from "
                    "generic primitives.\n"
                )
            elif "crowded" in err or "too many distinct visual elements" in err:
                feedback_msg += (
                    "\n\nCROWDING FIX: Your state has too many separate elements in a single frame (density ceiling is 8). "
                    "Split the diagram into 2-3 progressive reveal steps using `{\"steps\": 2}` or `{\"steps\": 3}`, "
                    "or split the crowded elements across separate sequential states.\n"
                )
                
            feedback = extra_feedback + feedback_msg
            # The rejected code already shows whether this section wants
            # progressive reveal (the {"steps": N} opts dict) — REVEAL_DOC's
            # ~280 tokens of explanation are dead weight on every retry that
            # doesn't use it, resent unchanged on top of the same API_DOC
            # every attempt already pays for.
            if "steps" not in code:
                prompt = build_prompt(script, sec, sents, include_reveal=False,
                                      previous_context=previous_context)

            if max_attempts is None or attempt < max_attempts:
                attempt += 1
                total_attempt += 1
                continue

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
                 retries: int = 0, jobs: int | None = None) -> None:
    todo = []
    for sec in script.sections:
        if index is not None and sec.index != index:
            continue
        dst = stills.scene_path(proj, sec.stem)
        alt_dst = proj / "scenes" / f"{sec.stem}.py"
        rend = select_renderer(sec)
        if rend == "video":
            cfg.say(f"section {sec.stem}: video/b-roll media section, skipping code generation")
            continue
        if is_manim_renderer(rend):
            if dst.exists():
                cfg.say(f"section {sec.stem}: Manim scene already written, skipping (delete it to regenerate)")
                continue
            elif alt_dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copyfile(alt_dst, dst)
                cfg.say(f"section {sec.stem}: using pre-authored scene from {alt_dst}")
                continue
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
    continuity = os.environ.get("P2R_CONTINUITY", "1").strip().lower() not in {"0", "false", "off", "no"}
    # Previous-section context is a dependency, so concurrent generation would
    # race: section N may be generated before N-1 has an accepted scene. Keep
    # the reliable default serial; opt out explicitly for independent sections.
    if continuity:
        n = 1
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