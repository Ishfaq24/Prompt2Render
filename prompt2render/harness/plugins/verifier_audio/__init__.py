"""Real wrap of qc.py's caption-drift gate — the closest live analogue to `verifier_audio`.

Structurally whole-video, not per-scene: it re-transcribes the *finished, muxed* out/final.mp4
and aggregates drift across every section into one PASS/WARN/FAIL verdict, run only after
`finish` — a stage entirely outside this harness's scope (see the migration plan's
reconciliation #6 and #9). It can only run when out/final.mp4 already exists (the same
precondition qc.check itself has today); otherwise it reports SKIP, exactly like qc.py's own
missing-prerequisite gates. It structurally cannot participate in repair_router's per-scene
revert/re-invoke loop without new work to make caption-drift per-scene.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from ...context import SceneContext
from ...plugin import Plugin
from .... import asrmodel, cfg, qc, voice
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
        amap = voice.audio_map(context.project_dir)

        deltas: list[float] = []
        with tempfile.TemporaryDirectory(prefix="prompt2render-harness-verifier-audio-") as td:
            work = Path(td)
            wav = work / "final.wav"
            cfg.run(["ffmpeg", "-y", "-v", "error", "-i", str(final),
                    "-map", "0:a:0", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
            for sec in script.sections:
                deltas.extend(qc._drift_for_section(
                    sec, context.project_dir, amap["sections"][sec.stem], work, wav, model))

        if not deltas:
            context.check_results[self.name] = [{
                "status": "skip", "detail": "alignment produced nothing to compare"}]
            return context

        deltas.sort()
        p95 = deltas[int(len(deltas) * 0.95)]
        mx = deltas[-1]
        detail = f"p95 {p95*1000:.0f} ms, max {mx*1000:.0f} ms over {len(deltas)} sentences"
        if p95 <= 0.250 and mx <= 0.500:
            status = "pass"
        elif p95 <= 0.400:
            status = "warn"
        else:
            status = "fail"
        context.check_results[self.name] = [{"status": status, "detail": detail}]
        return context
