"""AnimationIR -- typed, renderer-neutral, versioned, hashed intermediate
representation between the storyboard and motion/temporal compilation.

Phase 1 of the Tier 1 migration (``docs/ARCHITECTURE_AUDIT.md`` SS17). Today
the only representation of "what should this section do" is
``SceneContext.storyboard_plan``, an untyped ``dict[str, Any]`` produced by
``planner_llm``. This module gives that shape typed, versioned, content-hashed
dataclasses plus a pure conversion function -- with no dependency on
``SceneContext``, ``Plugin``, or the DAG loader. Wiring this into the pipeline
(a new ``SceneContext`` field, a bridge/validation-gate plugin, repair
routing) is Phase 2, done separately once this type system is proven against
real storyboard output.

The motion-op vocabulary is reused as-is from :mod:`.motion` rather than
redefined here, so the two cannot drift apart (the exact failure mode fixed
in Phase 0.5, F7, for narration-duration definitions). A target/into/anchor
value must be a valid Python identifier -- this module treats that purely as
a safe, portable convention for symbolic addressing, not as a promise about
becoming a Python attribute; that association is Manim-specific and belongs
to ``renderer_manim``, not to a renderer-neutral IR.

Narration timing is deliberately excluded. The target architecture treats
"Temporal compilation (narration-authoritative)" as a separate downstream
stage from AnimationIR, and ``motion.py`` already establishes that timing is
never part of the motion vocabulary. A section here carries its ``stem`` so a
later stage can join narration data by lookup rather than this module
duplicating it (the "duplicate responsibilities" pattern the audit flags in
SS14).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .motion import MOTION_OPS, validate_motion_ops

#: IR schema version. Bump when the shape of AnimationIR/SectionIR/StateIR/
#: MotionOpIR changes in a way a consumer would need to branch on.
IR_SCHEMA_VERSION = "1.0"


@dataclass
class MotionOpIR:
    """One motion primitive applied to one or more symbolic targets.

    ``op`` and the keys of ``params`` are validated against
    :data:`motion.MOTION_OPS` at construction time via :func:`from_dict`, not
    here -- this dataclass itself stays a plain value holder so a caller that
    already has validated data (e.g. round-tripping ``to_dict``/``from_dict``)
    doesn't pay for revalidation.
    """

    op: str
    params: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "params": dict(self.params)}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MotionOpIR":
        return MotionOpIR(
            op=str(data.get("op", "")),
            params={
                str(k): str(v) for k, v in dict(data.get("params") or {}).items()
            },
        )


@dataclass
class StateIR:
    """One progressive visual state within a section."""

    name: str
    cue: int
    visual: str
    transition: str
    values: list[Any] = field(default_factory=list)
    ops: list[MotionOpIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cue": self.cue,
            "visual": self.visual,
            "transition": self.transition,
            "values": list(self.values),
            "ops": [op.to_dict() for op in self.ops],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StateIR":
        return StateIR(
            name=str(data.get("name", "")),
            cue=int(data.get("cue", 0)),
            visual=str(data.get("visual", "")),
            transition=str(data.get("transition", "")),
            values=list(data.get("values") or []),
            ops=[MotionOpIR.from_dict(op) for op in (data.get("ops") or [])],
        )


@dataclass
class SectionIR:
    """One section (scene) of the video."""

    index: int
    stem: str
    title: str
    states: list[StateIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "stem": self.stem,
            "title": self.title,
            "states": [state.to_dict() for state in self.states],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SectionIR":
        return SectionIR(
            index=int(data.get("index", 0)),
            stem=str(data.get("stem", "")),
            title=str(data.get("title", "")),
            states=[StateIR.from_dict(s) for s in (data.get("states") or [])],
        )


@dataclass
class AnimationIR:
    """The whole video's animation structure, typed and content-hashed.

    ``source_storyboard_version``/``source_hash`` are provenance: they record
    which ``storyboard_plan`` (by its own ``version``/``prompt_sha256``) this
    IR was derived from, so a later staleness check (in the spirit of the
    verifier_semantic preview-freshness fix, F10) has something to compare
    against.
    """

    schema_version: str
    source_storyboard_version: str
    source_hash: str
    sections: list[SectionIR] = field(default_factory=list)
    ir_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_storyboard_version": self.source_storyboard_version,
            "source_hash": self.source_hash,
            "sections": [section.to_dict() for section in self.sections],
            "ir_hash": self.ir_hash,
        }

    def compute_hash(self) -> str:
        """Content hash over everything except ``ir_hash`` itself.

        Full sha256 hex digest, matching the convention already used for
        ``storyboard_plan["prompt_sha256"]`` (``planner_llm._sha256_text``)
        rather than the unrelated truncated hash scheme ``repair_router``
        uses for its own cycle-tracking.
        """

        payload = self.to_dict()
        payload.pop("ir_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ir_from_dict(data: dict[str, Any]) -> AnimationIR:
    """Round-trip deserialization of :meth:`AnimationIR.to_dict` output."""

    return AnimationIR(
        schema_version=str(data.get("schema_version", "")),
        source_storyboard_version=str(data.get("source_storyboard_version", "")),
        source_hash=str(data.get("source_hash", "")),
        sections=[SectionIR.from_dict(s) for s in (data.get("sections") or [])],
        ir_hash=str(data.get("ir_hash", "")),
    )


def from_storyboard_plan(storyboard_plan: dict[str, Any]) -> AnimationIR:
    """Convert a real ``storyboard_plan`` (as produced by ``planner_llm``,
    e.g. ``build/harness/storyboard.json``) into an :class:`AnimationIR`.

    Raises ``ValueError`` with precise ``"Section {index}, state {n}: ..."``
    messages on any invalid motion op, mirroring
    ``planner_llm._validate_sections`` -- a future Phase 2 gate plugin can
    turn these directly into ``Finding``s without re-deriving the wording.

    Tolerates the same degraded shapes ``motion.find_storyboard_states``
    already tolerates: a section missing ``stem`` (deterministic-fallback
    sections have historically omitted it) and a state missing ``motion``
    entirely (also fallback-only) both fall back to an empty default rather
    than raising.
    """

    raw_sections = storyboard_plan.get("sections")

    if not isinstance(raw_sections, list):
        raise ValueError("storyboard_plan.sections must be a list.")

    sections: list[SectionIR] = []

    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            raise ValueError("storyboard_plan.sections entries must be objects.")

        index = raw_section.get("index")
        stem = str(raw_section.get("stem") or "")
        title = str(raw_section.get("title", ""))
        raw_states = raw_section.get("states")

        if not isinstance(raw_states, list):
            raise ValueError(f"Section {index}: states must be a list.")

        states: list[StateIR] = []

        for state_no, raw_state in enumerate(raw_states):
            if not isinstance(raw_state, dict):
                raise ValueError(
                    f"Section {index}, state {state_no}: state must be an object."
                )

            motion = raw_state.get("motion") or []
            errors = validate_motion_ops(motion)

            if errors:
                raise ValueError(
                    f"Section {index}, state {state_no}: " + " ".join(errors)
                )

            ops = [
                MotionOpIR(
                    op=str(op["op"]),
                    params={
                        key: str(op[key])
                        for key in MOTION_OPS[op["op"]]
                    },
                )
                for op in motion
            ]

            states.append(
                StateIR(
                    name=str(raw_state.get("name", "")),
                    cue=int(raw_state.get("cue", 0)),
                    visual=str(raw_state.get("visual", "")),
                    transition=str(raw_state.get("transition", "")),
                    values=list(raw_state.get("values") or []),
                    ops=ops,
                )
            )

        sections.append(
            SectionIR(index=index, stem=stem, title=title, states=states)
        )

    ir = AnimationIR(
        schema_version=IR_SCHEMA_VERSION,
        source_storyboard_version=str(storyboard_plan.get("version", "")),
        source_hash=str(storyboard_plan.get("prompt_sha256", "")),
        sections=sections,
    )
    ir.ir_hash = ir.compute_hash()

    return ir
