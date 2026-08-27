"""No-progress and oscillation detection for the repair loop.

The repair budget (``RepairController.max_repairs_per_scene`` /
``max_total_repairs``, ``repair_controller.py``) already stops a scene from
being repaired forever. What it does not do is stop *early* when a repair
cycle is provably making no headway -- three consecutive cycles that each
propose byte-identical source, or that each leave the exact same blocking
finding types in place, still consume the full budget one cycle at a time
before the budget-exhausted decision finally ends it.

Precedent for this exact idea already exists one layer down, inside a
single LLM retry loop: ``scenes.py``'s ``_generate_matplotlib``/
``_generate_manim`` track a ``seen_digests``/``seen`` set of sha256 hashes
of prior LLM output specifically to detect "the model proposed the same
thing again." This module lifts that idea from "one plugin's internal
retry loop" to "the repair controller's cross-cycle history for one
scene", and adds the one thing a single sha256 set cannot see: an A->B->A
oscillation, where two distinct candidates keep replacing each other
without ever converging.

Design constraints, matching :mod:`scene_quality`:

1. Deterministic -- same sequence of candidates, same stop reason, every
   time. No timing, no randomness.
2. Conservative -- a tracker never *causes* a rejection; it only tells the
   repair controller that continuing is provably pointless. The existing
   regression rule in ``RepairController._judge`` is what actually decides
   accept/reject; this module answers a different question ("is it even
   worth trying again?"), consulted after a candidate is judged.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class StopReason(str, Enum):
    """Why the repair loop should stop trying for one scene."""

    NONE = "none"

    #: The last two cycles left the exact same set of blocking finding
    #: types in place -- the repair changed nothing that matters.
    NO_PROGRESS = "no_progress"

    #: A candidate's source is byte-identical to one already tried for this
    #: scene (not necessarily the immediately preceding one).
    IDENTICAL_CANDIDATE = "identical_candidate"

    #: The scene's finding-type signature has returned to a state already
    #: seen at least one cycle earlier (A -> B -> A), meaning repairs are
    #: cycling rather than converging.
    REPAIR_OSCILLATION = "repair_oscillation"


@dataclass(frozen=True)
class CandidateSignature:
    """What one repair candidate looked like, for cross-cycle comparison.

    ``code_sha256`` catches "the LLM proposed the same fix again" even
    before it is rendered/verified. ``finding_keys`` catches "the *outcome*
    is the same as before" even when the source text differs (e.g. two
    cosmetically different rewrites that both still trip the same
    verifier) -- the signal the brief's "repeated identical repair" and
    "same verification result repeatedly returned" scenarios both describe.
    """

    code_sha256: str
    finding_keys: frozenset[str]

    @staticmethod
    def of(source: str, finding_types: "list[str] | tuple[str, ...]") -> "CandidateSignature":
        digest = hashlib.sha256(
            (source or "").encode("utf-8", errors="replace")
        ).hexdigest()

        return CandidateSignature(
            code_sha256=digest,
            finding_keys=frozenset(str(f) for f in finding_types),
        )


@dataclass
class ConvergenceTracker:
    """Per-scene cross-cycle history, consulted once per repair cycle.

    One tracker instance is meant to live for the whole harness run (owned
    by :class:`~prompt2render.harness.repair_controller.RepairController`,
    matching how it already owns the cross-cycle ``repairs_per_scene``
    budget counter) so history accumulates across repair cycles for the
    same scene, not just within one.
    """

    #: ``{stem: [signature, signature, ...]}`` in chronological order.
    _history: dict[str, list[CandidateSignature]] = field(default_factory=dict)

    def record(self, stem: str, signature: CandidateSignature) -> StopReason:
        """Record one candidate's signature and report whether to stop.

        Recording happens unconditionally (even when the answer is
        ``NONE``) so the next call has the full history to compare
        against -- a tracker that only remembered "successful" attempts
        could not detect A->B->A oscillation across a rejected middle
        cycle.
        """

        history = self._history.setdefault(str(stem), [])

        reason = self._classify(history, signature)

        history.append(signature)

        return reason

    @staticmethod
    def _classify(
        history: list[CandidateSignature],
        signature: CandidateSignature,
    ) -> StopReason:
        if not history:
            return StopReason.NONE

        # Identical source already tried for this scene, at any point in
        # its history -- not just the immediately preceding cycle, since a
        # model can revert to an earlier bad answer after a detour.
        if any(prior.code_sha256 == signature.code_sha256 for prior in history):
            return StopReason.IDENTICAL_CANDIDATE

        # No progress: the immediately preceding cycle left exactly the
        # same blocking finding-type signature in place.
        if history[-1].finding_keys == signature.finding_keys:
            return StopReason.NO_PROGRESS

        # Oscillation: this exact finding-type signature was already seen
        # at least one cycle *before* the immediately preceding one (i.e.
        # A -> B -> A, not just A -> A).
        if any(
            prior.finding_keys == signature.finding_keys
            for prior in history[:-1]
        ):
            return StopReason.REPAIR_OSCILLATION

        return StopReason.NONE

    def reset(self, stem: str | None = None) -> None:
        """Clear history for one scene, or every scene."""

        if stem is None:
            self._history.clear()
            return

        self._history.pop(str(stem), None)


__all__ = [
    "CandidateSignature",
    "ConvergenceTracker",
    "StopReason",
]
