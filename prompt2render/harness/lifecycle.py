"""Explicit scene lifecycle state machine.

Before this module, a scene's "state" was scattered across several
independent, weaker signals: ``CodeArtifact.generated``/``.accepted``
booleans, an integer revision (``SceneContext.scene_versions``), and
per-finding ``"pass"/"warn"/"fail"/"skip"`` status strings buried in
``check_results``. None of those is a state machine -- nothing prevents
(or even notices) an impossible transition, and answering "is scene 07
currently mid-repair or already accepted?" required cross-referencing all
three.

This module adds :class:`SceneState` plus a validated transition function.
It does not replace any of those existing signals -- :func:`derive_state`
reads them to seed a state for scenes that predate this field, and
production code sites (the runner, the repair controller, the generator
plugins) additionally call :func:`transition` explicitly as those events
happen, so old projects and old tests continue to behave exactly as before
while gaining an explainable current state.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import SceneContext
    from .journal import EventJournal


class SceneState(str, Enum):
    """Where one scene currently sits in its own lifecycle."""

    PLANNED = "planned"
    GENERATED = "generated"
    RENDERING = "rendering"
    RENDERED = "rendered"
    VERIFYING = "verifying"
    FAILED = "failed"
    REPAIRING = "repairing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


#: Valid transitions, keyed by the state being left. A state absent from
#: this mapping (there are none currently) would mean "terminal, no further
#: transitions permitted" -- ACCEPTED and ROLLED_BACK are reachable dead
#: ends in the sense that nothing *must* follow them, but a fresh repair
#: cycle legitimately starts again from either (a previously-accepted scene
#: can still be re-repaired later if a downstream verifier changes its
#: mind), so both keep an outgoing edge back into REPAIRING.
TRANSITIONS: dict[SceneState, frozenset[SceneState]] = {
    SceneState.PLANNED: frozenset({SceneState.GENERATED}),
    SceneState.GENERATED: frozenset({SceneState.RENDERING}),
    SceneState.RENDERING: frozenset({SceneState.RENDERED, SceneState.FAILED}),
    SceneState.RENDERED: frozenset({SceneState.VERIFYING}),
    SceneState.VERIFYING: frozenset(
        {SceneState.ACCEPTED, SceneState.FAILED, SceneState.REJECTED}
    ),
    SceneState.FAILED: frozenset({SceneState.REPAIRING}),
    SceneState.REPAIRING: frozenset(
        {SceneState.RENDERING, SceneState.ACCEPTED, SceneState.ROLLED_BACK}
    ),
    SceneState.ACCEPTED: frozenset({SceneState.REPAIRING}),
    SceneState.REJECTED: frozenset({SceneState.ROLLED_BACK, SceneState.REPAIRING}),
    SceneState.ROLLED_BACK: frozenset({SceneState.REPAIRING}),
}


class InvalidTransition(ValueError):
    """Raised when a caller asks for a lifecycle transition that is not
    reachable from the scene's current state.

    Deliberately a ``ValueError`` subclass (matching the house convention
    already used by ``AnimationIRValidationError``/``ConstructionValidationError``
    /``SemanticPlanValidationError`` -- a specific, catchable exception
    subclassing the nearest built-in, not a project-wide base class).
    """

    def __init__(
        self,
        stem: str,
        from_state: SceneState,
        to_state: SceneState,
    ) -> None:
        self.stem = str(stem)
        self.from_state = from_state
        self.to_state = to_state

        allowed = sorted(s.value for s in TRANSITIONS.get(from_state, frozenset()))

        super().__init__(
            f"scene {stem!r}: cannot transition {from_state.value!r} -> "
            f"{to_state.value!r}; allowed from {from_state.value!r}: {allowed}"
        )


def current_state(context: "SceneContext", stem: str) -> SceneState:
    """The scene's currently-recorded state, deriving one if none exists yet."""

    raw = context.scene_states.get(str(stem))

    if raw is not None:
        try:
            return SceneState(raw)
        except ValueError:
            pass

    return derive_state(context, stem)


def derive_state(context: "SceneContext", stem: str) -> SceneState:
    """Infer a state for a scene that has no explicit ``scene_states`` entry.

    Existing projects, and every harness test written before this module
    existed, have code/render artifacts and ``check_results`` but no
    ``scene_states`` entry. Rather than requiring a migration step, this
    reconstructs a reasonable state from the same signals a human already
    reads to answer "where is this scene": ``CodeArtifact.generated``/
    ``.accepted``, whether a render exists, and whether any verifier
    recorded a blocking finding for it. This is intentionally a *read-only*
    inference -- it never writes back to ``scene_states``; only
    :func:`transition` does that.
    """

    from .scene_quality import SceneQuality

    stem = str(stem)
    code = context.code_artifacts.get(stem)

    if code is None or not getattr(code, "generated", False):
        return SceneState.PLANNED

    render = context.render_artifacts.get(stem)

    if render is None:
        return SceneState.GENERATED

    quality = SceneQuality.collect(context, stem)

    if not quality.has_evidence:
        return SceneState.RENDERED

    if quality.blocking > 0:
        return SceneState.FAILED

    return SceneState.ACCEPTED


def transition(
    context: "SceneContext",
    stem: str,
    to_state: SceneState,
    *,
    journal: "EventJournal | None" = None,
    reason: str = "",
) -> SceneState:
    """Move a scene to ``to_state``, validating against :data:`TRANSITIONS`.

    Raises :class:`InvalidTransition` rather than silently accepting an
    impossible transition -- the whole point of an explicit state machine
    is that a caller cannot, say, mark a scene ACCEPTED directly out of
    PLANNED and have that go unnoticed.
    """

    stem = str(stem)
    from_state = current_state(context, stem)

    if to_state not in TRANSITIONS.get(from_state, frozenset()):
        raise InvalidTransition(stem, from_state, to_state)

    context.scene_states[stem] = to_state.value

    if journal is not None:
        project = ""
        project_dir = getattr(context, "project_dir", None)

        if project_dir is not None:
            project = getattr(project_dir, "name", str(project_dir))

        journal.append(
            event_type="scene.state",
            project=project,
            scene_id=stem,
            revision=context.scene_versions.get(stem, 0),
            status="ok",
            payload={
                "from": from_state.value,
                "to": to_state.value,
                "reason": reason,
            },
        )

    return to_state


__all__ = [
    "TRANSITIONS",
    "InvalidTransition",
    "SceneState",
    "current_state",
    "derive_state",
    "transition",
]
