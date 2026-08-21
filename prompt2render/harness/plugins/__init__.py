"""The flat plugin registry — one entry per top-level folder, per the wrapping rules
("do NOT nest by pipeline stage; plugin boundaries must match future experiment boundaries").
"""
from __future__ import annotations

from .chunker_scene import ChunkerScenePlugin
from .planner_llm import PlannerLlmPlugin
from .planner_visual import PlannerVisualPlugin
from .planner_audio import PlannerAudioPlugin
from .retriever_manim_rag import RetrieverManimRagPlugin
from .generator_code import GeneratorCodePlugin
from .verifier_semantic import VerifierSemanticPlugin
from .verifier_spatial import VerifierSpatialPlugin
from .verifier_lifecycle import VerifierLifecyclePlugin
from .verifier_audio import VerifierAudioPlugin
from .renderer_stills import RendererStillsPlugin
from .renderer_manim import RendererManimPlugin
from .evaluator_vlm import EvaluatorVlmPlugin
from .feedback_hitl import FeedbackHitlPlugin
from .repair_router import RepairRouterPlugin

#: Order here is the fallback tie-break for the loader's topological sort (declared
#: dependencies/effects are the real ordering signal) — listed roughly pipeline-shaped for
#: readability, not because order here is load-bearing.
REGISTRY: dict[str, type] = {
    "chunker_scene": ChunkerScenePlugin,
    "planner_llm": PlannerLlmPlugin,
    "planner_visual": PlannerVisualPlugin,
    "planner_audio": PlannerAudioPlugin,
    "retriever_manim_rag": RetrieverManimRagPlugin,
    "generator_code": GeneratorCodePlugin,
    "renderer_stills": RendererStillsPlugin,
    "renderer_manim": RendererManimPlugin,
    "verifier_semantic": VerifierSemanticPlugin,
    "verifier_spatial": VerifierSpatialPlugin,
    "verifier_lifecycle": VerifierLifecyclePlugin,
    "verifier_audio": VerifierAudioPlugin,
    "evaluator_vlm": EvaluatorVlmPlugin,
    "feedback_hitl": FeedbackHitlPlugin,
    # repair_router is deliberately NOT part of the ordinary pipeline — it's an event
    # subscriber (see its own docstring), instantiated separately by
    # loader.build_repair_router() and excluded from resolve_order.
    "repair_router": RepairRouterPlugin,
}

#: Not part of the topologically-ordered pipeline (see REGISTRY's comment above).
NON_PIPELINE = {"repair_router"}
