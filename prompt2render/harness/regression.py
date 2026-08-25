"""Verifier-driven repair with regression detection -- Tier 3 Phase 14.

The structural gap this closes (found by reading ``repair_router``/
``runner.py`` directly): SS15's implicit contract #2 already documents that
``regenerate_one``/``revert_scene`` are duck-typed and only 5 plugins
implement them (confirmed by grep: ``generator_code``, ``planner_llm``,
``planner_semantic``, ``renderer_manim``, ``renderer_stills``) -- "every
other repair target silently degrades to a full ``target.run(ctx)``." Any
such target can rewrite content for stems *other* than the one whose finding
triggered the repair. ``HarnessRunner.run()``'s existing rewind mechanism
only widens re-verification to stems named in its ``trigger`` set, built
from ``repair_context``/``render_artifacts`` diffs -- a whole-scope repair
that never touches either of those would leave an unrelated,
already-verified stem's downstream check_results silently stale forever,
with nothing in the existing triggers able to see it.

Honest scope note: ``reviser_script`` (repair target for ``pedagogy_review``
findings, ``ReviserScriptPlugin.run()`` revises the *entire* script -- see
``pedagogy._script_signature``, which already fingerprints the whole script
for that plugin's own narrower, self-referential "did my revision change
anything" check) is the one ``DEFAULT_TABLE`` entry without
``regenerate_one`` today, but it sits early enough in ``REGISTRY`` (before
``generator_code``/any renderer has ever run) that when its repair fires,
nothing downstream has produced stale artifacts yet -- so this specific
widening is inert for it today, a safety net rather than a fix for a
currently-live bug. The gap becomes load-bearing the moment a future
finding_type routes to a similarly full-``run()``-only plugin positioned
*after* code/render artifacts already exist, or if ``reviser_script``'s own
routing ever moves later -- this module makes that failure mode detectable
the day it becomes possible, rather than needing to be discovered by a
silent stale-render bug first (the same "build the reserved slot ahead of
its producer" discipline as F9's ``vlm_post_render_defect`` route).

This module supplies the detection half: a cheap, in-memory content
fingerprint per stem (:func:`scene_fingerprints`) and a pure diff
(:func:`changed_stems`). ``HarnessRunner`` (see ``runner.py``) calls both
around every stage and unions any silently-changed stem into its existing
``trigger`` set -- purely additive: it can only widen re-verification,
never narrow it, so it cannot destabilize the existing rewind/gate control
flow, only make it more correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .context import SceneContext


def scene_fingerprints(
    context: "SceneContext",
) -> dict[str, tuple]:
    """One cheap, hashable fingerprint per currently-known stem.

    Built only from already-in-memory ``ScenePlanEntry`` fields -- no file
    I/O, no re-parsing ``context.prompt`` (unlike ``pedagogy._script_
    signature``, which re-reads the script file every call; that cost is
    fine for ReviserScriptPlugin's own bounded revision loop but this
    function is called around *every* pipeline stage, so it stays as cheap
    as the in-memory representation allows). Covers exactly the fields a
    whole-script repair like ``reviser_script`` can rewrite.
    """

    fingerprints: dict[str, tuple] = {}

    for entry in context.scene_plan:
        stem = getattr(entry, "stem", None)

        # SceneContext.scene_plan is typed as list[ScenePlanEntry], but
        # nothing enforces that at runtime (several dummy-plugin tests put
        # plain strings there). An entry this function can't identify by
        # stem can't be usefully compared per-stem either way -- skip it
        # rather than crash a stage every future test/caller must otherwise
        # remember to avoid.
        if not stem:
            continue

        fingerprints[str(stem)] = (
            getattr(entry, "title", None),
            getattr(entry, "anim", None),
            getattr(entry, "narration_text", None),
        )

    return fingerprints


def changed_stems(
    before: dict[str, tuple],
    after: dict[str, tuple],
) -> set[str]:
    """Stems whose fingerprint differs between two snapshots.

    A stem present in only one snapshot (added or removed) counts as
    changed. Deliberately conservative: this feeds a re-verification
    *widening* decision, where over-including a stem costs one extra check
    and under-including one silently reintroduces the exact stale-evidence
    gap this module exists to close.
    """

    stems = set(before) | set(after)

    return {
        stem
        for stem in stems
        if before.get(stem) != after.get(stem)
    }


__all__ = [
    "changed_stems",
    "scene_fingerprints",
]
