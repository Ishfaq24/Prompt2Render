"""Flat Prompt2Render plugin registry.

Each entry corresponds to one top-level plugin boundary. Pipeline ordering is
determined by declared dependencies/effects; dictionary order is only a stable
tie-breaker for the loader.

``repair_router`` is intentionally excluded from the ordinary pipeline. It is
an event subscriber and must be constructed through the dedicated loader path.
"""

from __future__ import annotations

from .chunker_scene import ChunkerScenePlugin
from .planner_llm import PlannerLlmPlugin
from .planner_script import (
    PlannerScriptPlugin,
    PlannerVisualPlugin,
)
from .pedagogy import (
    PlannerPedagogyPlugin,
    ReviserScriptPlugin,
    VerifierPedagogyPlugin,
)
from .verifier_storyboard import (
    VerifierStoryboardPlugin,
)
from .verifier_animation_ir import (
    VerifierAnimationIrPlugin,
)
from .planner_semantic import (
    PlannerSemanticPlugin,
)
from .planner_temporal import (
    PlannerTemporalPlugin,
)
from .planner_audio import PlannerAudioPlugin
from .retriever_manim_rag import (
    RetrieverManimRagPlugin,
)
from .generator_code import GeneratorCodePlugin
from .verifier_semantic import (
    VerifierSemanticPlugin,
)
from .verifier_execution import (
    VerifierExecutionPlugin,
)
from .observer_visual import (
    ObserverVisualPlugin,
)
from .verifier_spatial import (
    VerifierSpatialPlugin,
)
from .verifier_lifecycle import (
    VerifierLifecyclePlugin,
)
from .verifier_temporal import (
    VerifierTemporalPlugin,
)
from .verifier_audio import (
    VerifierAudioPlugin,
)
from .renderer_stills import (
    RendererStillsPlugin,
)
from .renderer_manim import (
    GeneratorManimPlugin,
    RendererManimPlugin,
    RendererManimFinishPlugin,
    VerifierManimFinalQcPlugin,
)
from .feedback_hitl import FeedbackHitlPlugin
from .repair_router import RepairRouterPlugin
from .pipeline_downstream import (
    GeneratorVoicePlugin,
    GeneratorAlignPlugin,
    GeneratorTimelinePlugin,
    RendererEncodePlugin,
    RendererFinishPlugin,
    GeneratorPublishPlugin,
    VerifierFinalQCPlugin,
)


# ---------------------------------------------------------------------------
# Ordinary pipeline
# ---------------------------------------------------------------------------

REGISTRY: dict[str, type] = {
    # ---------------------------------------------------------------
    # Planning
    # ---------------------------------------------------------------
    "chunker_scene": ChunkerScenePlugin,

    "planner_script": PlannerScriptPlugin,
    "planner_pedagogy": PlannerPedagogyPlugin,
    "reviser_script": ReviserScriptPlugin,

    "verifier_pedagogy": VerifierPedagogyPlugin,

    "planner_llm": PlannerLlmPlugin,
    "verifier_storyboard": VerifierStoryboardPlugin,
    "verifier_animation_ir": VerifierAnimationIrPlugin,
    "planner_semantic": PlannerSemanticPlugin,
    "planner_temporal": PlannerTemporalPlugin,

    "planner_visual": PlannerVisualPlugin,
    "planner_audio": PlannerAudioPlugin,

    "retriever_manim_rag": RetrieverManimRagPlugin,

    # ---------------------------------------------------------------
    # Generation
    # ---------------------------------------------------------------
    "generator_code": GeneratorCodePlugin,
    "generator_manim": GeneratorManimPlugin,

    # ---------------------------------------------------------------
    # Pre-render verification
    # ---------------------------------------------------------------
    "verifier_execution": VerifierExecutionPlugin,

    # ---------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------
    "renderer_stills": RendererStillsPlugin,
    "renderer_manim": RendererManimPlugin,

    # ---------------------------------------------------------------
    # Post-generation / rendered verification
    # ---------------------------------------------------------------
    "verifier_semantic": VerifierSemanticPlugin,
    # Tier 3 Phase 11 (F3/F4): populates RenderArtifact.audit for Manim
    # stems before verifier_spatial reads it -- REGISTRY dict order is the
    # tie-break that guarantees this ordering (see loader.resolve_order's
    # own docstring), the same mechanism the rest of this section already
    # relies on.
    "observer_visual": ObserverVisualPlugin,
    "verifier_spatial": VerifierSpatialPlugin,
    "verifier_lifecycle": VerifierLifecyclePlugin,
    "verifier_temporal": VerifierTemporalPlugin,
    "verifier_audio": VerifierAudioPlugin,

    # ---------------------------------------------------------------
    # Human feedback
    # ---------------------------------------------------------------
    "feedback_hitl": FeedbackHitlPlugin,

    # ---------------------------------------------------------------
    # Downstream production
    # ---------------------------------------------------------------
    "generator_voice": GeneratorVoicePlugin,
    "generator_align": GeneratorAlignPlugin,
    "generator_timeline": GeneratorTimelinePlugin,

    "renderer_encode": RendererEncodePlugin,
    "renderer_finish": RendererFinishPlugin,

    "renderer_manim_finish": RendererManimFinishPlugin,
    "verifier_manim_final_qc": VerifierManimFinalQcPlugin,

    "generator_publish": GeneratorPublishPlugin,
    "verifier_final_qc": VerifierFinalQCPlugin,

    # ---------------------------------------------------------------
    # Event-driven repair infrastructure
    # ---------------------------------------------------------------
    #
    # Kept in REGISTRY so the loader can discover the class, but excluded
    # from ordinary topological execution by NON_PIPELINE below.
    "repair_router": RepairRouterPlugin,
}


# ---------------------------------------------------------------------------
# Non-pipeline plugins
# ---------------------------------------------------------------------------

#: Plugins that are discoverable but are not executed by the normal DAG.
NON_PIPELINE: frozenset[str] = frozenset(
    {
        "repair_router",
    }
)


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------

def validate_registry() -> None:
    """Validate structural registry invariants.

    Called by the loader/tests rather than at import time so importing the
    package cannot unexpectedly terminate a CLI invocation.
    """

    if not NON_PIPELINE.issubset(
        REGISTRY
    ):
        missing = sorted(
            NON_PIPELINE - REGISTRY.keys()
        )

        raise RuntimeError(
            "NON_PIPELINE contains unregistered "
            f"plugins: {missing}"
        )

    duplicate_classes: dict[type, list[str]] = {}

    for name, plugin_cls in REGISTRY.items():
        duplicate_classes.setdefault(
            plugin_cls,
            [],
        ).append(name)

    # Duplicate classes are allowed only when they intentionally provide
    # separate compatibility names. Keep the check informational rather than
    # rejecting the registry because PlannerScript/PlannerVisual are separate
    # classes and no accidental alias should silently enter the registry.
    accidental = {
        cls: names
        for cls, names in duplicate_classes.items()
        if len(names) > 1
        and cls.__name__
        not in {
            "PlannerScriptPlugin",
            "PlannerVisualPlugin",
        }
    }

    if accidental:
        raise RuntimeError(
            "Multiple registry names point to the same "
            f"plugin class: {accidental}"
        )


def pipeline_registry() -> dict[str, type]:
    """Return only plugins participating in normal DAG execution."""

    return {
        name: plugin_cls
        for name, plugin_cls in REGISTRY.items()
        if name not in NON_PIPELINE
    }


__all__ = [
    "REGISTRY",
    "NON_PIPELINE",
    "pipeline_registry",
    "validate_registry",
]