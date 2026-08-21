"""Real wrap of qc.py's caption-drift gate — the closest live analogue to `verifier_audio`.

Structurally whole-video, not per-scene: it re-transcribes the *finished, muxed* out/final.mp4
and aggregates drift across every section into one PASS/WARN/FAIL verdict, run only after
`finish` — a stage entirely outside this harness's scope (see the migration plan's
reconciliation #6 and #9). It can only run when out/final.mp4 already exists (the same
precondition qc.check itself has today); otherwise it reports SKIP, exactly like qc.py's own
missing-prerequisite gates. It structurally cannot participate in repair_router's per-scene
revert/re-invoke loop without new work to make caption-drift per-scene.

Delegates the actual re-transcription to qc.caption_drift(), which is cached by final.mp4's
signature — so a `prompt2render check` and a `tools/harness_run.py` run against the same build
don't each pay for an independent whisper pass over the whole finished video, and this plugin
gets qc's own thread-pool parallelism across sections for free instead of a duplicated serial loop.
"""
from __future__ import annotations

from ...context import SceneContext
from ...plugin import Plugin
from .... import asrmodel, qc
from ....project import parse_script


class VerifierAudioPlugin(Plugin):
    name = "verifier_audio"

    def declare_dependencies(self) -> list[str]:
        # Its real precondition (out/final.mp4) is outside this harness's own field schema — see
        # the module docstring. Declaring render_artifacts too is not a true data dependency, only
        # an ordering one: it keeps this whole-video check running after the per-scene
        # generation/render/verify loop instead of scheduling early just because `narration`
        # alone happens to be satisfied first.
        return ["narration", "render_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        final = context.project_dir / "out" / "final.mp4"
        if not final.exists():
            context.check_results[self.name] = [{
                "status": "skip",
                "detail": "no out/final.mp4 — this harness doesn't run finish; "
                          "run `prompt2render build` (or at least `prompt2render finish`) first",
            }]
            return context

        model = asrmodel.available()
        if model is None:
            context.check_results[self.name] = [{
                "status": "skip", "detail": "no ASR model — cannot verify independently"}]
            return context

        script = parse_script(context.prompt)
        result = qc.caption_drift(context.project_dir, script, final, model)
        context.check_results[self.name] = [result]
        return context
