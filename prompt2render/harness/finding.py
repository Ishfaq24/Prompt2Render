"""Finding / severity — the shared taxonomy the migration brief's Stage 5 calls for, so
`verifier_spatial`, `verifier_lifecycle`, `verifier_audio`, `verifier_semantic` and
`evaluator_vlm` all report findings the ablation runner can cross-tabulate directly, without a
per-verifier translation step.

Deliberately NOT in the original Stage 2/3 schema — the migration plan calls this out as a Stage 5
addition, made here because Stage 5 (the ablation runner) is the first thing that needs it.
`check_results` entries stay dict-shaped (Stage 3's contract, which HarnessRunner's gate logic
already depends on via a bare `"status"` key) — Finding fields are merged into that same dict via
`as_check_result()`, not a parallel structure a caller would have to know to also look at.
"""
from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from enum import Enum


class Category(str, Enum):
    SPATIAL = "SPATIAL"
    TEMPORAL = "TEMPORAL"
    SEMANTIC = "SEMANTIC"
    AUDIO = "AUDIO"


class Severity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


#: Nothing in prompt2render today produces INFO-severity findings — left unused, not fabricated
#: (docs/MIGRATION_INVENTORY.md's own discipline: don't invent behavior).
#: A "fail"-severity finding also gates the pipeline (HarnessRunner reads status == "fail").
_SEVERITY_TO_STATUS = {Severity.BLOCKING: "fail", Severity.WARNING: "warn", Severity.INFO: "pass"}

_counter = itertools.count(1)


@dataclass
class Finding:
    finding_id: str
    scene_id: str
    category: Category
    severity: Severity
    message: str
    object_id: str | None = None

    def as_check_result(self) -> dict:
        """The dict shape verifiers already write to context.check_results, with Finding's
        fields merged in — `status` stays the key HarnessRunner's gate logic reads."""
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["status"] = _SEVERITY_TO_STATUS[self.severity]
        d["stem"] = self.scene_id
        d["detail"] = self.message
        return d


def next_finding_id(prefix: str = "f") -> str:
    return f"{prefix}-{next(_counter):06d}"
