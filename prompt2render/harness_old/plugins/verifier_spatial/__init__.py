"""Real wrap of scenekit.audit()'s recorded verdict — deliberately NOT a `[]`-always shell.

scenekit.py::audit() is ~250 lines of working geometry checks (overlap, off-frame, collision,
tiny-text, ink-fraction) that scenes.py's own retry loop already depends on today. The audit runs
inline inside stills.render()/render_into(), invoked as a side effect of generator_code's call
into scenes.generate() — by the time this plugin runs, `build/scenes/<stem>/audit.json` already
exists for every accepted section. This plugin surfaces that already-computed verdict rather than
re-running matplotlib rendering a second time (see the migration plan's deviation #4).

`object_table[*].bbox` — the plugin-role table also lists this plugin writing per-object bounding
boxes into object_table. Deliberately not done here: object_table has no populated rows yet (no
cross-scene object identity exists anywhere in prompt2render — docs/MIGRATION_INVENTORY.md §7), and
attaching a bbox to a row that doesn't exist would mean inventing object identity ourselves. That
lands once Stage 4/5's AST pass (repair-router era) actually creates rows to attach it to.
"""
from __future__ import annotations

import re

from ...context import SceneContext
from ...finding import Category, Finding, Severity, next_finding_id
from ...plugin import Plugin

#: audit.json's warnings are pre-stringified via scenekit.Problem.__str__:
#: f"{level.upper()} [{kind}] {message}" — recovering severity from that format exposes
#: already-existing structured data rather than inventing new parsing logic.
_RECORDED = re.compile(r"^(WARN|FAIL) \[(?P<kind>[^\]]+)\] (?P<message>.*)$")


class VerifierSpatialPlugin(Plugin):
    name = "verifier_spatial"

    def declare_dependencies(self) -> list[str]:
        # Depending on render_artifacts (not code_artifacts) guarantees renderer_stills has run
        # first, so the audit it recorded is guaranteed current rather than relying on
        # generator_code's internal side effect alone.
        return ["render_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        findings = []
        for stem, art in context.render_artifacts.items():
            record = art.audit
            if record is None:
                findings.append({"status": "skip", "stem": stem,
                                 "detail": "no audit.json recorded"})
                continue
            warnings = record.get("warnings", [])
            if warnings:
                for w in warnings:
                    findings.append(_finding_for(stem, w).as_check_result())
            else:
                findings.append({"status": "pass", "stem": stem,
                                 "detail": f"{record.get('stills', 0)} stills clean",
                                 "category": Category.SPATIAL.value})
        context.check_results[self.name] = findings
        return context


def _finding_for(stem: str, recorded: str) -> Finding:
    m = _RECORDED.match(recorded)
    severity = Severity.BLOCKING if m and m.group(1) == "FAIL" else Severity.WARNING
    message = m.group("message") if m else recorded
    return Finding(finding_id=next_finding_id("spatial"), scene_id=stem,
                  category=Category.SPATIAL, severity=severity, message=message)
