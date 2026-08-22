"""The real Coder role — wraps scenes.py's generate_all() unchanged, including its existing
inline retry-with-feedback loop and Gemini key rotation on 429. Stage 4 extracts that loop into
the general-purpose repair_router; this plugin doesn't touch it.
"""
from __future__ import annotations

from ...context import CodeArtifact, SceneContext
from ...plugin import Plugin
from ....project import parse_script
from ....scenes import generate_all
from ....stills import scene_path


class GeneratorCodePlugin(Plugin):
    name = "generator_code"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan", "narration"]

    def declare_effects(self) -> list[str]:
        return ["code_artifacts"]

    def run(self, context: SceneContext) -> SceneContext:
        # Ensure llm.keys() is monkeypatched for compatibility if missing,
        # because generate_all() will call it.
        from .... import llm
        if not hasattr(llm, "keys"):
            import os
            def _keys():
                ks = [os.environ.get("GEMINI_API_KEY", "")]
                for name, val in sorted(os.environ.items()):
                    if name.startswith("GEMINI_API_KEY_BACKUP") and val:
                        ks.append(val)
                ks = [k for k in ks if k]
                if not ks:
                    import sys
                    sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
                return ks
            llm.keys = _keys

        # scenes.generate_all needs a full Script (title/meta for the prompt) — re-parsing here
        # is the same cheap, pure call chunker_scene already made, not new logic. Section
        # selection follows scene_plan (what earlier plugins decided is in scope), not the raw
        # parse, so an upstream filter/reorder is respected.
        script = parse_script(context.prompt)
        indices = {e.index for e in context.scene_plan}
        script.sections = [s for s in script.sections if s.index in indices]
        
        # Inject the modified `anim` from the harness scene_plan back into the 
        # script sections so that `planner_llm` and `retriever_manim_rag` additions
        # actually reach the prompt.
        plan_by_index = {e.index: e for e in context.scene_plan}
        for sec in script.sections:
            if sec.index in plan_by_index:
                sec.anim = plan_by_index[sec.index].anim

        retries = int(self.config.get("retries", 3))
        jobs = self.config.get("jobs")
        generate_all(context.project_dir, script, retries=retries, jobs=jobs)

        for entry in context.scene_plan:
            p = scene_path(context.project_dir, entry.stem)
            context.code_artifacts[entry.stem] = CodeArtifact(
                stem=entry.stem, path=p if p.exists() else None, accepted=p.exists())
        return context

    # ------------------------------------------------------- repair_router (Stage 4) hooks --

    def revert_scene(self, context: SceneContext, stem: str) -> None:
        """Undo this plugin's effect for one section only, per repair_router's per-scene cycle.

        generate_all() skips any section whose scene_<stem>.py already exists on disk ("scene
        already written, skipping — delete it to regenerate") — so a real per-scene revert has to
        delete that file, not just clear the in-memory field, or regenerate_one() below would
        silently no-op.
        """
        p = scene_path(context.project_dir, stem)
        p.unlink(missing_ok=True)
        context.code_artifacts.pop(stem, None)
        context.render_artifacts.pop(stem, None)

    def regenerate_one(self, context: SceneContext, stem: str) -> None:
        """Re-run generation for exactly one section, feeding repair_router's accumulated"""
        from .... import llm
        if not hasattr(llm, "keys"):
            import os
            def _keys():
                ks = [os.environ.get("GEMINI_API_KEY", "")]
                for name, val in sorted(os.environ.items()):
                    if name.startswith("GEMINI_API_KEY_BACKUP") and val:
                        ks.append(val)
                ks = [k for k in ks if k]
                if not ks:
                    import sys
                    sys.exit("[prompt2render] GEMINI_API_KEY not set (it lives in .env)")
                return ks
            llm.keys = _keys
            
        """Re-run generation for exactly one section, feeding repair_router's accumulated
        diagnostics in as scenes.generate()'s new `extra_feedback` parameter (Stage 4 addition —
        see scenes.py). Note: scenes.generate() already re-renders and re-audits internally
        before returning (its own accept/reject loop), so a successful call here already implies
        the section passed verifier_spatial's check — no separate re-verification step is needed
        for that finding type.
        """
        script = parse_script(context.prompt)
        sec = next(s for s in script.sections if s.stem == stem)
        
        # Inject the modified `anim` for this specific section during repair
        plan_entry = next((e for e in context.scene_plan if e.stem == stem), None)
        if plan_entry:
            sec.anim = plan_entry.anim
            
        msgs = context.repair_context.get(stem, [])
        extra_feedback = ("\n\nPRIOR REPAIR FEEDBACK:\n" + "\n".join(msgs)) if msgs else ""
        retries = int(self.config.get("retries", 3))

        from ....scenes import generate as generate_one
        generate_one(context.project_dir, script, sec.index, retries=retries,
                    extra_feedback=extra_feedback)

        p = scene_path(context.project_dir, stem)
        context.code_artifacts[stem] = CodeArtifact(
            stem=stem, path=p if p.exists() else None, accepted=p.exists())
