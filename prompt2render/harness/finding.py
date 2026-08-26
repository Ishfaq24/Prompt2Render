"""Shared finding taxonomy for the Prompt2Render harness.

Every verifier emits the same normalized finding shape so that:

    verifier
        ↓
    Finding
        ↓
    check_results
        ↓
    RoutingPolicy / repair_router
        ↓
    ablation + self-correction metrics

The public ``check_results`` contract remains dictionary-based for backward
compatibility. ``Finding.as_check_result()`` merges the typed finding into
that existing dictionary representation.

A finding's ``severity`` controls the pipeline-facing ``status``:

    BLOCKING -> fail
    WARNING  -> warn
    INFO     -> pass

This module deliberately contains taxonomy and serialization only. It does
not contain routing or repair behavior.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from enum import Enum
from threading import Lock
from typing import Any


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

class Category(str, Enum):
    """Top-level failure category."""

    SPATIAL = "SPATIAL"
    LAYOUT = "LAYOUT"
    STRUCTURAL = "STRUCTURAL"
    TEMPORAL = "TEMPORAL"
    SEMANTIC = "SEMANTIC"
    AUDIO = "AUDIO"
    PEDAGOGY = "PEDAGOGY"
    MATH = "MATH"
    TECHNICAL = "TECHNICAL"
    STORYBOARD = "STORYBOARD"
    CODE = "CODE"
    RENDER = "RENDER"


# ---------------------------------------------------------------------------
# Layout sub-types (diagnosis-driven taxonomy)
# ---------------------------------------------------------------------------

class LayoutSubtype(str, Enum):
    """Refined layout failure modes."""

    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    OVERLAP = "OVERLAP"
    CROWDING = "CROWDING"
    UNSAFE_MARGIN = "UNSAFE_MARGIN"
    TEXT_OVERFLOW = "TEXT_OVERFLOW"
    CAPTION_COLLISION = "CAPTION_COLLISION"
    TITLE_COLLISION = "TITLE_COLLISION"
    NEAR_SAFE_MARGIN = "NEAR_SAFE_MARGIN"


class SemanticSubtype(str, Enum):
    """Semantic correctness subtypes."""

    WRONG_OBJECT = "WRONG_OBJECT"
    WRONG_VALUE = "WRONG_VALUE"
    WRONG_STATE = "WRONG_STATE"
    MISSING_CONCEPT = "MISSING_CONCEPT"
    NARRATION_MISMATCH = "NARRATION_MISMATCH"


class StructuralSubtype(str, Enum):
    """Structural/system subtypes."""

    RENDER_FAILURE = "RENDER_FAILURE"
    MISSING_ASSET = "MISSING_ASSET"
    WRONG_RESOLUTION = "WRONG_RESOLUTION"
    WRONG_DURATION = "WRONG_DURATION"


class PedagogicalSubtype(str, Enum):
    """Pedagogical subtypes."""

    UNCLEAR_PROGRESSION = "UNCLEAR_PROGRESSION"
    MISSING_STEP = "MISSING_STEP"
    INCONSISTENT_EXAMPLE = "INCONSISTENT_EXAMPLE"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"


class TemporalSubtype(str, Enum):
    """Temporal subtypes."""

    CUE_MISALIGNMENT = "CUE_MISALIGNMENT"
    STATE_TOO_EARLY = "STATE_TOO_EARLY"
    STATE_TOO_LATE = "STATE_TOO_LATE"


class Severity(str, Enum):
    """Pipeline severity."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


_SEVERITY_TO_STATUS: dict[
    Severity,
    str,
] = {
    Severity.BLOCKING: "fail",
    Severity.WARNING: "warn",
    Severity.INFO: "pass",
}


# ---------------------------------------------------------------------------
# Finding ID generation
# ---------------------------------------------------------------------------

_counter = itertools.count(1)
_counter_lock = Lock()


def next_finding_id(
    prefix: str = "f",
) -> str:
    """Return a process-local monotonically increasing finding ID.

    The lock matters because renderer/verifier stages may execute concurrently
    in future configurations.
    """

    prefix = str(
        prefix
    ).strip()

    if not prefix:
        prefix = "f"

    with _counter_lock:
        number = next(
            _counter
        )

    return (
        f"{prefix}-{number:06d}"
    )


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """Canonical typed verifier finding."""

    finding_id: str
    scene_id: str
    category: Category
    severity: Severity
    message: str
    object_id: str | None = None

    #: The routing key consumed by ``repair_router``. It lives here so the
    #: typed layer and the routing layer are not disjoint: previously every
    #: verifier had to remember to hand-add ``result["finding_type"] = ...``
    #: to the raw dict after calling :meth:`as_check_result`, with nothing
    #: to remind it, and a forgotten assignment silently fell back to
    #: ``_DEFAULT_FINDING_TYPE[source_plugin]``.
    #:
    #: Left ``None`` the key is omitted from the serialized dict entirely
    #: rather than emitted as null -- ``RoutingPolicy.decide`` reads it with
    #: ``str(finding.get("finding_type", ""))``, so a literal ``None`` would
    #: stringify to ``"None"``, match no route, and disable the fallback.
    finding_type: str | None = None

    def __post_init__(
        self,
    ) -> None:
        """Normalize and validate the canonical fields."""

        self.finding_id = str(
            self.finding_id
        ).strip()

        self.scene_id = str(
            self.scene_id
        ).strip()

        self.message = str(
            self.message
        ).strip()

        if not self.finding_id:
            raise ValueError(
                "finding_id cannot be empty"
            )

        if not self.scene_id:
            raise ValueError(
                "scene_id cannot be empty"
            )

        if not self.message:
            raise ValueError(
                "message cannot be empty"
            )

        # Accept enum-compatible strings for compatibility with older
        # verifier code, while guaranteeing that the object itself always
        # contains canonical enum values.
        if not isinstance(
            self.category,
            Category,
        ):
            try:
                self.category = Category(
                    self.category
                )
            except (
                ValueError,
                TypeError,
            ) as exc:
                raise ValueError(
                    f"Invalid finding category: "
                    f"{self.category!r}"
                ) from exc

        if not isinstance(
            self.severity,
            Severity,
        ):
            try:
                self.severity = Severity(
                    self.severity
                )
            except (
                ValueError,
                TypeError,
            ) as exc:
                raise ValueError(
                    f"Invalid finding severity: "
                    f"{self.severity!r}"
                ) from exc

        if self.object_id is not None:
            self.object_id = str(
                self.object_id
            ).strip() or None

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def as_check_result(
        self,
    ) -> dict[str, Any]:
        """Serialize into the existing ``check_results`` dictionary shape.

        ``status`` remains the compatibility key consumed by HarnessRunner.
        Typed Finding fields are flattened into the same dictionary rather
        than introducing a second result structure.
        """

        result = asdict(
            self
        )

        result[
            "category"
        ] = self.category.value

        result[
            "severity"
        ] = self.severity.value

        result[
            "status"
        ] = _SEVERITY_TO_STATUS[
            self.severity
        ]

        # Existing verifier/runner terminology uses ``stem`` and ``detail``.
        result[
            "stem"
        ] = self.scene_id

        result[
            "detail"
        ] = self.message

        # An unset finding_type must be ABSENT, not null: consumers read it
        # via ``.get("finding_type", "")`` and would otherwise receive None,
        # whose str() is the truthy "None". See the field's docstring.
        if self.finding_type is None:
            result.pop(
                "finding_type",
                None,
            )

        return result

    @property
    def status(
        self,
    ) -> str:
        """Return the pipeline-facing status."""

        return _SEVERITY_TO_STATUS[
            self.severity
        ]

    @property
    def is_blocking(
        self,
    ) -> bool:
        """Whether this finding should block a gated pipeline."""

        return (
            self.severity
            is Severity.BLOCKING
        )


__all__ = [
    "Category",
    "Severity",
    "Finding",
    "next_finding_id",
    "LayoutSubtype",
    "SemanticSubtype",
    "StructuralSubtype",
    "PedagogicalSubtype",
    "TemporalSubtype",
]