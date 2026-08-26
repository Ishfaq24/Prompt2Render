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


def build_prompt(script: Script, sec, sents: list[dict],
                 include_reveal: bool = True, previous_context: str = "") -> str:
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


def strip_fences(code: str) -> str:
    code = code.strip()
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", code, re.S)
    return m.group(1) if m else code


_LITERAL_MISSING = object()
_ALLOWED_PRIMITIVES = {
    "title", "caption", "label", "bits", "bit_brace", "arrow", "strike",
    "badge", "compare", "addition", "number_line", "dial", "register",
    "array", "predicate_strip", "code", "table", "rectangle", "curves",
    "hanoi", "tree", "grid", "block", "bus", "circle",
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

    known = set(dir(manim)) | set(dir(_builtins)) | {"__name__", "__file__"}
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
            # Only allow from manim import * or import math/numpy
            if isinstance(node, ast.ImportFrom) and node.module == "manim":
                continue
            if isinstance(node, ast.Import) and any(alias.name in {"math", "numpy"} for alias in node.names):
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
                    if kw.arg in {"include_background", "row_height", "col_widths", "corner", "alignment", "word_wrap_width", "multiline"}:
                        errors.append(f"{func_name}() does not accept '{kw.arg}=' in Manim {_target} (line {node.lineno})")

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
                break
                
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
    scene_classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and base.id == "Scene")
            or (isinstance(base, ast.Attribute) and base.attr == "Scene")
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
    class SceneXX(Scene):
        def construct(self):
            ...

Allowed imports:
    from manim import *
    import math
    import numpy as np

Do not import external packages.

CANVAS:
  * 16:9 landscape, designed for 1920x1080.
  * Keep important content inside x=-7..7 and y=-3.8..3.8.
  * Reserve the top for titles and the bottom for captions.
  * Never allow text or diagrams to clip.

TEXT SIZING:
  * Prefer Text(...).scale_to_fit_width(...) (or a deterministic font_size
    reduction) over a large fixed font_size — never assume a string will fit
    just because it looked fine for a shorter one.
  * Titles and captions must stay inside their reserved band; if a line is
    long, shrink it or wrap it rather than letting it cross the canvas edge.

CODE OBJECT (only if the section is specifically about source code):
  * Code(code_string=..., language="python", formatter_style="monokai",
    add_line_numbers=True, paragraph_config={"font_size": 24}) is the
    correct call shape.
  * Do NOT use code=, style=, insert_line_numbers=, or a bare font_size=
    kwarg — none of those exist on Code() anymore.

ANIMATION:
  * This is a genuine Manim animation timeline.
  * Use self.play(), self.wait(), .animate, Transform, ReplacementTransform,
    FadeIn, FadeOut, Create, Write, Indicate, Circumscribe, AnimationGroup,
    Succession and LaggedStart when appropriate.
  * Persistent objects keep identity; do not recreate them to fake continuity.
  * Use VGroup when labels must move with objects.
  * Every important animation has an explicit run_time.
  * Use anticipation -> action -> consequence.
  * Do not teleport an educationally important object.

PHYSICAL MOTION:
  * For movement prefer: highlight -> lift -> travel -> settle -> explain.
  * Tower of Hanoi legal move:
        lift vertically -> horizontal travel -> lower vertically.
  * Labels remain attached to disks.
  * Larger disks cannot be placed on smaller disks except during an explicitly
    labelled illegal demonstration.
  * Illegal demonstrations show the attempted state, INVALID/ILLEGAL marker,
    then restore the valid state.

PEDAGOGY:
  * One major visual idea per moment.
  * Highlight the active object before changing it.
  * Pause after important actions.
  * Color is never the only semantic signal.

TIMING:
  * Narration timestamps are authoritative.
  * Synchronize self.play() and self.wait() with the narration.
  * Do not leave an unexplained static scene for more than about 8 seconds.
  * Finish in the state described by the narration.

CODE QUALITY:
  * No pseudocode, markdown fences, print/open/exec/eval.
  * No undefined names or hallucinated Manim APIs.
  * Use constants and small geometry helpers.
  * The result must execute directly with Manim.
"""


def select_renderer(sec) -> str:
    """Select the renderer from explicit section tags or semantic cues."""
    explicit = getattr(sec, "renderer", None)
    if isinstance(explicit, str):
        explicit = explicit.strip().lower()
        if explicit in {"manim", "matplotlib"}:
            return explicit

    brief = str(getattr(sec, "anim", "") or "").lower()

    # Explicit tags in the animation brief always win.
    if "[manim]" in brief:
        return "manim"
    if "[matplotlib]" in brief or "[scenekit]" in brief:
        return "matplotlib"

    # Strong continuous-animation signals.
    manim_terms = (
        "animate", "animation", "move", "transform", "morph", "lift",
        "drop", "rotate", "zoom", "camera", "tower of hanoi", "recursion",
        "sorting", "pointer moves", "traverse", "step through", "trajectory",
        "physical motion",
    )
    if any(term in brief for term in manim_terms):
        return "manim"

    # Plot/data-heavy sections remain on the mature Matplotlib backend.
    return "matplotlib"


def build_manim_prompt(script: Script, sec, sents: list[dict],
                       previous_context: str = "") -> str:
    numbered = "\n".join(
        f"  [{i}] t={s['start']:6.1f}s -> {s['end']:6.1f}s  {s['text']}"
        for i, s in enumerate(sents)
    )
    total = sents[-1]["end"] if sents else 0.0
    class_name = f"Scene{sec.stem}"
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

    PREVIOUS SECTION CONTEXT:
        {previous_context}

    NARRATION TIMELINE:
        Total duration: {total:.2f} seconds

    {numbered}

    {manim_api_doc}

    OUTPUT CONTRACT:
      * Output ONLY complete Python source.
      * Start with: from manim import *
      * Define exactly one main class named {class_name}.
      * It MUST inherit from Scene and implement construct(self).
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
                  class_name: str) -> list[Path]:
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

    quality = os.environ.get("P2R_MANIM_QUALITY", "-qh")
    if quality not in {"-ql", "-qm", "-qh", "-qp"}:
        quality = "-qh"

    timeout = int(os.environ.get("P2R_MANIM_TIMEOUT", "600"))

    cmd = [
        sys.executable,
        "-m",
        "manim",
        quality,
        "--disable_caching",
        "--media_dir",
        str(media_dir),
        str(src),
        class_name,
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(proj),
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

    videos = sorted(
        media_dir.rglob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not videos:
        raise SystemExit("Manim completed without producing an MP4")

    target = section_dir / f"{src.stem}.mp4"
    shutil.copy2(videos[0], target)

    return sorted(media_dir.rglob("*.png"))


def _generate_manim(proj: Path, script: Script, index: int,
                    retries: int = 0, extra_feedback: str = "",
                    dst: Path | None = None) -> Path:
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
                previous_context = (
                    "Previous Manim scene for continuity. Preserve important "
                    "coordinates, scale and visual identity:\n"
                    f"```python\n"
                    f"{prev_dst.read_text(encoding='utf-8')[-10000:]}\n"
                    f"```\n"
                )

    prompt = build_manim_prompt(
        script, sec, sents, previous_context
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
            )
        except Exception as exc:
            sys.exit(
                f"[prompt2render] Manim section {sec.stem}: "
                f"LLM call failed — {exc}"
            )

        raw = strip_fences(code or "").strip()
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

        dst.write_text(raw, encoding="utf-8")

        try:
            with _RENDER_LOCK:
                frames = _render_manim(
                    proj,
                    dst,
                    section_dir,
                    f"Scene{sec.stem}",
                )
        except SystemExit as exc:
            err = str(exc)
            cfg.say(
                f"Manim section {sec.stem}: render rejected — {err[:120]}"
            )
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
             extra_feedback: str = "", dst: Path | None = None) -> Path:
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

    if renderer == "manim":
        return _generate_manim(
            proj, script, index,
            retries=retries,
            extra_feedback=extra_feedback,
            dst=dst,
        )

    return _generate_matplotlib(
        proj, script, index,
        retries=retries,
        extra_feedback=extra_feedback,
        dst=dst,
    )


def _generate_matplotlib(proj: Path, script: Script, index: int, retries: int = 0,
            extra_feedback: str = "", dst: Path | None = None) -> Path:
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

    prompt = build_prompt(script, sec, sents, previous_context=previous_context)
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
                label=f"section {sec.stem} (attempt {attempt}/{max_attempts or 'until pass'})"
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