"""Human-approval publish gate -- Tier 4, HUMAN_APPROVAL mode.

Today's HITL system (SS18) is a single, always-optional reject/accept file:
an automated run never waits for a human (``feedback_hitl``'s gate defaults
``False``), and ``"accept"`` only means "never touch this stem again" (a
lock, consumed by ``renderer_manim.hitl_status_sets``) -- there was no way
to require universal sign-off before a build is allowed to ship.

This plugin adds exactly that, reusing the *same* ``hitl_feedback.json``
contract and the same ``"accept"`` semantics (via ``harness.hitl.
status_sets`` -- no new file, no new schema): every stem present in
``render_artifacts`` must have an explicit ``"accept"`` entry, or this
plugin fails it.

Only meaningful when ``HUMAN_APPROVAL`` mode is selected (``--hitl-mode
human_approval`` toggles this plugin's ``enabled`` -- see
``prompt2render.py``'s ``cmd_harness``); disabled by default, so
``AUTONOMOUS`` (today's behavior) is completely unaffected. Unlike every
other advisory-by-default addition this migration has shipped,
``_default_gate()`` here is ``True`` **by explicit user direction**: the
entire point of turning this mode on is "do not ship without a human
sign-off" -- an advisory default would silently defeat that the moment
someone enables the mode expecting it to mean what its name says.
"""

from __future__ import annotations

from typing import Any

from ... import hitl
from ...context import SceneContext
from ...finding import Category
from ...plugin import Plugin


class VerifierHitlApprovalPlugin(Plugin):
    """Blocks publish until every rendered stem has an explicit human accept."""

    name = "verifier_hitl_approval"

    def declare_dependencies(self) -> list[str]:
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

        gate = self.is_gate()
        _, locked = hitl.status_sets(context.project_dir)

        findings: list[dict[str, Any]] = []

        for stem in sorted(context.render_artifacts):

            if stem in locked:
                findings.append(
                    {
                        "status": "pass",
                        "stem": stem,
                        "finding_type": "hitl_approval",
                        "category": Category.SEMANTIC.value,
                        "detail": "Human-approved (hitl_feedback.json accept).",
                    }
                )
                continue

            findings.append(
                {
                    "status": "fail" if gate else "warn",
                    "stem": stem,
                    "finding_type": "hitl_approval_missing",
                    "category": Category.SEMANTIC.value,
                    "severity": "BLOCKING" if gate else "WARNING",
                    "detail": (
                        f"Section {stem} has not been explicitly approved. "
                        "HUMAN_APPROVAL mode requires an \"accept\" entry "
                        "in hitl_feedback.json for every section before "
                        "publish."
                    ),
                }
            )

        context.check_results[self.name] = findings

        return context

    def _default_gate(self) -> bool:
        """Hard gate when this plugin is enabled -- see module docstring."""

        return True


__all__ = [
    "VerifierHitlApprovalPlugin",
]
