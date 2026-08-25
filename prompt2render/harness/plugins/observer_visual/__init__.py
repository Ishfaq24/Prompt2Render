"""Visual observation -- Tier 3 Phases 11-12 (F3 closed-loop visual
grounding; motion traces).

The target architecture (docs/ARCHITECTURE_AUDIT.md SS16) names this as its
own pipeline stage, distinct from verification:

    Executable artifact -> rendered video
        -> Visual observation (frame sampling, object/motion traces)
        -> Multi-verifier: semantic | temporal | spatial | motion | ...

This plugin IS that stage, in full -- both named sub-concerns ("frame
sampling" and "object/motion traces") are grouped under the one diagram box,
so both live in this one plugin rather than two:

- Presence (Phase 11): samples a rendered Manim clip and measures
  non-background pixel presence via ``visual_observe.observe_clip`` (cv2, no
  LLM/VLM), writing ``RenderArtifact.audit``.
- Motion (Phase 12): samples each state's run_time start/end and measures
  frame-to-frame change via ``visual_observe.observe_motion``, writing
  ``RenderArtifact.motion``.

Neither half decides pass/fail here -- this plugin produces evidence, the
same role ``renderer_stills`` already plays for the SceneKit audit on the
stills path. Two different verifiers turn that evidence into findings:
``verifier_spatial`` reads ``.audit`` (Phase 11; unmodified, see below),
``verifier_motion`` reads ``.motion`` (Phase 12; new, see its own
docstring for why the threshold decision lives there and not here).

Concretely, the presence half populates ``RenderArtifact.audit`` for Manim
stems, using the exact record shape ``verifier_spatial`` already parses --
so this also resolves F4 (``verifier_spatial`` unconditionally reporting
``skip`` on the Manim path, because ``renderer_manim`` never set ``.audit``)
as a direct side effect, without any change to ``verifier_spatial``'s own
contract beyond a one-line message-wording fix (see its docstring).

No-ops for stills stems: ``RendererStillsPlugin`` already populates a real
audit record via ``scenekit.audit()`` (matplotlib-artist bbox math -- the
right tool for that renderer, unrelated machinery, and one with no
per-section clip to diff for motion either). This plugin only fills the gap
where ``RenderArtifact.audit`` is still ``None``, so it is safe to enable
unconditionally without disturbing the stills default path -- though in
practice it is only meaningful in ``--manim`` mode and is toggled off by
default the same way the other Manim-only plugins are (F13's precedent).

Deliberately advisory (``_default_gate() -> False``) and deliberately
produces no ``check_results`` of its own -- the two verifiers above already
do that from the evidence this plugin writes, so a second finding set here
would just double-report the same evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .... import visual_observe
from ...context import SceneContext
from ...plugin import Plugin


class ObserverVisualPlugin(Plugin):
    """Samples rendered Manim clips and records deterministic content-presence."""

    name = "observer_visual"

    def declare_dependencies(self) -> list[str]:
        return [
            "render_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        # Mutates RenderArtifact.audit in place rather than declaring
        # render_artifacts as an owned effect -- declaring it would collide
        # with whichever renderer (renderer_stills/renderer_manim) already
        # owns that effect, since only "check_results" is a mergeable
        # effect. This mirrors verifier_execution's existing, documented
        # in-place-mutation precedent (F15) rather than introducing a new
        # kind of contract gap.
        return []

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        min_ink_fraction = float(
            self.config.get(
                "min_ink_fraction",
                visual_observe.DEFAULT_MIN_INK_FRACTION,
            )
        )

        fallback_count = int(
            self.config.get(
                "sample_fallback_count",
                visual_observe.DEFAULT_FALLBACK_COUNT,
            )
        )

        section_timings: dict[str, Any] = {}

        if context.temporal_ir is not None:
            section_timings = {
                section.stem: section
                for section in context.temporal_ir.sections
            }

        for stem, artifact in context.render_artifacts.items():

            if getattr(artifact, "audit", None) is not None:
                # Already observed (stills path's own scenekit audit, or a
                # previous run) -- don't overwrite or double-report.
                continue

            clip_path = self._clip_path(artifact)

            if clip_path is None:
                # No Manim clip on this artifact (e.g. a stills-rendered
                # stem with no "mp4" manifest entry, or a Manim render that
                # failed before producing one) -- nothing to observe.
                continue

            scratch_dir = self._scratch_dir(
                context,
                stem,
            )

            record = visual_observe.observe_clip(
                clip_path,
                section_timings.get(stem),
                scratch_dir=scratch_dir,
                min_ink_fraction=min_ink_fraction,
                fallback_count=fallback_count,
            )

            artifact.audit = record

            artifact.motion = visual_observe.observe_motion(
                clip_path,
                section_timings.get(stem),
                scratch_dir=scratch_dir,
            )

        return context

    @staticmethod
    def _clip_path(
        artifact: Any,
    ) -> Path | None:
        """The rendered Manim clip path, or ``None`` if this artifact has none."""

        for entry in getattr(artifact, "manifest", None) or []:
            if not isinstance(entry, dict):
                continue

            mp4 = entry.get("mp4")

            if mp4:
                return Path(mp4)

        return None

    @staticmethod
    def _scratch_dir(
        context: SceneContext,
        stem: str,
    ) -> Path:
        if context.project_dir is not None:
            return (
                context.project_dir
                / "build"
                / "harness"
                / "visual_observe"
                / stem
            )

        return Path(f"./_visual_observe_{stem}")

    def _default_gate(self) -> bool:
        """Advisory by default -- see module docstring."""

        return False


__all__ = [
    "ObserverVisualPlugin",
]
