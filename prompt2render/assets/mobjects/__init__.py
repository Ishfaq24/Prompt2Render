"""Prompt2Render universal Manim Mobject component & layout stage library."""

from .base import P2RSVGMobject
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
)
from .algo_math_widgets import (
    ArrayGrid,
    FormulaCard,
    KeyBadge,
)

__all__ = [
    "P2RSVGMobject",
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
    "ArrayGrid",
    "FormulaCard",
    "KeyBadge",
]


