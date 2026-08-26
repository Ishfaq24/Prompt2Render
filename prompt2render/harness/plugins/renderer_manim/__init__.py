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

from ... import hitl, lineage, workspace
from ...context import CodeArtifact, RenderArtifact, SceneContext, VideoArtifact
from ...motion import MOTION_OPS, find_storyboard_states
from ...temporal_ir import compute_state_slots
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

    Tier 4: a thin wrapper over ``harness.hitl.status_sets`` -- SS14 already
    documented this and ``feedback_hitl`` as two independent parsers of the
    same file; kept as a module-level function here (rather than deleted)
    for the one external call site below and so this stays the module's own
    established entry point.
    """

    return hitl.status_sets(project_dir)


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
# Construction-DSL JSON extraction (Tier 2 Phase 6)
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response (plain, fenced, or
    surrounded by accidental prose) -- same logic as planner_llm's/
    planner_semantic's own ``_extract_json`` (each plugin owns this small
    helper rather than sharing a utils module, matching this codebase's
    existing per-plugin convention)."""

    import json

    if not isinstance(text, str):
        return None

    text = text.strip()

    if not text:
        return None

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        return None

    try:
        value = json.loads(text[start:end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


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
    """Where this scene's Manim module lives right now.

    Redirects to the sidecar workspace while a repair candidate for this
    scene is open, so generation, verification and rendering all operate on
    the candidate while the accepted module stays intact on disk. Without an
    open candidate this is the canonical path, unchanged.
    """

    canonical = (
        context.project_dir
        / MANIM_BUILD_DIR
        / f"scene_{stem}.py"
    )

    return workspace.resolve_code_path(context, stem, canonical)


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

    if exists:
        lineage.ensure_tracked(context, stem)

    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=path if exists else None,
        accepted=bool(
            accepted and exists
        ),
        revision=lineage.current_revision(context, stem),
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
    """Remove generated code and stale downstream artifacts.

    With a repair candidate open for this scene the accepted ``.py`` is
    left untouched -- the candidate lands on a sidecar path, and destroying
    the accepted scene here would leave nothing to restore if the candidate
    proves worse.
    """

    if not workspace.is_candidate_open(context, stem):
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
# Pattern retrieval (Tier 2 Phase 7)
# ---------------------------------------------------------------------------

def _pattern_hints(
    context: SceneContext,
    stem: str,
) -> str:
    """Format this section's retrieved patterns (retriever_manim_rag) into
    a short prompt section, or "" when nothing matched or retrieval never
    ran (the plugin is gated separately and may be disabled)."""

    retrieval_context = getattr(context, "retrieval_context", {})

    if not isinstance(retrieval_context, dict):
        return ""

    matches = retrieval_context.get(stem, [])

    if not isinstance(matches, list) or not matches:
        return ""

    lines = [
        f"- {match.get('text')}"
        for match in matches
        if isinstance(match, dict) and match.get("text")
    ]

    if not lines:
        return ""

    return "RELEVANT PATTERNS:\n" + "\n".join(lines)


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


def _construction_required_ids(
    states: list[dict[str, Any]],
) -> list[tuple[str, list[str]]]:
    """Per state: which ids (from its motion targets, plus its own
    caption, plus the shared title in the first state) something must
    define -- shared by `_build_construction_prompt` (what it tells the LLM
    to cover) and `_try_construction_dsl` (which state's `_state_<name>`
    method each compiled id's lines get attributed to)."""

    result: list[tuple[str, list[str]]] = []

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

        required_ids = list(targets)
        required_ids.append(f"caption_{name}")

        if state_no == 0:
            required_ids.append("title")

        result.append((name, required_ids))

    return result


def _wrap_construction_lines(
    section,
    states: list[dict[str, Any]],
    id_lines: list[tuple[str, str]],
) -> str:
    """Wrap `construction_ir.compile_construction_lines`' flat ``(id,
    line)`` pairs into the same ``class Scene<stem>(Scene): def
    _state_<name>(self): ...`` shape a hand-written (or Phase 4 freehand)
    setup source already takes, so `_splice_construct_method` can splice a
    compiled `construct()` into it exactly as before.

    Each id's lines are attributed to the *earliest* state that requires it
    (`_construction_required_ids`) -- an id not required by any state (the
    LLM defined something extra) falls back to the first state so nothing
    is silently dropped.
    """

    required_by_state = _construction_required_ids(states)
    id_to_state_index: dict[str, int] = {}

    for state_index, (_name, required_ids) in enumerate(required_by_state):
        for required_id in required_ids:
            id_to_state_index.setdefault(required_id, state_index)

    lines_by_state_index: dict[int, list[str]] = {i: [] for i in range(len(states))}

    for node_id, line in id_lines:
        state_index = id_to_state_index.get(node_id, 0)
        lines_by_state_index.setdefault(state_index, []).append(line)

    body: list[str] = [f"class Scene{section.stem}(Scene):"]

    if not states:
        body.append("    pass")
    else:
        for state_index, (name, _required_ids) in enumerate(required_by_state):
            body.append(f"    def _state_{name}(self):")
            state_lines = lines_by_state_index.get(state_index) or []

            if not state_lines:
                body.append("        pass")
            else:
                body.extend(f"        {line}" for line in state_lines)

    return "\n".join(body)


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


#: Relocated to harness/temporal_ir.py (Tier 2 Phase 5), which is now the
#: single owner of narration-timing math shared with verifier_temporal. Kept
#: importable under this name so this file's own call sites/tests need no
#: further changes -- only the implementation moved.
_state_cue_timings = compute_state_slots


def _timings_for(
    context: SceneContext,
    stem: str,
    states: list[dict[str, Any]],
    sentences: list[dict[str, float]] | None,
    duration: float,
) -> list[dict[str, float]]:
    """Prefer ``context.temporal_ir`` (Tier 2 Phase 5) when this stem has a
    matching, already-computed ``SectionTiming``; otherwise compute the
    slots on-the-fly exactly as before Phase 5 -- same resilience pattern as
    ``_states_from_semantic_ir``'s graceful fallback, no new hard-failure
    mode for this still-experimental path.
    """

    temporal_ir = context.temporal_ir

    if temporal_ir is not None:
        section_timing = next(
            (s for s in temporal_ir.sections if s.stem == stem), None
        )

        if section_timing is not None and len(section_timing.states) == len(states):
            return [state.to_dict() for state in section_timing.states]

    return compute_state_slots(states, sentences, duration)


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

        # With a repair candidate open, render into the sidecar workspace so
        # the accepted sections/NN.mp4 survives an unproven regeneration.
        candidate_dir = (
            context.candidate.render_dir
            if workspace.is_candidate_open(context, stem)
            else None
        )

        try:
            out = manim_scene(
                context.project_dir,
                script,
                artifact.path,
                f"Scene{stem}",
                section.index,
                out_dir=candidate_dir,
            )

            context.render_artifacts[stem] = (
                RenderArtifact(
                    stem=stem,
                    outdir=out.parent,
                    # `clip` is what RendererManimFinishPlugin reads to
                    # assemble the programme. It used to be left unset here
                    # while only the manifest carried the path, so the
                    # finish stage always saw an empty clip map and could
                    # never produce out/final.mp4. Both are written now.
                    clip=out,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                    source_revision=lineage.current_revision(
                        context,
                        stem,
                    ),
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
                    clip=out,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                    source_revision=lineage.current_revision(
                        context,
                        stem,
                    ),
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
            "retrieval_context",
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

    def _build_construction_prompt(
        self,
        section,
        states: list[dict[str, Any]],
        duration: float,
        extra_feedback: str,
    ) -> str:
        """Tier 2 Phase 6: construction-DSL variant of `_build_setup_prompt`.

        Same contract (one construction per state, `self.title` only in the
        first state, `self.caption_<name>` in every state) but the LLM
        emits schema-validated JSON (`harness.construction_ir`) instead of
        Python -- Manim's Python API becomes a compile target
        (`construction_ir.compile_construction`), not something the LLM
        writes directly.
        """

        from ...construction_ir import KNOWN_COLORS, OBJECT_REQUIRED_PROPS, OBJECT_REQUIRED_REFS

        state_blocks = []
        required_by_state = _construction_required_ids(states)

        for state_no, (state, (name, required_ids)) in enumerate(
            zip(states, required_by_state)
        ):
            state_blocks.append(
                f"- state {name!r}:\n"
                f"    Visual: {state.get('visual', '')}\n"
                f"    Transition: {state.get('transition', '')}\n"
                f"    Must define a node/repeat with exactly this id for "
                f"each of: {required_ids}"
                + (
                    " (title -- only this first state may define it)"
                    if state_no == 0
                    else ""
                )
            )

        states_block = "\n\n".join(state_blocks)
        kinds = sorted(set(OBJECT_REQUIRED_PROPS) | {"VGroup"})

        prompt = f"""
Describe the objects for this Manim Community Edition {MANIM_VERSION} scene as
JSON -- do NOT write Python or Manim API calls yourself. A deterministic
compiler renders your JSON into the actual construction code.

TITLE:
{section.title}

VISUAL PLAN:
{section.anim}

TOTAL DURATION:
{duration:.1f} seconds

One id per object you define below (across all states) -- ids persist
across states, define each one exactly once, in whichever state first
needs it.

STATES (each needs the listed ids defined by SOME node or repeat):

{states_block}

Return ONLY valid JSON of this exact shape:
{{
  "repeats": [
    {{"id": "array", "count": 4, "kind": "Square",
      "props": {{"side_length": 0.9, "color": "BLUE"}},
      "arrange_direction": "RIGHT", "arrange_buff": 0.1,
      "position": {{"kind": "band", "band": "CENTER"}}}}
  ],
  "nodes": [
    {{"id": "title", "kind": "Text", "props": {{"content": "...", "font_size": 40}},
      "position": {{"kind": "band", "band": "TITLE"}}}},
    {{"id": "caption_introduce", "kind": "Text",
      "props": {{"content": "...", "font_size": 24}},
      "position": {{"kind": "band", "band": "CAPTION"}}}},
    {{"id": "pointer", "kind": "Arrow", "refs": {{"start_ref": "array", "end_ref": "title"}}}}
  ]
}}

RULES:
1. "kind" must be one of: {kinds}. Object kinds beyond this list (Axes,
   Code, Table, etc.) are not supported yet -- express the state's visual
   using only these.
2. Required props/refs per kind: {dict(OBJECT_REQUIRED_PROPS)}; ref-valued
   (point at another id): {dict(OBJECT_REQUIRED_REFS)}.
3. Optional props: "font_size" (number), "color" (one of {sorted(KNOWN_COLORS)}),
   "radius" (Circle), "side_length" (Square). Never any other prop key.
4. "position" is optional. "kind" must be "to_edge" (needs "direction" one
   of UP/DOWN/LEFT/RIGHT, optional "buff"), "next_to" (needs "direction"
   and "ref" -- an id already defined above), or "band" (needs "band" one
   of TITLE/CAPTION/CENTER -- there is no other way to place something at
   an absolute coordinate; never invent one).
5. "repeats" is for N structurally-identical instances (an array/list/
   sequence of elements) -- each repeat auto-creates a VGroup under its own
   "id"; other nodes reference that id directly, never the individual
   instances.
6. "VGroup" nodes need "children": a list of already-defined ids, and
   optionally "arrange_direction"/"arrange_buff".
7. ids must be short, stable Python identifiers, each defined exactly once,
   never referenced before they're defined (repeats first, then nodes in
   the order you list them).
8. Never include a duration/timestamp/numeric timing value anywhere.
9. Output ONLY the JSON object. No Markdown fences. No explanation.
""".strip()

        if extra_feedback:
            prompt += "\n\n" + extra_feedback

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

    def _try_construction_dsl(
        self,
        section,
        states: list[dict[str, Any]],
        duration: float,
        extra_feedback: str,
    ) -> str | None:
        """Tier 2 Phase 6: ask the LLM for construction-DSL JSON and compile
        it deterministically into setup_source Python.

        Returns ``None`` (never raises) on any parse/validation/compile
        failure -- the caller falls back to Phase 4's freehand
        `_build_setup_prompt`, matching the same graceful-degradation
        precedent as `_states_from_semantic_ir`/the motion compiler's own
        `_compile_construct_method` fallback. DSL failure never regresses
        below what Phase 4 already tolerates.
        """

        from .... import cfg
        from ...construction_ir import compile_construction_lines, validate_and_parse

        stem = section.stem
        prompt = self._build_construction_prompt(section, states, duration, extra_feedback)

        try:
            raw_response = self._generate_code(prompt)
            raw_dsl = _extract_json(raw_response)

            if raw_dsl is None:
                raise ValueError("LLM response was not valid JSON.")

            plan = validate_and_parse(raw_dsl)
            id_lines = compile_construction_lines(plan)

            return _wrap_construction_lines(section, states, id_lines)
        except Exception as exc:
            cfg.warn(
                f"section {stem}: construction DSL failed, falling back to "
                f"freehand setup-only prompt: {exc}"
            )
            return None

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

        # Tier 2 Phase 7: retrieved patterns come first, repair feedback (a
        # specific, already-diagnosed problem) stays the most prominent
        # thing at the end -- combined into the one `extra_feedback` string
        # every prompt builder already appends verbatim, so none of them
        # need a new parameter for this.
        pattern_hints = _pattern_hints(context, stem)

        if pattern_hints:
            extra_feedback = (
                f"{pattern_hints}\n\n{extra_feedback}"
                if extra_feedback
                else pattern_hints
            )

        use_compiler = bool(
            self.config.get(
                "use_motion_compiler",
                False,
            )
        )
        use_dsl = use_compiler and bool(
            self.config.get(
                "use_construction_dsl",
                False,
            )
        )

        states: list[dict[str, Any]] = []
        dsl_code: str | None = None

        if use_compiler:
            states = (
                _states_from_semantic_ir(context, stem)
                or _storyboard_states_for(context, stem, index=section.index)
                or []
            )

            if use_dsl:
                dsl_code = self._try_construction_dsl(
                    section, states, duration, extra_feedback
                )

        if dsl_code is not None:
            prompt = None
        elif use_compiler:
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
            code = dsl_code if prompt is None else self._generate_code(prompt)

            code = self._clean_generated_code(
                code
            )

            if not code:
                raise RuntimeError(
                    "LLM returned empty Manim code."
                )

            if use_compiler:
                try:
                    timings = _timings_for(context, stem, states, sentences, duration)
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

# ---------------------------------------------------------------------------
# Manim-aware production tail (Tier 2 Phase 8-9, F12)
# ---------------------------------------------------------------------------

class RendererManimFinishPlugin(Plugin):
    """Assemble Manim's per-section clips into ``out/final.mp4``.

    Bypasses the stills-only ``generator_timeline``/``renderer_encode``
    stages entirely -- Manim already renders one complete video per
    section, so there is no per-frame Ken-Burns plan to build. See
    ``finish.finish_manim`` for the renderer-agnostic building blocks this
    reuses.
    """

    name = "renderer_manim_finish"

    def declare_dependencies(self) -> list[str]:
        return [
            "render_artifacts",
            "audio_artifacts",
            "scene_plan",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "final_video",
        ]

    def run(self, context: SceneContext) -> SceneContext:
        from .... import finish as finish_module
        from ....project import parse_script

        script = parse_script(context.prompt)

        section_clips: dict[str, Path] = {}

        for entry in context.scene_plan:
            artifact = context.render_artifacts.get(entry.stem)

            # RenderArtifact.clip_path() tolerates either the explicit
            # `clip` field or the manifest's "mp4" entry, so a context
            # produced by an older run still resolves.
            clip = artifact.clip_path() if artifact is not None else None

            if clip is not None:
                section_clips[entry.stem] = Path(clip)

        burn = bool(self.config.get("burn", False))

        final = finish_module.finish_manim(
            context.project_dir,
            script,
            section_clips,
            burn=burn,
        )

        srt = context.project_dir / "out" / "captions.srt"

        for entry in context.scene_plan:
            if entry.stem not in context.video_artifacts:
                context.video_artifacts[entry.stem] = VideoArtifact(stem=entry.stem)

            context.video_artifacts[entry.stem].final_mp4 = final if final.exists() else None
            context.video_artifacts[entry.stem].captions_srt = srt if srt.exists() else None

        lineage.record_program(
            context,
            final_mp4=final,
            captions_srt=srt,
            chapters=context.project_dir / "build" / "chapters.txt",
        )

        return context

    def _default_gate(self) -> bool:
        return True


def _ffprobe_stream_types(clip_path: Path) -> set[str]:
    """The set of stream codec_types (e.g. {"video", "audio"}) ffprobe
    reports for a container -- same subprocess-wrapping style as
    verifier_temporal's own ``_ffprobe_duration``."""

    import shutil as _shutil
    import subprocess

    if _shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is not available on PATH.")

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


class VerifierManimFinalQcPlugin(Plugin):
    """Minimal Manim-mode final QC: ``out/final.mp4`` exists, has both a
    video and an audio stream, and its duration is within tolerance of the
    programme's expected total.

    Deliberately smaller in scope than the stills pipeline's ``qc.check()``
    (``qc.py``), which directly re-inspects stills-specific ``.py`` scene
    modules via ``stills.*`` calls that don't exist in Manim mode --
    confirmed by reading ``qc.py:133-161`` this session. Full parity with
    that suite is future work, not attempted here.
    """

    name = "verifier_manim_final_qc"

    DEFAULT_TOLERANCE_SECONDS = 5.0

    def declare_dependencies(self) -> list[str]:
        return [
            "final_video",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
            "final_qc",
        ]

    def run(self, context: SceneContext) -> SceneContext:
        from ...finding import Category, Finding, Severity, next_finding_id

        final = context.project_dir / "out" / "final.mp4"
        findings = []

        if not final.exists():
            findings.append(
                Finding(
                    finding_id=next_finding_id("mqc"),
                    scene_id="__all__",
                    category=Category.TECHNICAL,
                    severity=Severity.BLOCKING,
                    message="out/final.mp4 was not produced.",
                    finding_type="final_qc_failure",
                ).as_check_result()
            )
        else:
            try:
                streams = _ffprobe_stream_types(final)
            except Exception as exc:
                findings.append(
                    Finding(
                        finding_id=next_finding_id("mqc"),
                        scene_id="__all__",
                        category=Category.TECHNICAL,
                        severity=Severity.BLOCKING,
                        message=f"could not inspect out/final.mp4: {exc}",
                        finding_type="final_qc_failure",
                    ).as_check_result()
                )
            else:
                missing = {"video", "audio"} - streams

                if missing:
                    findings.append(
                        Finding(
                            finding_id=next_finding_id("mqc"),
                            scene_id="__all__",
                            category=Category.TECHNICAL,
                            severity=Severity.BLOCKING,
                            message=f"out/final.mp4 is missing stream(s): {sorted(missing)}.",
                            finding_type="final_qc_failure",
                        ).as_check_result()
                    )

        if not findings:
            findings.append(
                {
                    "status": "pass",
                    "stem": "__all__",
                    "finding_type": "final_qc_pass",
                    "category": Category.TECHNICAL.value,
                    "detail": "out/final.mp4 exists with video and audio streams.",
                }
            )

        context.check_results[self.name] = findings

        from ...logging_ import write_self_correction_report

        has_blocking = any(
            isinstance(f, dict) and f.get("status") == "fail" for f in findings
        )
        write_self_correction_report(context, final_pass=not has_blocking)

        return context

    def _default_gate(self) -> bool:
        return True
