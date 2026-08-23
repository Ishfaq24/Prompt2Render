"""Deterministic spatial verifier for rendered Prompt2Render scenes.

This plugin surfaces the geometry verdict already recorded by SceneKit's
``audit()`` during rendering. It deliberately does not render scenes again.

The renderer/audit pipeline is:

    generated scene
        ↓
    stills.render_many()
        ↓
    SceneKit audit()
        ↓
    RenderArtifact.audit
        ↓
    VerifierSpatialPlugin
        ↓
    structured spatial findings

The audit is therefore treated as an observed renderer result, not something
this verifier recomputes.

The verifier also deliberately does not populate object-level bounding boxes:
there is currently no authoritative cross-scene object identity table from
which such rows could be created safely.
"""

from __future__ import annotations

import re
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin


# SceneKit's Problem.__str__() is recorded approximately as:
#
#     WARN [kind] message
#     FAIL [kind] message
#
# Keep the parser deliberately narrow so malformed/unknown audit records are
# not accidentally interpreted as successful findings.
_RECORDED = re.compile(
    r"^(?P<level>WARN|FAIL)\s+\[(?P<kind>[^\]]+)\]\s+(?P<message>.*)$"
)


def _normalize_status(
    value: Any,
) -> str:
    """Normalize an audit status without inventing semantics."""

    status = str(
        value or ""
    ).strip().lower()

    if status in {
        "pass",
        "warn",
        "fail",
        "skip",
    }:
        return status

    return ""


def _finding_for(
    stem: str,
    recorded: Any,
    *,
    gate: bool,
) -> Finding:
    """Convert one recorded SceneKit warning into a harness Finding."""

    text = str(
        recorded
    ).strip()

    match = _RECORDED.match(
        text
    )

    if match:
        level = match.group(
            "level"
        )

        kind = match.group(
            "kind"
        ).strip()

        message = match.group(
            "message"
        ).strip()

    else:
        # The audit record is authoritative but its textual representation
        # may evolve. Preserve the complete record instead of dropping it.
        level = "WARN"
        kind = "unknown"
        message = text or (
            "SceneKit spatial audit reported "
            "an unspecified issue."
        )

    severity = (
        Severity.BLOCKING
        if level == "FAIL" and gate
        else Severity.WARNING
    )

    finding = Finding(
        finding_id=next_finding_id(
            "spatial"
        ),
        scene_id=stem,
        category=Category.SPATIAL,
        severity=severity,
        message=message,
    )

    result = finding.as_check_result()

    # Keep the normalized routing information explicit.
    result["finding_type"] = (
        "spatial_conflict"
    )
    result["mismatch_subtype"] = (
        kind
    )
    result["audit_level"] = (
        level
    )
    result["recorded_problem"] = (
        text
    )

    return finding


def _audit_warnings(
    record: dict[str, Any],
) -> list[Any]:
    """Extract recorded warnings defensively."""

    warnings = record.get(
        "warnings",
        [],
    )

    if warnings is None:
        return []

    if isinstance(
        warnings,
        (list, tuple),
    ):
        return list(
            warnings
        )

    # Preserve a malformed single warning instead of iterating its characters.
    return [warnings]


class VerifierSpatialPlugin(Plugin):
    """Surface SceneKit's already-computed spatial audit verdict."""

    name = "verifier_spatial"

    def declare_dependencies(self) -> list[str]:
        # render_artifacts guarantees that RendererStillsPlugin has populated
        # RenderArtifact.audit before this verifier runs.
        return [
            "render_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        findings: list[
            dict[str, Any]
        ] = []

        gate = self.is_gate()

        for stem, artifact in (
            context.render_artifacts.items()
        ):

            record = getattr(
                artifact,
                "audit",
                None,
            )

            # ----------------------------------------------------------
            # Missing audit record
            # ----------------------------------------------------------

            if record is None:
                findings.append(
                    {
                        "status": "skip",
                        "stem": stem,
                        "finding_type": (
                            "spatial_audit_unavailable"
                        ),
                        "category": (
                            Category.SPATIAL.value
                        ),
                        "detail": (
                            "No SceneKit audit record was "
                            "recorded for this rendered scene."
                        ),
                    }
                )
                continue

            if not isinstance(
                record,
                dict,
            ):
                findings.append(
                    {
                        "status": "fail",
                        "stem": stem,
                        "finding_type": (
                            "spatial_audit_invalid"
                        ),
                        "category": (
                            Category.SPATIAL.value
                        ),
                        "detail": (
                            "RenderArtifact.audit is not a "
                            "dictionary."
                        ),
                    }
                )
                continue

            # ----------------------------------------------------------
            # Explicit audit status
            # ----------------------------------------------------------

            audit_status = _normalize_status(
                record.get(
                    "status"
                )
            )

            warnings = _audit_warnings(
                record
            )

            # Some versions of SceneKit expose only warnings/stills and not
            # an explicit status. In that case the presence/absence of
            # warnings remains authoritative.
            if audit_status == "fail" and not warnings:
                warnings = [
                    record.get(
                        "detail",
                        "SceneKit audit reported FAIL.",
                    )
                ]

            if warnings:

                for warning in warnings:
                    finding = _finding_for(
                        stem,
                        warning,
                        gate=gate,
                    )

                    findings.append(
                        finding.as_check_result()
                    )

                continue

            # ----------------------------------------------------------
            # Explicit audit warning without warning list
            # ----------------------------------------------------------

            if audit_status == "warn":
                findings.append(
                    {
                        "status": "warn",
                        "stem": stem,
                        "finding_type": (
                            "spatial_audit_warning"
                        ),
                        "category": (
                            Category.SPATIAL.value
                        ),
                        "detail": (
                            "SceneKit audit returned WARN "
                            "without a structured warning list."
                        ),
                    }
                )
                continue

            # ----------------------------------------------------------
            # Explicit audit failure
            # ----------------------------------------------------------

            if audit_status == "fail":
                findings.append(
                    {
                        "status": "fail",
                        "stem": stem,
                        "finding_type": (
                            "spatial_conflict"
                        ),
                        "category": (
                            Category.SPATIAL.value
                        ),
                        "detail": (
                            "SceneKit audit reported FAIL."
                        ),
                    }
                )
                continue

            # ----------------------------------------------------------
            # Clean result
            # ----------------------------------------------------------

            still_count = record.get(
                "stills",
                0,
            )

            findings.append(
                {
                    "status": "pass",
                    "stem": stem,
                    "finding_type": (
                        "spatial_audit"
                    ),
                    "category": (
                        Category.SPATIAL.value
                    ),
                    "detail": (
                        f"{still_count} stills clean"
                    ),
                }
            )

        context.check_results[
            self.name
        ] = findings

        return context

    def _default_gate(self) -> bool:
        """Spatial audit is advisory by default.

        Set ``gate=true`` in the plugin configuration when spatial audit
        failures should hard-block the pipeline.
        """

        return False