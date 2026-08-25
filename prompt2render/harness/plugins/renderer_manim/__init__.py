"""Manim generation and rendering plugins for Prompt2Render.

This module provides two distinct roles:

1. GeneratorManimPlugin
   - LLM-driven alternative code generator.
   - Generates one Manim Scene per section.
   - Does NOT decide whether generated code is accepted.
   - Supports targeted repair through repair_router.

2. RendererManimPlugin
   - Renders generated Manim scenes.
   - The manual ``prompt2render manim`` escape hatch remains available.
   - Emits blocking findings when Manim compilation/rendering fails.

Acceptance is intentionally downstream:

    generation
        ↓
    code artifact
        ↓
    render
        ↓
    spatial / visual verification
        ↓
    accepted

A generated Python file therefore does not automatically mean that the
scene is accepted.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from ...context import CodeArtifact, RenderArtifact, SceneContext
from ...motion import MOTION_OPS, find_storyboard_states
from ...timing import narration_span
from ...plugin import Plugin
from ..verifier_execution import check_scene_artifact
from ....project import parse_script
from ....visuals import manim_scene


def hitl_status_sets(project_dir: Path | None) -> tuple[set[str], set[str]]:
    """Read ``hitl_feedback.json`` and split stems by status.

    Returns ``(rejected, locked)``. A "reject" entry forces a fresh
    regenerate+rerender. An "accept" entry is a hard LOCK: once the user is
    satisfied with a section, it must never be swept into an unrelated
    regeneration pass again — e.g. the align-mtime staleness heuristic
    below, which otherwise cannot tell "this scene's code is stale" apart
    from "some other scene's narration was re-synced, bumping every align
    file's mtime". Without an explicit lock, that kind of incidental
    trigger silently re-runs the (non-deterministic) LLM on a scene the
    user already approved, and it can come back worse.
    """

    rejected: set[str] = set()
    locked: set[str] = set()

    try:
        import json as _json

        path = project_dir / "hitl_feedback.json" if project_dir else None

        if path and path.exists():
            data = _json.loads(path.read_text(encoding="utf-8") or "{}")

            if isinstance(data, dict):
                for stem, entry in data.items():
                    if not isinstance(entry, dict):
                        continue
                    status = entry.get("status")
                    if status == "reject":
                        rejected.add(str(stem))
                    elif status == "accept":
                        locked.add(str(stem))
    except Exception:
        return set(), set()

    return rejected, locked


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIM_VERSION = "0.19.0"

MANIM_BUILD_DIR = "build/manim"

DEFAULT_MODEL = "gemini-3.7-flash"

DEFAULT_DURATION = 5.0

MAX_REPAIR_FEEDBACK = 6000

#: One initial attempt plus this many local regenerate-and-recheck attempts
#: before a scene's harness check failure is logged and generation moves on
#: to the next scene. See ``generator_code``'s identical constant/pattern.
MAX_HARNESS_CHECK_RETRIES = 1


# ---------------------------------------------------------------------------
# Deterministic Manim compatibility normalization
# ---------------------------------------------------------------------------

def _normalize_manim19(code: str) -> str:
    """Normalize a small set of known Manim 0.19 compatibility aliases.

    This is intentionally conservative.

    It must NOT become a generic code-repair mechanism. Actual semantic or
    compilation failures belong to the generator/repair/verifier pipeline.
    """

    if not isinstance(code, str):
        return ""

    # Strip BOM / zero-width that LLM or PowerShell may inject at start
    if code and code[0] == "\ufeff":
        code = code.lstrip("\ufeff")

    # Known Code keyword alias.
    code = re.sub(
        r"\binsert_line_numbers\s*=",
        "add_line_numbers=",
        code,
    )

    # Direction aliases sometimes emitted by LLMs.
    for old, new in (
        ("UP_LEFT", "UL"),
        ("UP_RIGHT", "UR"),
        ("DOWN_LEFT", "DL"),
        ("DOWN_RIGHT", "DR"),
    ):
        code = re.sub(
            rf"\b{old}\b",
            new,
            code,
        )

    # Known invalid LaTeX string escapes.
    code = re.sub(
        r"\\([&%_$#{}~^])",
        r"\\\\\1",
        code,
    )

    # Manim 0.19: Scene.wait(0) is a ValueError (duration must be >0).
    # The cue map may legitimately have gap 0.00 for back-to-back
    # sentences; LLMs sometimes emit self.wait(0.0) literally, which
    # crashes rendering. Strip those no-ops deterministically.
    # Keep waits >= 0.05s (manim's practical minimum is >0).
    code = re.sub(
        r"^\s*self\.wait\s*\(\s*0+(?:\.0+)?\s*\)\s*(?:\n|$)",
        "",
        code,
        flags=re.M,
    )
    code = re.sub(
        r"self\.wait\s*\(\s*0+(?:\.0+)?\s*\)",
        "self.wait(0.1)",
        code,
    )

    return code


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _safe_int(
    value: Any,
    default: int = 0,
    minimum: int = 0,
) -> int:
    """Safely parse a non-negative integer."""

    try:
        result = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, result)


def _ensure_llm_keys() -> None:
    """Provide legacy llm.keys() compatibility when required."""

    from .... import llm

    if hasattr(llm, "keys"):
        return

    def _keys() -> list[str]:
        keys: list[str] = []

        primary = os.environ.get(
            "GEMINI_API_KEY",
            "",
        ).strip()

        if primary:
            keys.append(primary)

        for name, value in sorted(
            os.environ.items()
        ):
            if (
                name.startswith("GEMINI_API_KEY_BACKUP")
                and value.strip()
            ):
                keys.append(value.strip())

        if not keys:
            raise RuntimeError(
                "[prompt2render] GEMINI_API_KEY is not configured."
            )

        return keys

    llm.keys = _keys


# ---------------------------------------------------------------------------
# Scene/script helpers
# ---------------------------------------------------------------------------

def _build_script(
    context: SceneContext,
):
    """Build the generator Script from the validated scene plan.

    The raw script determines title/narration/meta information.
    The harness scene plan determines scope and visual animation briefs.
    """

    script = parse_script(
        context.prompt
    )

    allowed_indices = {
        int(entry.index)
        for entry in context.scene_plan
    }

    plan_by_index = {
        int(entry.index): entry
        for entry in context.scene_plan
    }

    sections = []

    for section in script.sections:

        if int(section.index) not in allowed_indices:
            continue

        entry = plan_by_index.get(
            int(section.index)
        )

        if entry is None:
            continue

        # Harness-controlled animation brief is authoritative.
        section.anim = entry.anim

        sections.append(section)

    script.sections = sections

    return script


def _find_section(
    script,
    stem: str,
):
    """Find a script section safely."""

    return next(
        (
            section
            for section in script.sections
            if section.stem == stem
        ),
        None,
    )


def _scene_py_path(
    context: SceneContext,
    stem: str,
) -> Path:
    return (
        context.project_dir
        / MANIM_BUILD_DIR
        / f"scene_{stem}.py"
    )


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def _record_code_artifact(
    context: SceneContext,
    stem: str,
    path: Path | None,
    *,
    accepted: bool = False,
) -> None:
    """Synchronize code-artifact state.

    ``accepted`` defaults to False because generation alone does not establish
    semantic correctness.
    """

    exists = (
        path is not None
        and path.exists()
        and path.is_file()
    )

    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=path if exists else None,
        accepted=bool(
            accepted and exists
        ),
    )


def _record_failed_code_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=None,
        accepted=False,
    )


def _remove_generated_scene(
    context: SceneContext,
    stem: str,
) -> None:
    """Remove generated code and stale downstream artifacts."""

    py_file = _scene_py_path(
        context,
        stem,
    )

    py_file.unlink(
        missing_ok=True
    )

    context.code_artifacts.pop(
        stem,
        None,
    )

    context.render_artifacts.pop(
        stem,
        None,
    )


# ---------------------------------------------------------------------------
# Repair feedback
# ---------------------------------------------------------------------------

def _repair_feedback(
    context: SceneContext,
    stem: str,
) -> str:
    """Build bounded repair feedback for one scene."""

    repair_context = getattr(
        context,
        "repair_context",
        {},
    )

    if not isinstance(
        repair_context,
        dict,
    ):
        return ""

    messages = repair_context.get(
        stem,
        [],
    )

    if not isinstance(
        messages,
        list,
    ):
        return ""

    clean = [
        str(message).strip()
        for message in messages
        if str(message).strip()
    ]

    if not clean:
        return ""

    feedback = (
        "\n\nPRIOR REPAIR FEEDBACK:\n"
        + "\n".join(
            f"- {message}"
            for message in clean
        )
    )

    return feedback[-MAX_REPAIR_FEEDBACK:]


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def _load_timing(
    context: SceneContext,
    stem: str,
) -> tuple[float, str, list[dict[str, float]]]:
    """Load sentence timing when available.

    Returns (total_duration, timing_table_text, sentences_list).
    The raw sentences list is kept so the prompt can compute exact
    per-sentence wait deltas (when they are necessary to keep cue
    alignment).  Callers that only need the table can ignore the third
    value.
    """

    try:
        from .... import align

        data = align.load(
            context.project_dir,
            stem,
        )

        sentences = data.get(
            "sentences",
            [],
        )

        if isinstance(sentences, list) and sentences:
            # Both the old (dur) and new (start/end) align formats are
            # handled inside harness/timing.py -- see sentence_duration().

            # The section's wall-clock span, INCLUDING inter-sentence
            # silence. Previously this summed per-sentence durations, which
            # excludes every gap -- and since the prompt below asserts "the
            # total animation duration MUST equal {duration}", every scene
            # was told to finish early by exactly the accumulated silence
            # (measured: 13.50s across 342.08s on a real project). See
            # harness/timing.py.
            duration = narration_span(sentences)
            # fallback to audio_dur if sentences sum is broken (e.g. missing end)
            if duration <= 0.01:
                try:
                    duration = float(data.get("audio_dur", 0))
                except Exception:
                    pass

            timing_lines = []
            for s in sentences:
                if not isinstance(s, dict):
                    continue
                try:
                    st = float(s.get("start", 0))
                    en_raw = s.get("end")
                    if en_raw is None:
                        en_raw = st + float(s.get("dur", 0))
                    en = float(en_raw)
                except Exception:
                    continue
                txt = str(s.get("text", "")).strip()
                timing_lines.append(f"[{st:.2f}s - {en:.2f}s] {txt}")

            if duration > 0 and timing_lines:
                # Normalise sentences to a safe list of dicts with floats
                safe: list[dict[str, float]] = []
                for s in sentences:
                    if not isinstance(s, dict):
                        continue
                    try:
                        st = float(s.get("start", 0))
                        en_raw = s.get("end")
                        if en_raw is None:
                            en_raw = st + float(s.get("dur", 0))
                        en = float(en_raw)
                        dur = float(s.get("dur", en - st))
                        if dur <= 0:
                            dur = max(0.0, en - st)
                        safe.append({
                            "start": float(st),
                            "end": float(en),
                            "dur": float(dur),
                        })
                    except Exception:
                        continue
                return (
                    duration,
                    "\n".join(timing_lines),
                    safe,
                )

    except Exception:
        pass

    return (
        DEFAULT_DURATION,
        "[0.0s - 5.0s] "
        "(No timing data available)",
        [],
    )


# ---------------------------------------------------------------------------
# Deterministic motion compiler (Phase 2)
#
# GeneratorManimPlugin's LLM call authors object construction/placement
# only (one `_state_<name>(self)` method per storyboard state). The actual
# `construct()` choreography — self.play/self.wait sequencing and timing —
# is compiled deterministically from the storyboard's `motion` list here,
# instead of being free-hand authored by the LLM. This removes the LLM as a
# source of overlap/timing bugs for choreography, though it does not govern
# the LLM's *initial* placement of new mobjects inside each state's own
# setup method (see renderer_manim's REFERENCE PATTERN prompt guidance for
# that half of the problem).
# ---------------------------------------------------------------------------

def _storyboard_states_for(
    context: SceneContext,
    stem: str,
    index: int | None = None,
) -> list[dict[str, Any]] | None:
    """One section's ``states`` list, looked up by stem with index fallback."""

    return find_storyboard_states(context, stem, index=index)


#: CONTEXT->ANTICIPATION->ACTION->CONSEQUENCE ordering for flattening a
#: SemanticStateIR's beats into a flat motion-op list, regardless of the
#: order the LLM happened to list them in its response.
_PHASE_ORDER = {"CONTEXT": 0, "ANTICIPATION": 1, "ACTION": 2, "CONSEQUENCE": 3}


def _states_from_semantic_ir(
    context: SceneContext,
    stem: str,
) -> list[dict[str, Any]] | None:
    """Adapt Phase 3's ``SemanticAnimationIR`` into the flat state-dict shape
    ``_build_setup_prompt``/``_compile_construct_method`` already expect, so
    the compiler consumes the phase-tagged, potentially LLM-enriched beats
    instead of the flatter pre-Tier-1 storyboard motion list -- this is what
    actually delivers Phase 3's enrichment into rendered choreography rather
    than leaving it unconsumed.

    A ``hold=True`` state needs no special case: its empty beats list already
    produces an empty motion list, which ``_compile_construct_method``
    already treats as "fold this state's whole time budget into
    ``self.wait()``".

    Returns ``None`` (never raises) when either IR is missing or has no
    matching section/state for this stem -- the caller falls back to
    ``_storyboard_states_for``, keeping this experimental path resilient
    rather than adding a new hard-failure mode.
    """

    animation_ir = context.animation_ir
    semantic_ir = context.semantic_ir

    if animation_ir is None or semantic_ir is None:
        return None

    source_section = next(
        (s for s in animation_ir.sections if s.stem == stem), None
    )
    semantic_section = next(
        (s for s in semantic_ir.sections if s.stem == stem), None
    )

    if source_section is None or semantic_section is None:
        return None

    source_state_by_name = {s.name: s for s in source_section.states}
    states: list[dict[str, Any]] = []

    for sem_state in semantic_section.states:
        source_state = source_state_by_name.get(sem_state.name)

        if source_state is None:
            return None

        ordered_beats = sorted(
            sem_state.beats,
            key=lambda b: _PHASE_ORDER.get(b.phase, len(_PHASE_ORDER)),
        )

        states.append(
            {
                "name": sem_state.name,
                "cue": sem_state.cue,
                "visual": source_state.visual,
                "transition": source_state.transition,
                "motion": [
                    {"op": beat.op.op, **beat.op.params} for beat in ordered_beats
                ],
            }
        )

    return states


def _state_cue_timings(
    states: list[dict[str, Any]],
    sentences: list[dict[str, float]] | None,
    duration: float,
) -> list[dict[str, float]]:
    """Split narration time into a run_time/wait budget per state.

    Each state's ``cue`` resolves to a narration start timestamp. States are
    partitioned into consecutive slots bounded by the next state's start,
    with the final slot's boundary telescoping to the TRUE narration end
    (``sentences[-1]["end"]``) rather than ``duration`` — ``duration`` (as
    computed by ``_load_timing``) is sum(sentence durations), which excludes
    inter-sentence silence gaps and would otherwise silently truncate the
    final state's slot by the sum of every such gap in the section.
    """

    if not states:
        return []

    if sentences:
        true_end = float(sentences[-1].get("end", duration))
    else:
        true_end = float(duration)

    def _cue_start(cue: Any) -> float:
        if not sentences:
            return 0.0
        try:
            idx = int(cue)
        except (TypeError, ValueError):
            return 0.0
        if idx < 0 or idx >= len(sentences):
            return 0.0
        return float(sentences[idx].get("start", 0.0))

    starts = [_cue_start(state.get("cue", 0)) for state in states]
    boundaries = starts[1:] + [true_end]

    timings: list[dict[str, float]] = []

    for start, boundary in zip(starts, boundaries):
        slot = boundary - start

        # A degenerate (zero/negative) slot only arises when cues can't
        # resolve to real timestamps (e.g. no sentence data at all) — floor
        # it so the state still gets a positive run_time. Real sentence data
        # never triggers this, so the telescoping sum stays exact above.
        if slot <= 0.0:
            slot = 0.1

        run_time = slot * 0.85
        wait = slot - run_time

        timings.append({"run_time": run_time, "wait": wait})

    return timings


#: How long each motion op naturally takes to read as an animation, in
#: seconds -- independent of how long the narration slot around it happens
#: to be. Regression: a real e2e run showed run_time values of 15-30s for a
#: SINGLE Create() of one line/matrix, because run_time was simply 85% of
#: the whole narration slot with no ceiling -- a near-motionless crawl
#: instead of an animation. The excess must become self.wait() (the scene
#: holds while narration keeps talking), not stretch the animation itself.
_NATURAL_DURATION = {
    "Create": 1.4,
    "Write": 1.4,
    "FadeIn": 0.7,
    "FadeOut": 0.6,
    "Transform": 1.1,
    "MoveTo": 0.9,
    "Highlight": 0.8,
    # Phase 3 (docs/ARCHITECTURE_AUDIT.md SS17) ops.
    "NextTo": 0.9,
    "Circumscribe": 0.8,
    "GrowArrow": 1.0,
    "Uncreate": 1.2,
    "Rotate": 1.0,
}
_DEFAULT_NATURAL_DURATION = 1.2


def _natural_run_time(motion: list[dict[str, Any]]) -> float:
    """The natural animation duration for a group of simultaneous ops.

    Ops in one self.play(...) call run concurrently, not sequentially, so
    the group's natural duration is the slowest single op, not their sum.
    """

    if not motion:
        return 0.0

    return max(
        _NATURAL_DURATION.get(op.get("op"), _DEFAULT_NATURAL_DURATION)
        for op in motion
        if isinstance(op, dict)
    )


def _render_motion_op(op_name: str, op: dict[str, Any]) -> str:
    """Render one validated motion op to a Manim expression string."""

    target = op.get("target")

    if op_name in ("Create", "Write", "FadeIn", "FadeOut"):
        return f"{op_name}(self.{target})"

    if op_name == "Transform":
        return f"Transform(self.{target}, self.{op.get('into')})"

    if op_name == "MoveTo":
        return f"self.{target}.animate.move_to(self.{op.get('anchor')})"

    if op_name == "Highlight":
        return f"Indicate(self.{target})"

    if op_name == "NextTo":
        return f"self.{target}.animate.next_to(self.{op.get('anchor')})"

    if op_name == "Circumscribe":
        return f"Circumscribe(self.{target})"

    if op_name == "GrowArrow":
        return f"GrowArrow(self.{target})"

    if op_name == "Uncreate":
        return f"Uncreate(self.{target})"

    if op_name == "Rotate":
        # Angle is never authored in the motion vocabulary (see motion.py) --
        # a quarter turn is a safe, generic "show the other side" default.
        return f"Rotate(self.{target}, angle=PI/2)"

    raise ValueError(f"unknown motion op {op_name!r}")


def _validate_motion_op(op_name: str, op: dict[str, Any], state_name: str) -> None:
    """Defense-in-depth check mirroring harness.motion.validate_motion_ops.

    verifier_storyboard is the real gate for malformed motion; this only
    guards against the compiler ever being asked to emit broken Python if
    that gate is somehow bypassed.
    """

    if op_name not in MOTION_OPS:
        raise ValueError(
            f"unknown motion op {op_name!r} in state {state_name!r}"
        )

    missing = sorted(
        key for key in MOTION_OPS[op_name] if not op.get(key)
    )

    if missing:
        raise ValueError(
            f"missing required key(s) {missing} for {op_name} "
            f"in state {state_name!r}"
        )


def _state_setup_assignments(
    setup_source: str,
    state_name: str,
) -> dict[str, bool]:
    """{attr: has_constructor_args} for every ``self.<attr> = ...``
    assignment inside ``_state_<state_name>``'s own method body that
    ultimately traces to a real constructor call — either directly
    (``self.attr = Ctor(...)``) or via a local variable built up first and
    attached to ``self`` afterward (``group = VGroup(...); ...;
    self.attr = group`` — a common, natural way to write setup code, e.g.
    when the group is arranged/positioned across a couple of statements
    before being assigned). A real e2e run showed the direct-only version
    of this silently missing every object built this second way, so it
    never got a default entrance and never appeared on screen at all.

    Scoped to that one method's body (not the whole class) — an attribute
    reassigned by a *later* state is a different method entirely and is
    examined independently when that state is processed, so continuity
    ("don't re-fade-in a persistent object introduced earlier") falls out
    naturally without needing separate cross-state bookkeeping.
    """

    try:
        tree = ast.parse(setup_source)
    except SyntaxError:
        return {}

    method_name = f"_state_{state_name}"
    assignments: dict[str, bool] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            # First pass: local `name = Ctor(...)` bindings, so a later
            # `self.attr = name` can be traced back to its constructor call.
            local_calls: dict[str, bool] = {}

            for stmt in ast.walk(node):
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)):
                    continue
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        has_args = bool(stmt.value.args) or bool(stmt.value.keywords)
                        local_calls[target.id] = has_args

            # Second pass: self.attr assignments, resolved directly or via
            # the local-variable trace above.
            for stmt in ast.walk(node):
                if not isinstance(stmt, ast.Assign):
                    continue

                if isinstance(stmt.value, ast.Call):
                    has_args = bool(stmt.value.args) or bool(stmt.value.keywords)
                elif isinstance(stmt.value, ast.Name) and stmt.value.id in local_calls:
                    has_args = local_calls[stmt.value.id]
                else:
                    continue

                for target in stmt.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        assignments[target.attr] = has_args
            break

    return assignments


def _compile_construct_method(
    states: list[dict[str, Any]],
    timings: list[dict[str, float]],
    setup_source: str | None = None,
) -> str:
    """Deterministically compile ``construct(self):`` from storyboard states.

    Per state: call its ``_state_<name>()`` setup method, then group all of
    its motion ops into one ``self.play(..., run_time=...)`` and follow with
    ``self.wait(...)`` (suppressed when it would round to ~0 — Manim raises
    on ``wait(0)``). A state with no motion folds its whole time budget into
    a single ``self.wait(...)``.

    When ``setup_source`` is given, any mobject a state's own setup method
    constructs but that state's motion never explicitly brings on screen
    (the storyboard contract allows an empty ``motion`` list even when the
    setup code still legally does ``self.title = Text(...)`` — assigning to
    a Python attribute does not add anything to the Manim scene) gets a
    default entrance: ``self.add(...)`` for a zero-argument constructor call
    (the "build a container across states via later .add() calls" pattern —
    Manim errors animating FadeIn on a statically-empty VGroup()), otherwise
    a soft ``FadeIn`` folded into that state's grouped ``self.play(...)``.

    Two attribute names are structural, independent of the storyboard's
    motion vocabulary (which only plans the diagram/content, not chrome):
    ``self.title`` (any state) gets the same default-entrance FadeIn as any
    other newly-introduced object — nothing special, it just needs to exist
    once. ``self.caption_<state name>`` is special-cased: the first state
    that defines one gets it as a normal entrance, but every later state
    that defines its own ``caption_<state name>`` gets a ``Transform`` from
    the FIRST caption attribute into the new one, not a second independent
    FadeIn — this is what keeps every scene down to exactly one on-screen
    caption at a time (Transform mutates the original mobject's identity in
    place; a second independent FadeIn would instead leave both texts
    visible simultaneously, reproducing the original overlap bug this
    compiler exists to prevent).
    """

    lines = ["def construct(self):"]

    if not states:
        lines.append("    pass")
        return "\n".join(lines)

    # Attributes already on screen from an earlier state (via motion or a
    # prior default entrance). A later state's own setup method commonly
    # re-declares `self.<attr> = Ctor(...)` for an object that already
    # exists (ordinary, harmless code redundancy) — without this, that
    # re-declaration reads as "newly introduced" and gets a spurious default
    # FadeIn, which combines with a same-beat FadeOut into a fade-out-then-
    # back-in glitch instead of the intended removal.
    seen_attrs: set[str] = set()

    # The single caption mobject's identity attribute, once introduced —
    # every later state's caption update Transforms into/out of this same
    # attribute rather than creating a second independent caption.
    caption_identity: str | None = None

    for state, timing in zip(states, timings):
        name = state.get("name", "state")
        motion = state.get("motion") or []

        lines.append(f"    self._state_{name}()")

        effective_motion = list(motion)

        # Any attribute this state's OWN motion already references at all —
        # as target, into, or anchor, on ANY op — is already accounted for
        # by the storyboard author. Restricting this to just Create/Write/
        # FadeIn missed Transform/FadeOut/MoveTo targets, so e.g. an object
        # the storyboard already FadeOut's this beat would ALSO get a
        # default FadeIn layered into the same self.play(...) call —
        # contradictory (fade out and in at once) purely because its setup
        # method happens to construct it in this state too.
        introduced = {
            op.get(key)
            for op in motion
            if isinstance(op, dict)
            for key in ("target", "into", "anchor")
            if op.get(key)
        }

        if setup_source:
            assignments = _state_setup_assignments(setup_source, name)

            caption_attr = f"caption_{name}"

            if caption_attr in assignments:
                if caption_identity is None:
                    effective_motion.append({"op": "FadeIn", "target": caption_attr})
                    caption_identity = caption_attr
                else:
                    effective_motion.append(
                        {"op": "Transform", "target": caption_identity, "into": caption_attr}
                    )
                # Handled above — the generic default-entrance loop below
                # must not also fade it in independently.
                introduced = introduced | {caption_attr}

            for attr, has_args in sorted(assignments.items()):
                if attr in introduced or attr in seen_attrs:
                    continue
                if has_args:
                    effective_motion.append({"op": "FadeIn", "target": attr})
                else:
                    lines.append(f"    self.add(self.{attr})")

            seen_attrs.update(assignments.keys())

        seen_attrs.update(introduced)

        run_time = float(timing.get("run_time", 0.0))
        wait = float(timing.get("wait", 0.0))

        if effective_motion:
            calls = []

            for op in effective_motion:
                if not isinstance(op, dict):
                    raise ValueError(f"invalid motion op in state {name!r}: {op!r}")

                op_name = op.get("op")
                _validate_motion_op(op_name, op, name)
                calls.append(_render_motion_op(op_name, op))

            # Cap run_time at what this motion naturally takes to read as an
            # animation; a wide narration slot must not stretch the
            # animation itself into a crawl -- the excess becomes wait
            # instead, so the scene holds still while narration continues.
            natural = _natural_run_time(effective_motion)
            if natural > 0.0 and run_time > natural:
                wait += run_time - natural
                run_time = natural

            lines.append(
                f"    self.play({', '.join(calls)}, run_time={run_time:.2f})"
            )

            if wait > 0.05:
                lines.append(f"    self.wait({wait:.2f})")
        else:
            total_wait = run_time + wait

            if total_wait > 0.05:
                lines.append(f"    self.wait({total_wait:.2f})")

    return "\n".join(lines)


def _splice_construct_method(setup_source: str, construct_src: str) -> str:
    """Insert a compiled ``construct(self):`` method into the single class
    defined by ``setup_source`` (LLM-authored ``_state_<name>`` methods).

    Appended after the class's existing methods rather than parsed/rebuilt
    as an AST and unparsed, so the LLM's original formatting/comments in
    ``setup_source`` are preserved byte-for-byte.
    """

    tree = ast.parse(setup_source)

    class_node = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef)),
        None,
    )

    if class_node is None:
        raise ValueError(
            "generated setup source does not define a class"
        )

    lines = setup_source.splitlines()

    indent = "    "

    if class_node.body:
        first_line = lines[class_node.body[0].lineno - 1]
        indent = first_line[: len(first_line) - len(first_line.lstrip())] or indent

    indented_construct = [
        indent + line for line in construct_src.splitlines()
    ]

    end = class_node.end_lineno or len(lines)

    return "\n".join(lines[:end] + [""] + indented_construct + lines[end:])


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class RendererManimPlugin(Plugin):
    """Render Manim scenes.

    This plugin also preserves the manual Manim escape hatch:

        prompt2render manim <slug> <pyfile> <scene> <index>

    Automatic rendering operates only on accepted/generated code artifacts.
    Rendering failure becomes a blocking finding for repair_router.
    """

    name = "renderer_manim"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
            # Without this, renderer_manim and verifier_execution are mere
            # sibling consumers of code_artifacts with no ordering between
            # them, so "verify before render" held only by accident of
            # registry list order. Depending on the field verifier_execution
            # actually publishes makes the topological sort put it first
            # unconditionally, so a scene can never reach the Manim CLI
            # before its generated code has passed (or been repaired past)
            # the pre-flight static check.
            "static_code_verified",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "render_artifacts",
            "check_results",
        ]

    def _record_render_failure(
        self,
        context: SceneContext,
        stem: str,
        error: Exception | str,
    ) -> None:
        from ...finding import (
            Category,
            Finding,
            Severity,
            next_finding_id,
        )

        message = str(error)

        finding = Finding(
            finding_id=next_finding_id(
                "manim"
            ),
            scene_id=stem,
            category=Category.RENDER,
            severity=Severity.BLOCKING,
            message=(
                "Manim compilation/render failed:\n"
                f"{message}"
            ),
        )

        result = finding.as_check_result()
        result["finding_type"] = "manim_crash"

        context.check_results.setdefault(
            self.name,
            [],
        ).append(result)

        context.render_artifacts[stem] = (
            RenderArtifact(
                stem=stem,
                outdir=context.project_dir,
                manifest=[],
            )
        )

    def _render_one(
        self,
        context: SceneContext,
        script,
        artifact: CodeArtifact,
        section,
    ) -> None:
        from .... import cfg

        stem = artifact.stem

        try:
            out = manim_scene(
                context.project_dir,
                script,
                artifact.path,
                f"Scene{stem}",
                section.index,
            )

            context.render_artifacts[stem] = (
                RenderArtifact(
                    stem=stem,
                    outdir=out.parent,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                )
            )

        except SystemExit as exc:
            # visuals.manim_scene historically calls sys.exit().
            error = str(exc)

            cfg.warn(
                f"Manim render failed for {stem}: "
                f"{error}"
            )

            self._record_render_failure(
                context,
                stem,
                error,
            )

        except Exception as exc:
            cfg.warn(
                f"Manim render failed for {stem}: "
                f"{exc}"
            )

            self._record_render_failure(
                context,
                stem,
                exc,
            )

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        # ---------------------------------------------------------------
        # Manual escape hatch
        # ---------------------------------------------------------------

        py_file = self.config.get(
            "py_file"
        )

        scene = self.config.get(
            "scene"
        )

        index = self.config.get(
            "index"
        )

        script = parse_script(
            context.prompt
        )

        if (
            py_file
            and scene
            and index is not None
        ):
            try:
                numeric_index = int(index)
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"Invalid Manim index: {index}"
                ) from exc

            out = manim_scene(
                context.project_dir,
                script,
                Path(py_file),
                str(scene),
                numeric_index,
            )

            stem = (
                f"{numeric_index:02d}"
            )

            context.render_artifacts[stem] = (
                RenderArtifact(
                    stem=stem,
                    outdir=out.parent,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                )
            )

            return context

        # ---------------------------------------------------------------
        # Automatic rendering
        # ---------------------------------------------------------------

        if not context.code_artifacts:
            return context

        # Preserve successful renders unless this scene is explicitly
        # being repaired.  HITL rejects are treated as repairs so the
        # sections listed in hitl_feedback.json are always re-rendered to
        # a fresh clip before any assembly decision.
        repair_context = getattr(
            context,
            "repair_context",
            {},
        )
        hitl_rejects_r, locked_r = hitl_status_sets(context.project_dir)

        for stem, artifact in list(
            context.code_artifacts.items()
        ):

            if (
                not artifact.path
                or not artifact.path.exists()
            ):
                continue

            if (
                artifact.accepted is False
                and stem not in repair_context
            ):
                # Generated code exists but has not yet passed downstream
                # code/semantic acceptance. It may still be rendered for
                # verification depending on the surrounding pipeline, so
                # we intentionally do not reject it here.
                pass

            existing = context.render_artifacts.get(
                stem
            )

            # A locked (hitl "accept") stem with an existing render is done —
            # skip unconditionally, even if a stray repair_context/reject
            # entry would otherwise force a re-render. Its code never
            # changes once locked (see the generator's own lock check), so
            # the only thing a forced re-render could do here is burn time
            # reproducing the same clip.
            if existing and existing.manifest and stem in locked_r:
                continue

            if (
                existing
                and existing.manifest
                and stem not in repair_context
                and stem not in hitl_rejects_r
            ):
                continue

            section = _find_section(
                script,
                stem,
            )

            if section is None:
                continue

            self._render_one(
                context,
                script,
                artifact,
                section,
            )

        return context

    def _default_gate(self) -> bool:
        # Rendering is not an upstream quality gate.
        return False


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class GeneratorManimPlugin(Plugin):
    """Generate Manim code for each validated scene.

    This is an alternative backend to generator_code.

    It is deliberately LLM-driven, but the LLM is constrained by:
    - the validated scene plan,
    - the storyboard/visual contract,
    - exact narration timing,
    - Manim CE 0.19 compatibility rules,
    - and repair feedback.

    Generated code is NOT automatically accepted.
    """

    name = "generator_manim"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "narration",
            # Documents the real data dependency now that the (opt-in)
            # motion-compiler path can consume animation_ir/semantic_ir.
            # Note: generator_manim is hot-swapped in for generator_code
            # AFTER DAG resolution (F13, unfixed -- Tier 2 Phase 8-9's job),
            # so this has no effect on today's actual ordering; it's
            # accurate documentation, not yet a functional guarantee.
            "animation_ir",
            "semantic_ir",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "code_artifacts",
        ]

    def _get_llm_client(
        self,
    ):
        """Compatibility fallback for older llm implementations."""

        from .... import llm

        _ensure_llm_keys()

        keys = llm.keys()

        if not keys:
            raise RuntimeError(
                "No Gemini API key configured."
            )

        if hasattr(
            llm,
            "client",
        ):
            return (
                llm,
                llm.client(keys[0]),
                None,
            )

        try:
            if hasattr(
                llm,
                "model_chain",
            ):
                models = llm.model_chain(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                )

                model = models[0]

            else:
                model = os.environ.get(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                )

            if hasattr(
                llm,
                "complete",
            ):
                return (
                    llm,
                    None,
                    model,
                )

            from openai import OpenAI

            client = OpenAI(
                api_key=keys[0],
                base_url=(
                    "https://generativelanguage."
                    "googleapis.com/v1beta/openai/"
                ),
                timeout=300.0,
                max_retries=2,
            )

            return (
                llm,
                client,
                model,
            )

        except ImportError as exc:
            raise RuntimeError(
                "Neither the project LLM client nor "
                "the OpenAI compatibility client is available."
            ) from exc

    def _build_prompt(
        self,
        section,
        timing_table: str,
        duration: float,
        extra_feedback: str,
        sentences: list[dict[str, float]] | None = None,
    ) -> str:
        """Construct the deterministic Manim generation contract."""

        # Build exact per-sentence cue deltas so the LLM can emit precise
        # self.wait() values.  When necessary (i.e. when the narration has
        # >1 sentence) the animation for sentence N must start exactly at
        # sentences[N].start — the gap to the next cue is the source of
        # truth, not an estimated run_time.
        cue_block = ""
        if sentences and len(sentences) > 1:
            lines = []
            for idx, s in enumerate(sentences):
                st = float(s.get("start", 0))
                en = float(s.get("end", st + float(s.get("dur", 0))))
                dur = float(s.get("dur", en - st))
                nxt = float(sentences[idx + 1].get("start", en)) if idx + 1 < len(sentences) else duration
                gap = max(0.0, nxt - en)
                # Only emit a wait cue when the narration actually has a gap;
                # when sentences are back-to-back the gap is ~0 and no extra
                # wait is necessary. Emitting wait(0.0) crashes Manim
                # (ValueError: duration <=0), so suppress it.
                if idx + 1 < len(sentences):
                    if gap > 0.05:
                        lines.append(
                            f"  - After sentence {idx+1} ends at {en:.2f}s, wait {gap:.2f}s "
                            f"(until {nxt:.2f}s) before starting sentence {idx+2}'s animation."
                        )
                    else:
                        lines.append(
                            f"  - After sentence {idx+1} ends at {en:.2f}s, next sentence starts immediately at {nxt:.2f}s (gap ≈0, no wait needed)."
                        )
                # Highlight duration budget for this sentence's animation
                lines.append(
                    f"  - Sentence {idx+1} window: start {st:.2f}s, duration budget {dur:.2f}s "
                    f"(do not overrun {en:.2f}s)."
                )
            cue_block = "\n".join(lines)
        elif sentences and len(sentences) == 1:
            s = sentences[0]
            cue_block = (
                f"  - Single-sentence section: animation window is "
                f"{float(s.get('start',0)):.2f}s → {float(s.get('end', duration)):.2f}s "
                f"(budget {float(s.get('dur', duration)):.2f}s)."
            )

        prompt = f"""
Write a Manim Community Edition {MANIM_VERSION} script for this educational
video section.

TITLE:
{section.title}

VISUAL PLAN:
{section.anim}

NARRATION WITH EXACT TIMING:
{timing_table}

TOTAL DURATION:
{duration:.1f} seconds
"""
        if cue_block:
            prompt += f"""
EXACT CUE MAP (use these waits when they are necessary to keep sync):
{cue_block}
"""

        prompt += f"""
REQUIREMENTS:

1. Use Manim Community Edition v{MANIM_VERSION}.
   Use:
        from manim import *

   Do not use APIs introduced after v{MANIM_VERSION}.

2. Define exactly one class:
        Scene{section.stem}

   It must inherit from Scene.

3. EXACT SYNCHRONIZATION (CRITICAL — when they are necessary):
   You MUST use the exact start times from the NARRATION table and CUE MAP above.
   - Do NOT start an animation before its corresponding narration sentence begins.
    - Between sentences, use `self.wait(gap)` where gap is the exact value from the CUE MAP.
      When sentences are back-to-back (gap ≤0.05), do NOT insert any self.wait at all — Manim
      rejects wait(0) with ValueError. Let the next animation start immediately, but still
      ensure the previous animation's run_time did not overrun its window. NEVER emit
      self.wait(0) or self.wait(0.0).
    - Set each `self.play(..., run_time=...)` so the animation fits inside its sentence's
      duration budget.  Prefer `run_time = min(budget*0.85, natural_duration)` and then
      `self.wait(remaining)` to fill to the exact cue (remaining must be >0).
    - For example, if sentence 2 starts at 4.50s and sentence 1 ends at 4.20s, insert
      `self.wait(0.30)` after sentence 1's animation before starting sentence 2's. If the gap
      is 0.00, insert no wait.
    - When `remaining` is large (> ~3s) after the primary reveal, do NOT spend it as one
      silent `self.wait(remaining)` — that reads as the video freezing. Chain 1-3 more small,
      purposeful animations that continue supporting the SAME sentence instead (see
      ANIMATION QUALITY below), and only `self.wait()` whatever small remainder is left after
      those.
   
   The total animation duration MUST equal:
        {duration:.1f} seconds

4. LAYOUT (avoid overlap):
   - Title: `title.to_edge(UP, buff=0.35)`. Never place the title with an absolute
     `move_to(UP * <guess>)` — a guessed offset can collide with content below it
     depending on the actual rendered text height; `to_edge` cannot.
   - Title font_size: 40-48.
   - Define ONE caption position constant near the top of construct(), e.g.
     `caption_y = DOWN * 3.15`, and reuse that exact constant for every narration
     caption in the scene.
   - Use exactly ONE caption Mobject for the whole scene. Create it once and
     `.move_to(caption_y)`. For every subsequent narration sentence, update the
     SAME mobject with `Transform(caption, new_caption)` (or `.become(...)`).
     Never create a second caption-like text that is visible at the same time as
     the first — that is a direct overlap risk with the caption band.
   - Primary visual: centered or slightly above center, clear of the title band
     and the caption band.
   - Every OTHER text/label/equation introduced for a single narration beat
     (a side annotation, an equation, a call-out) must do ONE of:
       (a) be explicitly removed with `FadeOut` (or replaced via `Transform`)
           before or when the next beat's own annotations appear, OR
       (b) be positioned with `next_to(existing_mobject, DIRECTION, buff=...)`
           relative to a persistent on-screen object — not an absolute
           `UP*k` / `DOWN*k` guess.
     Do not let more than one auxiliary label/equation sit simultaneously at
     independent absolute coordinates as the scene progresses — accumulating
     "floating" annotations that are never cleaned up is the most common cause
     of text overlapping other elements later in a scene.
   - Only the core recurring diagram (e.g. axes, nodes, a persistent graph) may
     legitimately stay on screen unmodified for the whole scene; everything else
     is transient and must be cleaned up per the rule above.
   - Build any legend or multi-part label as
     `VGroup(part1, part2, ...).arrange(RIGHT, buff=...)` (or `DOWN`) followed by
     ONE `.move_to(...)` on the group — never position each child of a group
     with its own separate absolute coordinate; `.arrange()` guarantees the
     children can't overlap each other by construction.

5. TEXT:
   - Break long sentences into multiple lines.
   - Scale text when necessary.
   - Never allow text to leave the 16:9 frame.
   - Prefer concise labels over paragraphs.
   - Organize construct() with one comment block per narration sentence
     (e.g. `# SENTENCE 2`) so the structure is easy to review and regenerate.

REFERENCE PATTERN (imitate this structure — not the specific text/content):

    title = Text("...").to_edge(UP, buff=0.35)
    caption_y = DOWN * 3.15

    caption = Text("First narration sentence.", font_size=26).move_to(caption_y)
    self.play(Write(title), Write(caption), run_time=2.0)

    # ... when sentence 2 begins, update the SAME caption mobject ...
    caption_2 = Text("Second narration sentence.", font_size=26).move_to(caption_y)
    self.play(Transform(caption, caption_2), run_time=2.0)

    # A transient annotation anchored to an existing object, not a guessed
    # absolute coordinate:
    note = Text("detail", font_size=20).next_to(some_node, RIGHT, buff=0.2)
    self.play(FadeIn(note), run_time=0.8)
    ...
    self.play(FadeOut(note), run_time=0.4)  # cleaned up before the next beat's annotations appear

    # A legend/group built with .arrange(), not per-child absolute coordinates:
    legend = VGroup(
        VGroup(Dot(color=BLUE), Text("Class 0", font_size=21)).arrange(RIGHT, buff=0.15),
        VGroup(Dot(color=RED), Text("Class 1", font_size=21)).arrange(RIGHT, buff=0.15),
    ).arrange(RIGHT, buff=0.5).move_to(DOWN * 2.65)

6. MANIM 0.19 API SAFETY:
   - Do not pass font_size or direction to Axes.get_x_label/get_y_label. Create Text labels and position them with next_to.
   - Do not pass corner= to move_to. Use move_to(point) or align_to.
   - Do not pass theme= to Code. Use Code(code_string=..., language=...).
   - Do not pass row_height=, col_widths=, or include_background= to MobjectTable or Table. Scale the entire table using scale() or scale_to_fit_width() instead.
   - Do not pass include_background= to Text, MathTex, or Tex.
   - For Code line numbers use add_line_numbers=True. Never use insert_line_numbers.
   - Use UL/UR/DL/DR. Never use UP_LEFT/UP_RIGHT/DOWN_LEFT/DOWN_RIGHT.

7. VECTOR SAFETY & SHAPES:
   - move_to() requires a coordinate vector.
   - put_start_and_end_on() requires coordinate vectors.
   - Never pass a scalar where a 3D coordinate is required.
   - SurroundingRectangle, BackgroundRectangle, and always_redraw require a Mobject (like a Text or Circle), NOT a coordinate array. Never pass number_to_point(), get_center(), or c2p() directly to them.

8. ANIMATION QUALITY (this is what separates a state-of-the-art explainer
   from a slideshow — treat it as a hard requirement, not decoration):
   - Build multi-part diagrams PROGRESSIVELY, never as one flat reveal.
     Instead of `Create(whole_group)` or `FadeIn(whole_group)`, stagger the
     pieces: `self.play(LaggedStart(*[Create(m) for m in group], lag_ratio=0.15), run_time=...)`.
     A diagram assembling itself piece by piece reads as intentional and
     alive; a whole diagram popping in at once reads as a slide.
   - Match the animation verb to what is actually happening, not just
     Create/FadeIn/Transform by default:
       * `Write` for text/equations being "spoken into existence".
       * `Create` for drawing a geometric shape/line/graph.
       * `GrowArrow` / `GrowFromCenter` for vectors, arrows, emphasis pops.
       * `Indicate`, `Circumscribe`, or `Flash` to draw the eye to
         whatever the CURRENT narration sentence is actually talking
         about — use these liberally as secondary beats, not just on
         first appearance.
       * `ReplacementTransform` or `TransformMatchingTex` when one
         equation morphs into a related one (e.g. simplifying, substituting
         a value) — never FadeOut the old one and FadeIn an unrelated new
         one when they are mathematically connected; a matching-transform
         visually shows the algebra happening.
   - Use `rate_func=` deliberately (e.g. `rate_func=smooth`,
     `rate_func=there_and_back` for a pulse/highlight) rather than leaving
     everything on Manim's raw default pacing — it is the difference between
     motion that feels considered and motion that feels mechanical.
   - Give every recurring concept (a class, a layer, a variable, a role) ONE
     fixed color used consistently for it everywhere it appears in this
     section — color should encode meaning, not be arbitrary decoration.
   - A long `run_time` window is an invitation to choreograph more, not to
     stretch one animation thin or sit on one `self.wait()`. If a beat's
     budget is generous, spend it on 2-4 small sequential animations
     (build → emphasize a detail → hold briefly) instead of a single slow
     `Create` or a single static freeze.

9. Do not use:
   - undocumented keyword arguments
   - deprecated classes
   - unknown Manim APIs
   - .set_shadow(blur=...)
   - invented helper APIs

10. Preserve all numerical values and relationships from the visual plan.

11. Implement the storyboard progressively.
     Do not display unrelated major visual elements simultaneously.
     When a new sentence's visual builds on the previous, keep prior mobjects on screen
     and animate the delta — do not clear the scene between cues unless the brief
     explicitly demands it.

12. The visual plan is authoritative.
     Do not reinterpret or replace its core visual claim.

13. Output ONLY valid Python code.
    No Markdown fences.
    No explanation.
""".strip()

        if extra_feedback:
            prompt += (
                "\n\n"
                + extra_feedback
            )

        return prompt

    def _build_setup_prompt(
        self,
        section,
        states: list[dict[str, Any]],
        duration: float,
        extra_feedback: str,
    ) -> str:
        """Contract for the compiler-backed path.

        The LLM authors ONLY object construction/placement — one
        `_state_<name>(self)` method per storyboard state. Choreography
        (self.play/self.wait/run_time) is compiled deterministically
        afterward by `_compile_construct_method` from each state's fixed
        `motion` list; it is never authored by the LLM here, which removes
        the LLM as a source of choreography-driven overlap/timing bugs.
        """

        state_blocks = []

        for state_no, state in enumerate(states):
            name = state.get("name", "state")
            motion = state.get("motion") or []

            targets = sorted({
                op.get(key)
                for op in motion
                if isinstance(op, dict)
                for key in ("target", "into", "anchor")
                if op.get(key)
            })

            motion_desc = ", ".join(
                f"{op.get('op')}("
                + ", ".join(
                    f"{k}={op.get(k)}"
                    for k in ("target", "into", "anchor")
                    if op.get(k)
                )
                + ")"
                for op in motion
                if isinstance(op, dict)
            ) or "(none — this state only adjusts what is already visible)"

            required = [f"self.{t}" for t in targets]
            required.append(f"self.caption_{name}")

            structural_notes = [
                f"    MUST ALSO define `self.caption_{name}`: a short (<=8 word) "
                f"on-screen caption Text summarizing this state's teaching point, "
                f"positioned at the SAME fixed caption position used by every "
                f"other state's caption (e.g. `.move_to(DOWN * 3.15)`) — the "
                f"compiled choreography transforms it into/out of every other "
                f"state's caption automatically; do not position or size it "
                f"differently per state."
            ]

            if state_no == 0:
                required.append("self.title")
                structural_notes.append(
                    f"    MUST ALSO define `self.title`: the section title Text, "
                    f"positioned with `.to_edge(UP, buff=0.35)`. Only this first "
                    f"state may define it."
                )

            attrs = ", ".join(required)

            state_blocks.append(
                f"- _state_{name}(self):\n"
                f"    Visual: {state.get('visual', '')}\n"
                f"    Transition: {state.get('transition', '')}\n"
                f"    Motion for this state (compiled separately — context only, "
                f"do not implement it yourself): {motion_desc}\n"
                f"    MUST define these exact attributes so the compiled "
                f"choreography can reference them: {attrs}\n"
                + "\n".join(structural_notes)
            )

        states_block = "\n\n".join(state_blocks)

        prompt = f"""
Write the object-construction half of a Manim Community Edition
{MANIM_VERSION} scene for this educational video section.

TITLE:
{section.title}

VISUAL PLAN:
{section.anim}

TOTAL DURATION:
{duration:.1f} seconds

You are authoring ONLY per-state setup methods, NOT the scene's
choreography. A separate deterministic compiler generates `construct(self)`
afterward from each state's fixed motion-op list, calling your methods in
order and animating the exact objects you define. Because of this:

- Do NOT define `construct(self)`.
- Do NOT call `self.play(`, `self.wait(`, or any other animation method
  anywhere in your code.
- Only CONSTRUCT and POSITION mobjects, assigning each one to a
  `self.<name>` attribute using `.move_to()` / `.to_edge()` / `.next_to()`
  / `.arrange()` etc. Positioning is required and expected; only
  *animating* is forbidden.

REQUIREMENTS:

1. Use Manim Community Edition v{MANIM_VERSION}.
   Use:
        from manim import *

   Do not use APIs introduced after v{MANIM_VERSION}.

2. Define exactly one class:
        Scene{section.stem}

   It must inherit from Scene.

3. Define exactly one method per state below, named exactly as given
   (`_state_<name>(self)`), in this order. Each method must define every
   `self.<name>` attribute listed for it — the compiled choreography
   references these attributes by name and will raise AttributeError at
   render time if any is missing.

STATES:

{states_block}

4. LAYOUT (avoid overlap):
   - Title: `self.title.to_edge(UP, buff=0.35)` in the first state only. Never
     place it with an absolute `move_to(UP * <guess>)` — a guessed offset can
     collide with content below it depending on the actual rendered text
     height; `to_edge` cannot.
   - Title font_size: 40-48.
   - Every state's `self.caption_<name>` MUST use the exact same position
     (e.g. `.move_to(DOWN * 3.15)`) and font_size — the compiler Transforms
     the first one into every later one, so any difference in position/size
     between them will visibly jump. Do NOT write any Transform/FadeIn calls
     for captions yourself; the compiler does that for you from the
     `caption_<name>` attributes alone.
   - Primary visual: centered or slightly above center, clear of the title
     band and the caption band.
   - Every OTHER text/label/equation attribute a state defines must either
     be positioned with `next_to(existing_mobject, DIRECTION, buff=...)`
     relative to a persistent on-screen object, or reuse the fixed caption
     position — never an independent absolute `UP*k` / `DOWN*k` guess.
     Accumulating "floating" annotations at independent absolute
     coordinates is the most common cause of text overlapping other
     elements later in a scene. The compiled choreography will FadeOut/
     Transform objects per each state's motion, but only if you have not
     already placed them somewhere that collides with what comes next.
   - Build any legend or multi-part label as
     `VGroup(part1, part2, ...).arrange(RIGHT, buff=...)` (or `DOWN`)
     followed by ONE `.move_to(...)` on the group.

5. MANIM 0.19 API SAFETY:
   - Do not pass font_size or direction to Axes.get_x_label/get_y_label. Create Text labels and position them with next_to.
   - Do not pass corner= to move_to. Use move_to(point) or align_to.
   - Do not pass theme= to Code. Use Code(code_string=..., language=...).
   - Do not pass row_height=, col_widths=, or include_background= to MobjectTable or Table. Scale the entire table using scale() or scale_to_fit_width() instead.
   - Do not pass include_background= to Text, MathTex, or Tex.
   - For Code line numbers use add_line_numbers=True. Never use insert_line_numbers.
   - Use UL/UR/DL/DR. Never use UP_LEFT/UP_RIGHT/DOWN_LEFT/DOWN_RIGHT.

6. VECTOR SAFETY & SHAPES:
   - move_to() requires a coordinate vector.
   - put_start_and_end_on() requires coordinate vectors.
   - Never pass a scalar where a 3D coordinate is required.
   - SurroundingRectangle, BackgroundRectangle, and always_redraw require a Mobject (like a Text or Circle), NOT a coordinate array. Never pass number_to_point(), get_center(), or c2p() directly to them.

7. Do not use:
   - undocumented keyword arguments
   - deprecated classes
   - unknown Manim APIs
   - .set_shadow(blur=...)
   - invented helper APIs

8. Preserve all numerical values and relationships from the visual plan.

9. Output ONLY valid Python code.
   No Markdown fences.
   No explanation.
""".strip()

        if extra_feedback:
            prompt += (
                "\n\n"
                + extra_feedback
            )

        return prompt

    def _generate_code(
        self,
        prompt: str,
    ) -> str:
        """Generate code through the project's LLM abstraction."""

        from .... import llm

        _ensure_llm_keys()

        if hasattr(
            llm,
            "complete",
        ):
            code = llm.complete(
                prompt,
                max_tokens=5000,
                model_env="P2R_SCENE_MODEL",
                default_model=os.environ.get(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                ),
                label="manim",
            )

            return str(code or "")

        _, client, model = (
            self._get_llm_client()
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        if not response.choices:
            return ""

        return str(
            response.choices[0].message.content
            or ""
        )

    def _clean_generated_code(
        self,
        code: str,
    ) -> str:
        """Remove fences and apply deterministic compatibility normalization."""

        code = (
            code
            or ""
        ).strip()

        # Strip Markdown code fences.
        match = re.match(
            r"^```(?:python)?\s*\n(.*?)\n```\s*$",
            code,
            re.S,
        )

        if match:
            code = match.group(1)

        return _normalize_manim19(
            code
        ).strip()

    def _generate_one(
        self,
        context: SceneContext,
        section,
    ) -> None:
        """Generate exactly one Manim scene."""

        from .... import cfg

        stem = section.stem

        outdir = (
            context.project_dir
            / MANIM_BUILD_DIR
        )

        outdir.mkdir(
            parents=True,
            exist_ok=True,
        )

        py_file = (
            outdir
            / f"scene_{stem}.py"
        )

        duration, timing_table, sentences = (
            _load_timing(
                context,
                stem,
            )
        )

        extra_feedback = (
            _repair_feedback(
                context,
                stem,
            )
        )

        use_compiler = bool(
            self.config.get(
                "use_motion_compiler",
                False,
            )
        )

        states: list[dict[str, Any]] = []

        if use_compiler:
            states = (
                _states_from_semantic_ir(context, stem)
                or _storyboard_states_for(context, stem, index=section.index)
                or []
            )
            prompt = self._build_setup_prompt(
                section,
                states,
                duration,
                extra_feedback,
            )
        else:
            prompt = self._build_prompt(
                section,
                timing_table,
                duration,
                extra_feedback,
                sentences,
            )

        try:
            code = self._generate_code(
                prompt
            )

            code = self._clean_generated_code(
                code
            )

            if not code:
                raise RuntimeError(
                    "LLM returned empty Manim code."
                )

            if use_compiler:
                try:
                    timings = _state_cue_timings(states, sentences, duration)
                    construct_src = _compile_construct_method(
                        states,
                        timings,
                        setup_source=code,
                    )
                    code = _splice_construct_method(code, construct_src)
                except (SyntaxError, ValueError) as exc:
                    cfg.warn(
                        f"section {stem}: motion compiler failed, falling "
                        f"back to setup-only code: {exc}"
                    )

            # Write only after successful generation and normalization.
            py_file.write_text(
                code,
                encoding="utf-8",
            )

            # IMPORTANT:
            # Generated != accepted.
            _record_code_artifact(
                context,
                stem,
                py_file,
                accepted=False,
            )

            cfg.say(
                f"section {stem}: "
                "Manim code generated"
            )

        except Exception as exc:
            cfg.warn(
                f"Manim generation failed for "
                f"{stem}: {exc}"
            )

            _record_failed_code_artifact(
                context,
                stem,
            )

    def _generate_and_check_one(
        self,
        context: SceneContext,
        section,
    ) -> None:
        """Generate one Manim scene, then send it to the harness immediately.

        ``_generate_one`` alone leaves the file completely unverified until
        the batch ``verifier_execution`` stage runs later in the pipeline —
        which meant a scene with a plain syntax error could sit unrewound
        long enough for ``renderer_manim`` to try (and crash on) it. This
        checks the file the instant it's written, retries once locally by
        feeding the harness's own diagnostics back as repair feedback, and
        otherwise logs the failure and moves on — the real
        ``verifier_execution`` pipeline stage remains the actual gate.
        """

        from .... import cfg

        stem = section.stem

        entry = next(
            (e for e in context.scene_plan if e.stem == stem),
            None,
        )

        attempt = 0

        while True:
            self._generate_one(context, section)

            artifact = context.code_artifacts.get(stem)
            if entry is None or artifact is None or artifact.path is None:
                # Generation itself already failed and logged a warning;
                # there is nothing on disk to send to the harness.
                return

            findings = check_scene_artifact(context, entry, gate=True)
            blocking = [
                f for f in findings
                if isinstance(f, dict) and str(f.get("status", "")).lower() == "fail"
            ]

            if not blocking:
                cfg.say(f"section {stem}: harness check passed")
                return

            if attempt >= MAX_HARNESS_CHECK_RETRIES:
                cfg.say(
                    f"section {stem}: harness check failed after "
                    f"{attempt + 1} attempt(s) — logging and continuing"
                )
                log = context.check_results.setdefault(
                    "generator_manim:preflight", []
                )
                log.extend(blocking)
                return

            attempt += 1
            first = str(
                blocking[0].get("detail") or blocking[0].get("message") or ""
            )[:110]
            cfg.say(
                f"section {stem}: harness check failed — {first} — retrying "
                f"({attempt}/{MAX_HARNESS_CHECK_RETRIES})"
            )

            diagnostics = [
                str(f.get("detail") or f.get("message") or "").strip()
                for f in blocking
                if isinstance(f, dict)
            ]
            context.repair_context.setdefault(stem, []).extend(
                d for d in diagnostics if d
            )

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        if not context.scene_plan:
            raise RuntimeError(
                "GeneratorManimPlugin received "
                "an empty scene plan."
            )

        _ensure_llm_keys()

        script = _build_script(
            context
        )

        if not script.sections:
            raise RuntimeError(
                "No script sections remain "
                "after scene-plan filtering."
            )

        outdir = (
            context.project_dir
            / MANIM_BUILD_DIR
        )

        outdir.mkdir(
            parents=True,
            exist_ok=True,
        )

        repair_context = getattr(
            context,
            "repair_context",
            {},
        )
        # HITL file is authoritative: if a stem is still listed as reject,
        # it must be regenerated even if repair_context is empty at the
        # start of a fresh harness invocation (the previous rewind fix was
        # not reliably re-rendering before assembly).  Read once per run.
        hitl_rejects: set[str] = set()
        try:
            import json as _json
            _hf = context.project_dir / "hitl_feedback.json" if context.project_dir else None
            if _hf and _hf.exists():
                _data = _json.loads(_hf.read_text(encoding="utf-8") or "{}")
                if isinstance(_data, dict):
                    for _k, _v in _data.items():
                        if isinstance(_v, dict) and _v.get("status") == "reject":
                            hitl_rejects.add(str(_k))
        except Exception:
            hitl_rejects = set()

        for section in script.sections:

            stem = section.stem

            py_file = (
                outdir
                / f"scene_{stem}.py"
            )

            is_repair = (
                stem in repair_context or stem in hitl_rejects
            )
            # If alignment was re-done (e.g. after voice re-synthesis,
            # narration 39s vs cached 5s code), the cached code is stale
            # even though hitl and repair_context are empty. Detect via
            # file mtimes: align JSON newer than code => must regenerate.
            if not is_repair and py_file.exists():
                try:
                    from .... import align as _align_mod
                    align_path = _align_mod.path_for(context.project_dir, stem)
                    if align_path.exists():
                        if align_path.stat().st_mtime > py_file.stat().st_mtime + 1.0:
                            is_repair = True
                except Exception:
                    pass

            # ----------------------------------------------------------
            # Cache handling
            # ----------------------------------------------------------

            if (
                py_file.exists()
                and not is_repair
            ):
                try:
                    cached_code = (
                        py_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    normalized = (
                        _normalize_manim19(
                            cached_code
                        )
                    )

                    if normalized != cached_code:
                        py_file.write_text(
                            normalized,
                            encoding="utf-8",
                        )

                    # Cached code is generated, not automatically accepted.
                    _record_code_artifact(
                        context,
                        stem,
                        py_file,
                        accepted=False,
                    )

                    from .... import cfg

                    cfg.say(
                        f"section {stem}: "
                        "cached, skipping"
                    )

                    continue

                except Exception:
                    # A corrupt/unreadable cache should be regenerated.
                    py_file.unlink(
                        missing_ok=True
                    )

            self._generate_and_check_one(
                context,
                section,
            )

        return context

    def _default_gate(self) -> bool:
        # Generation itself is not a quality gate.
        return False

    # ------------------------------------------------------------------
    # repair_router hooks
    # ------------------------------------------------------------------

    def revert_scene(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Remove exactly one generated scene."""

        plan = {
            str(entry.stem)
            for entry in context.scene_plan
        }

        if stem not in plan:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        _remove_generated_scene(
            context,
            stem,
        )

    def regenerate_one(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Regenerate exactly one Manim scene.

        This does NOT call run() and does NOT regenerate unrelated scenes.
        """

        if not context.scene_plan:
            raise RuntimeError(
                "Cannot repair Manim scene: "
                "scene plan is empty."
            )

        entry = next(
            (
                item
                for item in context.scene_plan
                if str(item.stem) == str(stem)
            ),
            None,
        )

        if entry is None:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        _ensure_llm_keys()

        script = _build_script(
            context
        )

        section = _find_section(
            script,
            stem,
        )

        if section is None:
            raise ValueError(
                f"Scene '{stem}' is not "
                "present in the current script."
            )

        # Scene-plan visual contract remains authoritative.
        section.anim = entry.anim

        # Generate only this section.
        self._generate_and_check_one(
            context,
            section,
        )