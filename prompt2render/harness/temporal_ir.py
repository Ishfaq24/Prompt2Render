"""TemporalIR -- typed, versioned, hashed, narration-authoritative timing.

Tier 2 Phase 5 (docs/ARCHITECTURE_AUDIT.md SS16-17: "Temporal compilation
(narration-authoritative)", the sibling stage to Phase 4's motion
compilation).

Unifies two timing computations that had drifted into separate, duplicated
implementations -- the same anti-pattern Phase 0.5 (F7, see :mod:`.timing`)
already fixed once for plain section duration:

- ``renderer_manim``'s per-state ``run_time``/``wait`` budget split (wired
  into the Phase 4 motion compiler) -- relocated here unchanged as
  :func:`compute_state_slots`.
- ``verifier_temporal``'s inline inter-sentence gap-sum loop, used for its
  cue-sync check -- reimplemented once, properly tested, as
  :func:`total_gap_seconds`, reusing :mod:`.timing`'s "no absolute
  timestamps, don't guess" philosophy rather than a third ad-hoc fallback
  chain.

Pure module -- no ``SceneContext``, no file I/O, no ``Plugin``. Real
alignment data is loaded by the caller (``harness/plugins/planner_temporal.py``
for the ``SceneContext``-wiring half, done separately once this type system
is proven, matching Phase 1's own precedent).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .semantic_plan import SemanticAnimationIR
from .timing import narration_span

#: Timing schema version. Independent of AnimationIR's/SemanticAnimationIR's
#: own schema versions -- this is a separately-evolving downstream layer.
TEMPORAL_SCHEMA_VERSION = "1.0"


@dataclass
class StateTiming:
    """One state's compiled run_time/wait budget."""

    name: str
    cue: int
    run_time: float
    wait: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cue": self.cue,
            "run_time": self.run_time,
            "wait": self.wait,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StateTiming":
        return StateTiming(
            name=str(data.get("name", "")),
            cue=int(data.get("cue", 0)),
            run_time=float(data.get("run_time", 0.0)),
            wait=float(data.get("wait", 0.0)),
        )


@dataclass
class SectionTiming:
    """One section's narration-authoritative timing."""

    index: int
    stem: str
    target_duration: float
    total_gap_seconds: float
    states: list[StateTiming] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "stem": self.stem,
            "target_duration": self.target_duration,
            "total_gap_seconds": self.total_gap_seconds,
            "states": [state.to_dict() for state in self.states],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SectionTiming":
        return SectionTiming(
            index=int(data.get("index", 0)),
            stem=str(data.get("stem", "")),
            target_duration=float(data.get("target_duration", 0.0)),
            total_gap_seconds=float(data.get("total_gap_seconds", 0.0)),
            states=[StateTiming.from_dict(s) for s in (data.get("states") or [])],
        )


@dataclass
class TemporalIR:
    """The whole video's narration-authoritative timing, typed and hashed.

    ``source_semantic_hash`` is provenance: the ``SemanticAnimationIR.
    semantic_hash`` this timing was derived from.
    """

    schema_version: str
    source_semantic_hash: str
    sections: list[SectionTiming] = field(default_factory=list)
    temporal_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_semantic_hash": self.source_semantic_hash,
            "sections": [section.to_dict() for section in self.sections],
            "temporal_hash": self.temporal_hash,
        }

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("temporal_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def temporal_ir_from_dict(data: dict[str, Any]) -> TemporalIR:
    """Round-trip deserialization of :meth:`TemporalIR.to_dict`."""

    return TemporalIR(
        schema_version=str(data.get("schema_version", "")),
        source_semantic_hash=str(data.get("source_semantic_hash", "")),
        sections=[SectionTiming.from_dict(s) for s in (data.get("sections") or [])],
        temporal_hash=str(data.get("temporal_hash", "")),
    )


def _sentence_start_end(sentence: Any) -> tuple[float, float] | None:
    """A sentence's ``(start, end)`` timestamps, or ``None`` when either is
    absent/unusable. Legacy dur-only sentences (no absolute timestamps)
    deliberately yield ``None`` here -- matching ``narration_span``'s own
    "don't guess a position from a duration alone" philosophy."""

    if not isinstance(sentence, dict):
        return None

    raw_start = sentence.get("start")
    raw_end = sentence.get("end")

    if raw_start is None or raw_end is None:
        return None

    try:
        start = float(raw_start)
        end = float(raw_end)
    except (TypeError, ValueError):
        return None

    return (start, end)


def total_gap_seconds(sentences: list[dict[str, Any]] | None) -> float:
    """Sum of inter-sentence silence -- the gap between one sentence's end
    and the next one's start, floored at zero per pair.

    Single source of truth, replacing ``verifier_temporal``'s own inline
    duplicate of this computation (see module docstring).
    """

    if not sentences:
        return 0.0

    items = [s for s in sentences if isinstance(s, dict)]
    total = 0.0

    for current, following in zip(items, items[1:]):
        current_pair = _sentence_start_end(current)
        following_pair = _sentence_start_end(following)

        if current_pair is None or following_pair is None:
            continue

        _, current_end = current_pair
        following_start, _ = following_pair

        total += max(0.0, following_start - current_end)

    return total


def compute_state_slots(
    states: list[dict[str, Any]],
    sentences: list[dict[str, float]] | None,
    duration: float,
) -> list[dict[str, float]]:
    """Split narration time into a run_time/wait budget per state.

    Relocated unchanged from ``renderer_manim._state_cue_timings`` (Tier 2
    Phase 4) -- this module is now its single owner. Each state's ``cue``
    resolves to a narration start timestamp. States are partitioned into
    consecutive slots bounded by the next state's start, with the final
    slot's boundary telescoping to the TRUE narration end
    (``sentences[-1]["end"]``) rather than ``duration`` -- ``duration`` (as
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
        # resolve to real timestamps (e.g. no sentence data at all) -- floor
        # it so the state still gets a positive run_time. Real sentence data
        # never triggers this, so the telescoping sum stays exact above.
        if slot <= 0.0:
            slot = 0.1

        run_time = slot * 0.85
        wait = slot - run_time

        timings.append({"run_time": run_time, "wait": wait})

    return timings


def build_section_timing(
    index: int,
    stem: str,
    states: list[dict[str, Any]],
    sentences: list[dict[str, Any]] | None,
    duration: float,
) -> SectionTiming:
    """Combine :func:`compute_state_slots` + :func:`total_gap_seconds` +
    :func:`~.timing.narration_span` into one typed :class:`SectionTiming`.

    ``states`` need only carry ``name``/``cue`` -- timing depends solely on
    cue positions, never on motion/visual content.
    """

    slots = compute_state_slots(states, sentences, duration)

    return SectionTiming(
        index=index,
        stem=stem,
        target_duration=narration_span(sentences or []),
        total_gap_seconds=total_gap_seconds(sentences),
        states=[
            StateTiming(
                name=str(state.get("name", "")),
                cue=int(state.get("cue", 0)),
                run_time=slot["run_time"],
                wait=slot["wait"],
            )
            for state, slot in zip(states, slots)
        ],
    )


def from_semantic_ir(
    semantic_ir: SemanticAnimationIR,
    sentences_by_stem: dict[str, list[dict[str, Any]]],
) -> TemporalIR:
    """Build a :class:`TemporalIR` from a validated
    :class:`~.semantic_plan.SemanticAnimationIR`.

    ``sentences_by_stem`` is already-loaded alignment data per section stem
    (an empty list for a stem with no alignment on disk yet) -- this
    function itself does no file I/O, matching :mod:`.animation_ir`'s and
    :mod:`.semantic_plan`'s own "pure module" convention. A section missing
    from ``sentences_by_stem`` degrades to ``target_duration=0``,
    ``total_gap_seconds=0`` rather than raising -- narration alignment may
    genuinely not exist yet for a section without that being a structural
    error in the semantic plan itself.
    """

    sections: list[SectionTiming] = []

    for section in semantic_ir.sections:
        sentences = sentences_by_stem.get(section.stem, [])
        state_dicts = [{"name": s.name, "cue": s.cue} for s in section.states]

        duration = narration_span(sentences) if sentences else 0.0

        sections.append(
            build_section_timing(
                section.index,
                section.stem,
                state_dicts,
                sentences,
                duration,
            )
        )

    ir = TemporalIR(
        schema_version=TEMPORAL_SCHEMA_VERSION,
        source_semantic_hash=semantic_ir.semantic_hash,
        sections=sections,
    )
    ir.temporal_hash = ir.compute_hash()

    return ir
