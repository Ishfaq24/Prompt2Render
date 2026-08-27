"""Deterministic validation for the LLM storyboard contract.

Internal convention: cue indices are ZERO-BASED (0..N-1) throughout the
harness. The LLM prompt explicitly documents this, and the parser boundary
(``planner_llm._normalise_cue``) is the single place where any external
one-based value would be normalized to this internal convention. All
subsequent validation — here and in ``scenes.validate_scene_source`` /
``stills.render`` — assumes zero-based.
"""
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
                sentences = timing.get("sentences", [])
                sentence_count = len(sentences)
                sentence_texts = [s.get("text", "") for s in sentences]
            except (Exception, SystemExit):
                # Fallback: approximate via textseg when no alignment exists.
                # The verifier must remain deterministic even without audio.
                sentences = []
                sentence_texts = []
                sentence_count = max(1, len(entry.narration_text.split(".")))
            previous_cue = -1
            for position, state in enumerate(states):
                cue = state.get("cue")
                state_name = str(state.get("name") or f"state {position}")
                # Strict zero-based validation: 0 <= cue < sentence_count
                if not isinstance(cue, int) or cue < 0 or cue >= sentence_count:
                    # Build rich diagnostic per task spec.
                    if isinstance(cue, int):
                        requested = f"cue {cue}"
                        # Include cue text if inside range, otherwise note invalid.
                        hint = ""
                        if 0 <= cue < len(sentence_texts) and sentence_texts[cue]:
                            hint = f" (cue text: {sentence_texts[cue][:80]!r})"
                        elif sentence_texts:
                            hint = f" (available cues: 0..{sentence_count - 1}, count={sentence_count})"
                        detail = (
                            f"Scene{entry.stem} state {position} ({state_name}) references {requested}, "
                            f"but section {entry.stem} contains {sentence_count} sentences "
                            f"(valid zero-based range: 0..{sentence_count - 1}, cue count={sentence_count}){hint}"
                        )
                        # Preserve legacy substring for existing log greps: 'is outside 0..N'
                        detail += f" — state {position} cue {cue!r} is outside 0..{sentence_count - 1}"
                        # Heuristic hint for one-based confusion
                        if isinstance(cue, int) and cue == sentence_count and sentence_count > 0:
                            detail += (
                                f" — cue {cue} equals sentence count {sentence_count}; "
                                f"if the source used one-based numbering (1..{sentence_count}), "
                                f"normalize to zero-based {cue - 1} at the parser boundary"
                            )
                    else:
                        detail = (
                            f"Scene{entry.stem} state {position} ({state_name}) has non-integer cue {cue!r}; "
                            f"expected int in 0..{sentence_count - 1} (count={sentence_count})"
                        )
                    issues.append({"status": "fail", "finding_type": "storyboard_failure",
                                   "category": "STORYBOARD", "severity": "BLOCKING",
                                   "stem": entry.stem,
                                   "detail": detail,
                                   "state_index": position,
                                   "state_name": state_name,
                                   "requested_cue": cue,
                                   "available_range": f"0..{sentence_count - 1}",
                                   "cue_count": sentence_count})
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
