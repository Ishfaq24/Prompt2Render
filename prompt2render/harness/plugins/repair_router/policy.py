"""Pluggable finding-type -> repair-target routing policy.

The routing policy is deliberately separate from ``repair_router`` so the
repair strategy is inspectable, testable, and replaceable.

A policy receives a normalized finding dictionary and returns target plugin
names in execution order.

The default policy supports both the SceneKit and Manim backends: the repair
router may alias ``generator_code`` to ``generator_manim`` when the latter is
the active backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any


class RoutingPolicy(ABC):
    """Abstract routing strategy."""

    @abstractmethod
    def decide(
        self,
        finding: dict[str, Any],
    ) -> list[str]:
        """Return repair target plugin names in call order.

        Expected finding fields include:

        - scene_id
        - finding_type
        - mismatch_subtype
        - category
        - severity
        - diagnostic_message/detail
        - source_plugin
        """
        raise NotImplementedError


class StaticTableRoutingPolicy(RoutingPolicy):
    """Deterministic, inspectable routing table.

    The table is intentionally data-driven rather than buried in the repair
    router. This makes the routing policy easy to test, log, compare, and
    replace with a learned or configurable policy later.

    ``generator_code`` is the canonical code-generation target. The repair
    router transparently maps it to ``generator_manim`` when Manim is the
    active backend.
    """

    DEFAULT_TABLE: dict[str, list[str]] = {
        "semantic_mismatch": ["generator_code"],
        "execution_failure": ["generator_code"],
        "spatial_conflict": ["generator_code"],
        "lifecycle_violation": ["generator_code"],
        "temporal_mismatch": ["generator_code"],
        "manim_crash": ["generator_code"],
        "stills_render_failure": ["generator_code"],
        "pedagogy_review": ["reviser_script"],
        "storyboard_failure": ["planner_llm"],
    }

    #: Post-render VLM findings are routed back to the verifier that owns
    #: the corresponding Finding category. The verifier then decides what
    #: precise finding/repair information to emit.
    VLM_CATEGORY_ROUTE: dict[str, list[str]] = {
        "SPATIAL": ["verifier_spatial"],
        "TEMPORAL": ["verifier_lifecycle"],
        "SEMANTIC": ["verifier_semantic"],
        "AUDIO": ["verifier_audio"],
    }

    #: Explicit subtype routes for audio/visual mismatches.
    AUDIO_VISUAL_ROUTE: dict[str, list[str]] = {
        "narration_wrong": ["planner_audio"],
        "visual_wrong": ["generator_code"],
        "unclear": [
            "generator_code",
            "planner_audio",
        ],
    }

    def __init__(
        self,
        table: dict[str, list[str]] | None = None,
    ):
        # Deep-copy the supplied/default table so callers cannot accidentally
        # mutate the class-level routing policy.
        source = (
            table
            if table is not None
            else self.DEFAULT_TABLE
        )

        self.table: dict[str, list[str]] = {
            str(finding_type): [
                str(target)
                for target in targets
                if str(target).strip()
            ]
            for finding_type, targets in deepcopy(
                source
            ).items()
            if isinstance(targets, (list, tuple))
        }

    def decide(
        self,
        finding: dict[str, Any],
    ) -> list[str]:
        """Resolve repair targets deterministically."""

        if not isinstance(
            finding,
            dict,
        ):
            return []

        finding_type = str(
            finding.get(
                "finding_type",
                "",
            )
        ).strip()

        if not finding_type:
            return []

        # --------------------------------------------------------------
        # Audio/visual mismatch
        # --------------------------------------------------------------

        if finding_type == "audio_visual_mismatch":
            subtype = str(
                finding.get(
                    "mismatch_subtype",
                    "unclear",
                )
            ).strip().lower()

            targets = self.AUDIO_VISUAL_ROUTE.get(
                subtype
            )

            if targets is None:
                targets = self.AUDIO_VISUAL_ROUTE[
                    "unclear"
                ]

            return self._unique_targets(
                targets
            )

        # --------------------------------------------------------------
        # Post-render VLM defect
        # --------------------------------------------------------------

        if finding_type == "vlm_post_render_defect":
            category = str(
                finding.get(
                    "category",
                    "",
                )
            ).strip().upper()

            return self._unique_targets(
                self.VLM_CATEGORY_ROUTE.get(
                    category,
                    [],
                )
            )

        # --------------------------------------------------------------
        # Direct table lookup
        # --------------------------------------------------------------

        return self._unique_targets(
            self.table.get(
                finding_type,
                [],
            )
        )

    @staticmethod
    def _unique_targets(
        targets: list[str] | tuple[str, ...],
    ) -> list[str]:
        """Preserve routing order while removing duplicates/empty targets."""

        return list(
            dict.fromkeys(
                str(target).strip()
                for target in targets
                if str(target).strip()
            )
        )

    def explain(
        self,
        finding: dict[str, Any],
    ) -> dict[str, Any]:
        """Return an inspectable explanation of the routing decision.

        Useful for logs, experiments, and the methods/evaluation section of
        the project without changing the routing behaviour.
        """

        finding_type = str(
            finding.get(
                "finding_type",
                "",
            )
        ).strip()

        targets = self.decide(
            finding
        )

        return {
            "finding_type": finding_type,
            "mismatch_subtype": finding.get(
                "mismatch_subtype"
            ),
            "category": finding.get(
                "category"
            ),
            "targets": targets,
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation of this policy."""

        return {
            "type": self.__class__.__name__,
            "table": deepcopy(
                self.table
            ),
            "audio_visual_route": deepcopy(
                self.AUDIO_VISUAL_ROUTE
            ),
            "vlm_category_route": deepcopy(
                self.VLM_CATEGORY_ROUTE
            ),
        }