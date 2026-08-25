"""SemanticAnimationIR -- typed, versioned, hashed pedagogical phase model
built on top of :mod:`.animation_ir`.

Phase 3 of the Tier 1 migration (``docs/ARCHITECTURE_AUDIT.md`` SS16-17). The
target architecture names a stage, "Semantic animation planning", between
AnimationIR and motion/temporal compilation, described only as
``CONTEXT->ANTICIPATION->ACTION->CONSEQUENCE->HOLD`` -- one line, defined
nowhere else in the repo. This module gives that model a concrete meaning:

- CONTEXT -- ops that establish what's already true as a state opens
  (entrances for supporting objects), before the state's defining change.
- ANTICIPATION -- ops that draw attention to what's about to change, before
  it changes. Optional.
- ACTION -- the state's defining pedagogical event. Every non-hold state
  needs at least one (mirrors the existing "every state needs real content"
  principle behind ``planner_llm.MIN_STATES``).
- CONSEQUENCE -- ops showing the result/implication of the action. Optional.
- HOLD -- not an op (there is nothing to animate); a per-*state* flag
  (``SemanticStateIR.hold``) meaning this state deliberately adds no new
  ops, letting the prior state's result sit while narration continues.
  Exempts that state from the "needs an ACTION beat" rule.

Kept as a module/type separate from :class:`~.animation_ir.AnimationIR`
rather than added onto it: the target architecture draws
``AnimationIR -> Semantic animation planning`` as two distinct arrows (a
transformation *from* the structural IR, not an in-place mutation of it), so
Phase 1's renderer-neutral IR stays untouched. A beat may only reference an
identifier (``target``/``into``/``anchor``) already present somewhere in the
source ``AnimationIR`` section it belongs to -- this module can choreograph
existing objects into a richer phase structure (using the full, Phase-3-
expanded :data:`motion.MOTION_OPS` vocabulary) but cannot invent new ones;
ownership of *what exists* stays with the storyboard/``generator_code``
stage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .animation_ir import AnimationIR, MotionOpIR
from .motion import MOTION_OPS, validate_motion_ops

#: Semantic-plan schema version. Independent of AnimationIR's own
#: schema_version -- this is a downstream, separately-evolving layer.
SEMANTIC_SCHEMA_VERSION = "1.0"


class Phase(str, Enum):
    CONTEXT = "CONTEXT"
    ANTICIPATION = "ANTICIPATION"
    ACTION = "ACTION"
    CONSEQUENCE = "CONSEQUENCE"


class SemanticPlanValidationError(ValueError):
    """``annotate`` failed to validate one section/state/beat.

    A plain ``ValueError`` (so ``pytest.raises(ValueError, ...)`` keeps
    working) plus the ``index``/``stem``/``state_no`` in scope when the
    error was raised, for precise ``Finding`` scoping -- same pattern as
    ``animation_ir.AnimationIRValidationError``.
    """

    def __init__(
        self,
        message: str,
        *,
        index: int | None = None,
        stem: str = "",
        state_no: int | None = None,
    ) -> None:
        super().__init__(message)
        self.index = index
        self.stem = stem
        self.state_no = state_no


@dataclass
class PhasedOpIR:
    """One motion op tagged with the pedagogical beat it belongs to."""

    phase: str
    op: MotionOpIR

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "op": self.op.to_dict()}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PhasedOpIR":
        return PhasedOpIR(
            phase=str(data.get("phase", "")),
            op=MotionOpIR.from_dict(data.get("op") or {}),
        )


@dataclass
class SemanticStateIR:
    name: str
    cue: int
    hold: bool = False
    beats: list[PhasedOpIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cue": self.cue,
            "hold": self.hold,
            "beats": [beat.to_dict() for beat in self.beats],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SemanticStateIR":
        return SemanticStateIR(
            name=str(data.get("name", "")),
            cue=int(data.get("cue", 0)),
            hold=bool(data.get("hold", False)),
            beats=[PhasedOpIR.from_dict(b) for b in (data.get("beats") or [])],
        )


@dataclass
class SemanticSectionIR:
    index: int
    stem: str
    title: str
    states: list[SemanticStateIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "stem": self.stem,
            "title": self.title,
            "states": [state.to_dict() for state in self.states],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SemanticSectionIR":
        return SemanticSectionIR(
            index=int(data.get("index", 0)),
            stem=str(data.get("stem", "")),
            title=str(data.get("title", "")),
            states=[SemanticStateIR.from_dict(s) for s in (data.get("states") or [])],
        )


@dataclass
class SemanticAnimationIR:
    """The whole video's pedagogical phase structure, typed and hashed.

    ``source_ir_hash`` is provenance: the ``AnimationIR.ir_hash`` this plan
    was derived from, so a later staleness check has something to compare
    against (same spirit as ``AnimationIR.source_hash``).
    """

    schema_version: str
    source_ir_hash: str
    sections: list[SemanticSectionIR] = field(default_factory=list)
    semantic_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_ir_hash": self.source_ir_hash,
            "sections": [section.to_dict() for section in self.sections],
            "semantic_hash": self.semantic_hash,
        }

    def compute_hash(self) -> str:
        payload = self.to_dict()
        payload.pop("semantic_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def semantic_ir_from_dict(data: dict[str, Any]) -> SemanticAnimationIR:
    """Round-trip deserialization of :meth:`SemanticAnimationIR.to_dict`."""

    return SemanticAnimationIR(
        schema_version=str(data.get("schema_version", "")),
        source_ir_hash=str(data.get("source_ir_hash", "")),
        sections=[
            SemanticSectionIR.from_dict(s) for s in (data.get("sections") or [])
        ],
        semantic_hash=str(data.get("semantic_hash", "")),
    )


def _known_identifiers(section) -> set[str]:
    """Every target/into/anchor identifier already used by this section's
    AnimationIR ops -- the allowed universe for this section's beats."""

    identifiers: set[str] = set()

    for state in section.states:
        for op in state.ops:
            identifiers.update(op.params.values())

    return identifiers


def annotate(
    animation_ir: AnimationIR,
    raw: dict[str, Any],
) -> SemanticAnimationIR:
    """Validate and convert the LLM's raw phase-tagging response.

    ``raw`` shape (flat op dicts, matching the storyboard's existing
    ``motion`` entry convention rather than AnimationIR's nested
    ``{"op": ..., "params": {...}}`` -- simpler for the LLM to author,
    consistent with what it already writes for ``storyboard_plan``)::

        {"sections": [{"index": 1, "states": [
            {"name": "introduce", "hold": false, "beats": [
                {"phase": "CONTEXT", "op": "Create", "target": "circle"},
                {"phase": "ACTION", "op": "Transform", "target": "circle",
                 "into": "square"},
            ]},
        ]}]}

    Every section and state present in ``animation_ir`` must have a matching
    entry (completeness is enforced, mirroring
    ``planner_llm._validate_sections``'s section-index coverage check) --
    this is not a partial annotation. Raises
    :class:`SemanticPlanValidationError` on any structural problem, an
    unknown phase name, a beat that fails :func:`motion.validate_motion_ops`,
    a beat referencing an identifier not already present in the source
    section, or a non-hold state with zero ACTION beats.
    """

    raw_sections = raw.get("sections")

    if not isinstance(raw_sections, list):
        raise SemanticPlanValidationError("raw.sections must be a list.")

    raw_by_index: dict[int, dict[str, Any]] = {}

    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise SemanticPlanValidationError("raw.sections entries must be objects.")

        index = raw_section.get("index")
        raw_by_index[index] = raw_section

    sections: list[SemanticSectionIR] = []

    for source_section in animation_ir.sections:
        raw_section = raw_by_index.get(source_section.index)

        if raw_section is None:
            raise SemanticPlanValidationError(
                f"Section {source_section.index}: missing from semantic plan.",
                index=source_section.index,
                stem=source_section.stem,
            )

        known = _known_identifiers(source_section)
        raw_states = raw_section.get("states")

        if not isinstance(raw_states, list):
            raise SemanticPlanValidationError(
                f"Section {source_section.index}: states must be a list.",
                index=source_section.index,
                stem=source_section.stem,
            )

        raw_state_by_name = {
            s.get("name"): s for s in raw_states if isinstance(s, dict)
        }

        states: list[SemanticStateIR] = []

        for source_state in source_section.states:
            raw_state = raw_state_by_name.get(source_state.name)

            if raw_state is None:
                raise SemanticPlanValidationError(
                    f"Section {source_section.index}, state {source_state.name!r}: "
                    "missing from semantic plan.",
                    index=source_section.index,
                    stem=source_section.stem,
                )

            hold = bool(raw_state.get("hold", False))
            raw_beats = raw_state.get("beats") or []

            if not isinstance(raw_beats, list):
                raise SemanticPlanValidationError(
                    f"Section {source_section.index}, state {source_state.name!r}: "
                    "beats must be a list.",
                    index=source_section.index,
                    stem=source_section.stem,
                )

            beats: list[PhasedOpIR] = []
            has_action = False

            for beat_no, raw_beat in enumerate(raw_beats):
                if not isinstance(raw_beat, dict):
                    raise SemanticPlanValidationError(
                        f"Section {source_section.index}, state "
                        f"{source_state.name!r}, beat {beat_no}: must be an object.",
                        index=source_section.index,
                        stem=source_section.stem,
                        state_no=beat_no,
                    )

                phase = raw_beat.get("phase")

                if phase not in {p.value for p in Phase}:
                    raise SemanticPlanValidationError(
                        f"Section {source_section.index}, state "
                        f"{source_state.name!r}, beat {beat_no}: unknown phase "
                        f"{phase!r}; must be one of {sorted(p.value for p in Phase)}.",
                        index=source_section.index,
                        stem=source_section.stem,
                        state_no=beat_no,
                    )

                op_dict = {k: v for k, v in raw_beat.items() if k != "phase"}
                errors = validate_motion_ops([op_dict])

                if errors:
                    raise SemanticPlanValidationError(
                        f"Section {source_section.index}, state "
                        f"{source_state.name!r}, beat {beat_no}: "
                        + " ".join(errors),
                        index=source_section.index,
                        stem=source_section.stem,
                        state_no=beat_no,
                    )

                op_name = op_dict["op"]
                params = {key: str(op_dict[key]) for key in MOTION_OPS[op_name]}
                unknown = set(params.values()) - known

                if unknown:
                    raise SemanticPlanValidationError(
                        f"Section {source_section.index}, state "
                        f"{source_state.name!r}, beat {beat_no}: references "
                        f"identifier(s) {sorted(unknown)} not present in the "
                        "source AnimationIR section.",
                        index=source_section.index,
                        stem=source_section.stem,
                        state_no=beat_no,
                    )

                if phase == Phase.ACTION.value:
                    has_action = True

                beats.append(
                    PhasedOpIR(phase=phase, op=MotionOpIR(op=op_name, params=params))
                )

            if not hold and not has_action:
                raise SemanticPlanValidationError(
                    f"Section {source_section.index}, state "
                    f"{source_state.name!r}: needs at least one ACTION beat "
                    "(or hold: true).",
                    index=source_section.index,
                    stem=source_section.stem,
                )

            states.append(
                SemanticStateIR(
                    name=source_state.name,
                    cue=source_state.cue,
                    hold=hold,
                    beats=beats,
                )
            )

        sections.append(
            SemanticSectionIR(
                index=source_section.index,
                stem=source_section.stem,
                title=source_section.title,
                states=states,
            )
        )

    plan = SemanticAnimationIR(
        schema_version=SEMANTIC_SCHEMA_VERSION,
        source_ir_hash=animation_ir.ir_hash,
        sections=sections,
    )
    plan.semantic_hash = plan.compute_hash()

    return plan


def _default_state_dict(state) -> dict[str, Any]:
    """Every existing op tagged ACTION. A state with zero AnimationIR ops
    has nothing to tag and no identifiers to reference -- marked ``hold``
    instead of fabricating a placeholder op."""

    if not state.ops:
        return {"name": state.name, "hold": True, "beats": []}

    return {
        "name": state.name,
        "hold": False,
        "beats": [
            {"phase": Phase.ACTION.value, "op": op.op, **op.params}
            for op in state.ops
        ],
    }


def default_semantic_plan(animation_ir: AnimationIR) -> SemanticAnimationIR:
    """Deterministic fallback: every existing op tagged ACTION, no
    enrichment. Used when the LLM is unavailable or fails -- trivially
    satisfies :func:`annotate`'s completeness/ACTION-beat rules since it's
    built directly from ``animation_ir`` rather than round-tripped through
    JSON.
    """

    raw = {
        "sections": [
            {
                "index": section.index,
                "states": [_default_state_dict(state) for state in section.states],
            }
            for section in animation_ir.sections
        ]
    }

    return annotate(animation_ir, raw)
