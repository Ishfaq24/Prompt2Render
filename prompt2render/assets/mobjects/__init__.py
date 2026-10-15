"""Prompt2Render universal Manim Mobject component & layout stage library."""

from .base import P2RSVGMobject, P2RText, apply_text_patches, get_default_font
from .hardware import MemoryBankMobject
from .data_structures import BinaryTreeMobject
from .math_widgets import CoordinateGridMobject
from .network_widgets import (
    ServerNode,
    ClientCluster,
    DatabaseNode,
    ConfigCodeCard,
    MetricBadge,
)
from .stages import (
    FlowStage,
    SplitStage,
    HeroFocusStage,
    BenchmarkStage,
    AutoVStack,
    AutoHStack,
    SafeCaptionZone,
    CaptionDock,
    AnnotatedCard,
    MediaCard,
)
from .algo_math_widgets import (
    ArrayGrid,
    FormulaCard,
    KeyBadge,
)

__all__ = [
    "P2RSVGMobject",
    "P2RText",
    "apply_text_patches",
    "get_default_font",
    "MemoryBankMobject",
    "BinaryTreeMobject",
    "CoordinateGridMobject",
    "ServerNode",
    "ClientCluster",
    "DatabaseNode",
    "ConfigCodeCard",
    "MetricBadge",
    "FlowStage",
    "SplitStage",
    "HeroFocusStage",
    "BenchmarkStage",
    "AutoVStack",
    "AutoHStack",
    "SafeCaptionZone",
    "CaptionDock",
    "AnnotatedCard",
    "MediaCard",
    "ArrayGrid",
    "FormulaCard",
    "KeyBadge",
    "NeuralNetworkMobject3D",
    "StackMobject",
    "QueueMobject",
    "AnimatedCurveMobject",
]


# Phase 5 — 3D neural network
try:
    from .neural_3d import NeuralNetworkMobject3D
except Exception:
    pass

# Phase 6 — Algorithm widgets
try:
    from .algorithm_widgets import StackMobject, QueueMobject
except Exception:
    pass

# Phase 6 — Math widgets
try:
    from .math_widgets import AnimatedCurveMobject
except Exception:
    pass
