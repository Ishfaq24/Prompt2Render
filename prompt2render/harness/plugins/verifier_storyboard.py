"""Deterministic validation for the LLM storyboard contract."""
from __future__ import annotations

from ..context import SceneContext
from ..motion import validate_motion_ops
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
                for message in validate_motion_ops(state.get("motion")):
                    issues.append({"status": "fail", "finding_type": "storyboard_failure",
                                   "category": "STORYBOARD", "severity": "BLOCKING",
                                   "stem": entry.stem,
                                   "detail": f"state {position} motion error: {message}"})
        has_blocking = any(
            isinstance(item, dict)
            and str(item.get("status", "")).lower() == "fail"
            and str(item.get("severity", "")) == "BLOCKING"
            for item in issues
        )
        if not issues:
            issues = [{"status": "pass", "finding_type": "storyboard_verified",
                       "category": "STORYBOARD", "severity": "INFO",
                       "detail": "storyboard states, cues, and transitions are structurally valid"}]
        context.check_results[self.name] = issues
        # Gate field consumed by generator_code — must be set even though
        # check_results already records the same verdict for the runner's gate.
        context.storyboard_verified = not has_blocking
        return context

    def _default_gate(self) -> bool:
        return True
