"""Deterministic validation for the LLM storyboard contract."""
from __future__ import annotations

from ..context import SceneContext
from ..plugin import Plugin
from ... import align


class VerifierStoryboardPlugin(Plugin):
    name = "verifier_storyboard"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "storyboard_plan", "narration"]

    def declare_effects(self) -> list[str]:
        return ["check_results", "storyboard_verified"]

    def run(self, context: SceneContext) -> SceneContext:
        issues: list[dict] = []
        sections = context.storyboard_plan.get("sections", [])
        by_index = {int(s.get("index")): s for s in sections if str(s.get("index", "")).isdigit()}
        for entry in context.scene_plan:
            item = by_index.get(entry.index)
            if not item:
                issues.append({"status": "fail", "finding_type": "storyboard_failure",
                               "category": "STORYBOARD", "severity": "BLOCKING",
                               "stem": entry.stem, "detail": "storyboard omitted this section"})
                continue
            states = item.get("states")
            if not isinstance(states, list) or not states:
                issues.append({"status": "fail", "finding_type": "storyboard_failure",
                               "category": "STORYBOARD", "severity": "BLOCKING",
                               "stem": entry.stem, "detail": "storyboard has no visual states"})
                continue
            try:
                timing = align.load(context.project_dir, entry.stem)
                sentence_count = len(timing.get("sentences", []))
            except (Exception, SystemExit):
                sentence_count = max(1, len(entry.narration_text.split(".")))
            previous_cue = -1
            for position, state in enumerate(states):
                cue = state.get("cue")
                if not isinstance(cue, int) or cue < 0 or cue >= sentence_count:
                    issues.append({"status": "fail", "finding_type": "storyboard_failure",
                                   "category": "STORYBOARD", "severity": "BLOCKING",
                                   "stem": entry.stem,
                                   "detail": f"state {position} cue {cue!r} is outside 0..{sentence_count - 1}"})
                if isinstance(cue, int) and cue < previous_cue:
                    issues.append({"status": "fail", "finding_type": "storyboard_failure",
                                   "category": "STORYBOARD", "severity": "BLOCKING",
                                   "stem": entry.stem,
                                   "detail": f"state {position} cue {cue} moves backward from {previous_cue}"})
                if isinstance(cue, int):
                    previous_cue = cue
                for key in ("visual", "transition"):
                    if not str(state.get(key, "")).strip():
                        issues.append({"status": "fail", "finding_type": "storyboard_failure",
                                       "category": "STORYBOARD", "severity": "BLOCKING",
                                       "stem": entry.stem,
                                       "detail": f"state {position} is missing {key}"})
        if not issues:
            issues = [{"status": "pass", "finding_type": "storyboard_verified",
                       "category": "STORYBOARD", "severity": "INFO",
                       "detail": "storyboard states, cues, and transitions are structurally valid"}]
        context.check_results[self.name] = issues
        return context

    def _default_gate(self) -> bool:
        return True
