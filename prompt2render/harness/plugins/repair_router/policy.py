"""RoutingPolicy — pluggable, loggable/swappable finding-type -> target-plugin routing.

Per the migration brief §2b: the audio-vs-code routing decision is itself one of the paper's
secondary contributions, so it needs to be swappable and inspectable like everything else, not a
buried if/else. One concrete policy ships: StaticTableRoutingPolicy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class RoutingPolicy(ABC):
    @abstractmethod
    def decide(self, finding: dict) -> list[str]:
        """finding: {scene_id, finding_type, mismatch_subtype?, category?, severity,
        diagnostic_message, source_plugin}. Returns target plugin name(s), in call order."""


class StaticTableRoutingPolicy(RoutingPolicy):
    #: This table is the artifact worth screenshotting into a methods section, per the brief.
    DEFAULT_TABLE = {
        "semantic_mismatch": ["generator_code"],
        "spatial_conflict": ["generator_code"],
        "lifecycle_violation": ["generator_code"],
    }

    #: vlm_post_render_defect routes to whichever pre-render verifier should have caught it,
    #: keyed by the shared Finding category taxonomy (Stage 5).
    VLM_CATEGORY_ROUTE = {
        "SPATIAL": ["verifier_spatial"],
        "TEMPORAL": ["verifier_lifecycle"],
        "SEMANTIC": ["verifier_semantic"],
        "AUDIO": ["verifier_audio"],
    }

    def __init__(self, table: dict | None = None):
        self.table = dict(table) if table else dict(self.DEFAULT_TABLE)

    def decide(self, finding: dict) -> list[str]:
        ftype = finding.get("finding_type")

        if ftype == "audio_visual_mismatch":
            subtype = finding.get("mismatch_subtype", "unclear")
            if subtype == "narration_wrong":
                return ["planner_audio"]
            if subtype == "visual_wrong":
                return ["generator_code"]
            return ["generator_code", "planner_audio"]     # unclear: both, code first

        if ftype == "vlm_post_render_defect":
            return list(self.VLM_CATEGORY_ROUTE.get(finding.get("category"), []))

        return list(self.table.get(ftype, []))
