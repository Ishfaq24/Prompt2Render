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
    TEMPORAL = "TEMPORAL"
    SEMANTIC = "SEMANTIC"
    AUDIO = "AUDIO"
    PEDAGOGY = "PEDAGOGY"
    MATH = "MATH"
    TECHNICAL = "TECHNICAL"
    STORYBOARD = "STORYBOARD"
    CODE = "CODE"
    RENDER = "RENDER"


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
]