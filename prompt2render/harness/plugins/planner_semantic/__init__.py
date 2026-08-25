"""Semantic animation planner -- CONTEXT/ANTICIPATION/ACTION/CONSEQUENCE/HOLD.

Phase 3 of the Tier 1 migration (``docs/ARCHITECTURE_AUDIT.md`` SS16-17).
Runs after ``verifier_animation_ir`` (so it always has a validated, typed
``AnimationIR`` to work from) and before ``generator_code``. One LLM request
per video -- same "video-level, not per-scene" shape as ``planner_llm`` --
asks the model to organize each state's existing motion ops into the
pedagogical beat structure defined in ``harness.semantic_plan``, optionally
proposing additional ops on already-known identifiers to enrich thin states.

Two distinct failure modes get two distinct responses, deliberately unlike
``planner_llm``'s uniform "always fall back silently" policy:

- The LLM is unavailable (no API keys) or the request itself raised: falls
  back to ``semantic_plan.default_semantic_plan()`` silently, exactly like
  ``planner_llm`` does for the same condition. Retrying wouldn't help, so
  there is nothing productive a blocking Finding + repair cycle could do.
- The LLM responded, but its content fails ``semantic_plan.annotate()``'s
  validation (a fixable mistake -- wrong phase name, missing ACTION beat,
  an invented identifier): raises a BLOCKING ``semantic_plan_failure``
  Finding instead of silently discarding the attempt. Unlike
  ``storyboard_plan`` (foundational -- the pipeline cannot proceed without
  some storyboard, so ``planner_llm`` must always produce *something*),
  ``semantic_ir`` is a refinement layer with no other consumer yet; there is
  no urgency to keep moving through bad content when a retry-with-feedback
  cycle can produce a real, enriched result instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ...animation_ir import AnimationIR, SectionIR
from ...context import SceneContext
from ...finding import Category, Finding, Severity, next_finding_id
from ...motion import MOTION_OPS
from ...plugin import Plugin
from ...semantic_plan import (
    SemanticPlanValidationError,
    annotate,
    default_semantic_plan,
)
from .... import cfg, llm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARNESS_DIR = "build/harness"
PROVENANCE_DIR = "build/harness/provenance"

SEMANTIC_PLAN_FILE = "semantic_plan.json"
SEMANTIC_PLAN_PROMPT_FILE = "semantic_plan.prompt.txt"

DEFAULT_MODEL = "gemini-3.5-flash-lite"


# ---------------------------------------------------------------------------
# Deterministic helpers (same shape as planner_llm's -- each plugin owns its
# own small persistence/parsing helpers rather than sharing a utils module,
# matching this codebase's existing per-plugin convention)
# ---------------------------------------------------------------------------

def _harness_dir(project_dir: Path) -> Path:
    path = project_dir / HARNESS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _provenance_dir(project_dir: Path) -> Path:
    path = project_dir / PROVENANCE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response (plain, fenced, or
    surrounded by accidental prose) -- same logic as planner_llm's own
    ``_extract_json``."""

    if not isinstance(text, str):
        return None

    text = text.strip()

    if not text:
        return None

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        return None

    try:
        value = json.loads(text[start:end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def _known_identifiers(section: SectionIR) -> list[str]:
    identifiers: set[str] = set()

    for state in section.states:
        for op in state.ops:
            identifiers.update(op.params.values())

    return sorted(identifiers)


def _section_payload(section: SectionIR) -> dict[str, Any]:
    return {
        "index": section.index,
        "title": section.title,
        "known_identifiers": _known_identifiers(section),
        "states": [
            {
                "name": state.name,
                "cue": state.cue,
                "visual": state.visual,
                "transition": state.transition,
                "existing_ops": [{"op": op.op, **op.params} for op in state.ops],
            }
            for state in section.states
        ],
    }


def _build_prompt(
    sections_payload: list[dict[str, Any]],
    repair_feedback: dict[str, list[str]] | None = None,
) -> str:
    ops_list = ", ".join(sorted(MOTION_OPS))
    ops_keys = "; ".join(
        f"{op} needs {sorted(keys)}" for op, keys in sorted(MOTION_OPS.items())
    )

    repair_text = ""

    if repair_feedback:
        repair_text = "\n\nTARGETED REPAIR FEEDBACK:\n" + json.dumps(
            repair_feedback, ensure_ascii=False, indent=2
        )

    return f"""
You are the animation choreographer. Each section below lists visual states
that already have some existing motion ops. For every state, organize its
"existing_ops" (and, optionally, new supporting ops on already-known
identifiers) into a pedagogical beat structure using exactly these phases:

- CONTEXT: ops that establish what's already true as the state opens,
  before its defining change. Optional.
- ANTICIPATION: ops that draw attention to what's about to change, before
  it changes. Optional.
- ACTION: the state's defining event. Every non-hold state needs at least
  one ACTION beat.
- CONSEQUENCE: ops showing the result of the action. Optional.

If a state genuinely has nothing new to show -- it should just hold on the
previous state's result while narration continues -- mark it "hold": true
with an empty "beats" list instead of forcing an ACTION beat.

RULES:
1. Every op listed in a state's "existing_ops" must appear somewhere in that
   state's "beats" -- do not drop any of them.
2. A beat's op may ONLY reference a target/into/anchor identifier already
   listed in that section's "known_identifiers". Never invent a new object.
3. Every beat's "op" must be one of: {ops_list}.
   Required keys per op: {ops_keys}.
4. target/into/anchor values must be short, stable Python identifiers.
5. Never include a duration/timestamp/numeric timing value in a beat.
6. Cover every section and every state listed below -- do not omit any.

Return ONLY valid JSON of this exact shape:
{{
  "sections": [
    {{"index": 1, "states": [
      {{"name": "introduce", "hold": false, "beats": [
        {{"phase": "CONTEXT", "op": "Create", "target": "circle"}}
      ]}}
    ]}}
  ]
}}

SECTIONS:
{json.dumps(sections_payload, ensure_ascii=False, indent=2)}
{repair_text}
""".strip()


# ---------------------------------------------------------------------------
# Main plugin
# ---------------------------------------------------------------------------

class PlannerSemanticPlugin(Plugin):
    """Annotate the validated AnimationIR with a pedagogical phase model."""

    name = "planner_semantic"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "storyboard_plan", "animation_ir"]

    def declare_effects(self) -> list[str]:
        return ["check_results", "semantic_ir"]

    def _repair_feedback(self, context: SceneContext) -> dict[str, list[str]]:
        feedback = getattr(context, "repair_context", {})

        if not isinstance(feedback, dict):
            return {}

        return {
            str(stem): [str(message) for message in messages]
            for stem, messages in feedback.items()
            if isinstance(messages, list)
        }

    def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        if not llm.keys():
            return None

        model = os.environ.get(
            "P2R_SEMANTIC_PLAN_MODEL",
            os.environ.get("P2R_SCENE_MODEL", DEFAULT_MODEL),
        )

        response = llm.complete(
            prompt,
            max_tokens=6000,
            model_env="P2R_SEMANTIC_PLAN_MODEL",
            default_model=model,
            label="semantic_plan",
        )

        return _extract_json(response)

    def _persist(self, context: SceneContext) -> None:
        project_dir = context.project_dir

        if project_dir is None or context.semantic_ir is None:
            return

        _atomic_write_json(
            _harness_dir(project_dir) / SEMANTIC_PLAN_FILE,
            context.semantic_ir.to_dict(),
        )

    def run(self, context: SceneContext) -> SceneContext:
        animation_ir = context.animation_ir

        if animation_ir is None:
            raise RuntimeError(
                "PlannerSemanticPlugin requires animation_ir to be set "
                "(should be unreachable -- verifier_animation_ir gates it)."
            )

        payload = [_section_payload(section) for section in animation_ir.sections]
        feedback = self._repair_feedback(context)
        prompt = _build_prompt(payload, feedback or None)

        project_dir = context.project_dir

        if project_dir is not None:
            (_provenance_dir(project_dir) / SEMANTIC_PLAN_PROMPT_FILE).write_text(
                prompt, encoding="utf-8"
            )

        try:
            raw = self._call_llm(prompt)
        except Exception as exc:
            cfg.warn(f"[planner_semantic] LLM call failed: {exc}")
            raw = None

        if raw is None:
            context.semantic_ir = default_semantic_plan(animation_ir)
            context.check_results[self.name] = []
            self._persist(context)
            return context

        try:
            context.semantic_ir = annotate(animation_ir, raw)
            context.check_results[self.name] = []
        except SemanticPlanValidationError as exc:
            finding = Finding(
                finding_id=next_finding_id("sem"),
                scene_id=exc.stem or "__all__",
                category=Category.STORYBOARD,
                severity=Severity.BLOCKING,
                message=str(exc),
                finding_type="semantic_plan_failure",
            )
            context.check_results[self.name] = [finding.as_check_result()]
            return context

        self._persist(context)
        return context

    def revert_scene(self, context: SceneContext, stem: str) -> None:
        """No mutable "needs repair" marker to set -- ``regenerate_one``
        recomputes the section from scratch each call. This method exists
        purely so ``repair_router``'s ``hasattr`` check finds both methods
        and prefers targeted single-section repair over a full plugin
        re-run."""

        return

    def regenerate_one(self, context: SceneContext, stem: str) -> None:
        animation_ir = context.animation_ir

        if animation_ir is None:
            return

        if context.semantic_ir is None:
            self.run(context)
            return

        source_section = next(
            (s for s in animation_ir.sections if s.stem == stem), None
        )

        if source_section is None:
            return

        feedback = self._repair_feedback(context)
        messages = feedback.get(str(stem), [])

        sub_ir = AnimationIR(
            schema_version=animation_ir.schema_version,
            source_storyboard_version=animation_ir.source_storyboard_version,
            source_hash=animation_ir.source_hash,
            sections=[source_section],
            ir_hash=animation_ir.ir_hash,
        )

        prompt = _build_prompt(
            [_section_payload(source_section)],
            {str(stem): messages} if messages else None,
        )

        try:
            raw = self._call_llm(prompt)
        except Exception as exc:
            cfg.warn(
                f"[planner_semantic] targeted repair LLM call failed for "
                f"{stem}: {exc}"
            )
            return

        if raw is None:
            return

        try:
            partial = annotate(sub_ir, raw)
        except SemanticPlanValidationError as exc:
            cfg.warn(
                f"[planner_semantic] targeted repair for {stem} still "
                f"invalid: {exc}"
            )
            return

        sections = list(context.semantic_ir.sections)

        for i, section in enumerate(sections):
            if section.stem == stem:
                sections[i] = partial.sections[0]
                break
        else:
            return

        context.semantic_ir.sections = sections
        context.semantic_ir.semantic_hash = context.semantic_ir.compute_hash()

        self._persist(context)

    def _default_gate(self) -> bool:
        return True
