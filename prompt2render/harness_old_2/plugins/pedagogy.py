"""Educational quality stages that run before voice and scene generation."""
from __future__ import annotations

import json
from pathlib import Path

from ..context import SceneContext, ScenePlanEntry
from ..plugin import Plugin
from ... import pedagogy
from ...project import parse_script


def _save(proj: Path, value: dict) -> None:
    out = proj / "build" / "harness"
    out.mkdir(parents=True, exist_ok=True)
    (out / "pedagogy_review.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _refresh_plan(context: SceneContext) -> None:
    script = parse_script(context.prompt)
    context.scene_plan = [
        ScenePlanEntry(index=s.index, stem=s.stem, title=s.title,
                       anim=s.anim, narration_text=s.narration)
        for s in script.sections
    ]


class PlannerPedagogyPlugin(Plugin):
    name = "planner_pedagogy"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["pedagogy_review"]

    def run(self, context: SceneContext) -> SceneContext:
        script = parse_script(context.prompt)
        review = pedagogy.review_script(script)
        context.pedagogy_review = review
        _save(context.project_dir, review)
        return context


class ReviserScriptPlugin(Plugin):
    name = "reviser_script"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "pedagogy_review"]

    def declare_effects(self) -> list[str]:
        return ["script_artifact", "scene_plan", "pedagogy_review"]

    def run(self, context: SceneContext) -> SceneContext:
        script = parse_script(context.prompt)
        review = context.pedagogy_review
        max_revisions = max(0, int(self.config.get("max_revisions", 2)))
        for cycle in range(max_revisions + 1):
            if review.get("pass") or cycle == max_revisions:
                break
            before = (context.prompt.read_text(encoding="utf-8")
                      if context.prompt else "")
            script, _ = pedagogy.revise_script(
                context.project_dir, script, review,
                label=f"pedagogy revision {cycle + 1}")
            after = context.prompt.read_text(encoding="utf-8") if context.prompt else ""
            if before == after:
                break
            review = pedagogy.review_script(script, label=f"pedagogy recheck {cycle + 1}")
            context.pedagogy_review = review
            _save(context.project_dir, {**review, "revision_cycle": cycle + 1})
        _refresh_plan(context)
        context.pedagogy_review = review
        return context


class VerifierPedagogyPlugin(Plugin):
    name = "verifier_pedagogy"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "pedagogy_review"]

    def declare_effects(self) -> list[str]:
        return ["check_results", "pedagogy_verified"]

    def run(self, context: SceneContext) -> SceneContext:
        review = context.pedagogy_review
        issues = review.get("issues", []) if isinstance(review, dict) else []
        blocking = [i for i in issues if isinstance(i, dict) and i.get("severity") == "blocking"]
        status = "fail" if blocking or not review.get("pass", False) else "pass"
        context.check_results[self.name] = [{
            "status": status,
            "finding_type": "pedagogy_review",
            "detail": review.get("summary", "pedagogy review complete"),
            "score": review.get("score", 0),
            "profile": review.get("profile", "standard"),
            "issues": issues,
        }]
        return context

    def _default_gate(self) -> bool:
        return True
