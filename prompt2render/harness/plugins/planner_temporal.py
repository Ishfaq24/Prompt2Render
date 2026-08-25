"""Deterministic temporal-IR builder -- Tier 2 Phase 5.

Builds ``SceneContext.temporal_ir`` from ``context.semantic_ir`` plus real
narration alignment, via ``temporal_ir.from_semantic_ir``. No LLM.

Deliberately advisory (``_default_gate() -> False``), unlike Phase 1-3's
hard gates on `animation_ir`/`semantic_ir`: `temporal_ir` has no consumer on
the shippable stills/freehand-Manim default path -- only the already-
experimental, opt-in Phase 4 motion-compiler branch in `renderer_manim`
consumes it, and that branch already falls back to computing timing
on-the-fly when `temporal_ir` is unavailable. Blocking the whole pipeline
over TemporalIR construction would risk destabilizing the shippable default
for a quantity nothing on that path needs.
"""
from __future__ import annotations

from ..context import SceneContext
from ..plugin import Plugin
from ..temporal_ir import from_semantic_ir
from ... import align


class PlannerTemporalPlugin(Plugin):
    name = "planner_temporal"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "semantic_ir", "narration"]

    def declare_effects(self) -> list[str]:
        return ["temporal_ir"]

    def run(self, context: SceneContext) -> SceneContext:
        semantic_ir = context.semantic_ir

        if semantic_ir is None:
            return context

        sentences_by_stem: dict[str, list[dict]] = {}

        for section in semantic_ir.sections:
            stem = section.stem
            sentences_by_stem[stem] = self._load_sentences(context, stem)

        context.temporal_ir = from_semantic_ir(semantic_ir, sentences_by_stem)

        return context

    def _load_sentences(self, context: SceneContext, stem: str) -> list[dict]:
        """Real alignment for one section, or ``[]`` when unavailable.

        ``align.load`` calls ``sys.exit()`` (a ``SystemExit``, not a
        catchable ``Exception``) when no alignment file exists on disk yet
        -- checking existence first avoids that landmine entirely rather
        than trying to catch it.
        """

        if context.project_dir is None:
            return []

        if not align.path_for(context.project_dir, stem).exists():
            return []

        data = align.load(context.project_dir, stem)
        sentences = data.get("sentences", []) if isinstance(data, dict) else []

        return sentences if isinstance(sentences, list) else []

    def _default_gate(self) -> bool:
        return False
