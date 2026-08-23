"""Harness adapters for the remaining pipeline stages.

This brings voice, align, timeline, encode, finish, and publish inside the
harness, allowing them to be tracked in context history, gated, and skipped
cleanly if an earlier stage failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ..context import AudioArtifact, SceneContext, VideoArtifact
from ..plugin import Plugin
from ... import align, encode, finish, publish, timeline, voice
from ... import cfg


class GeneratorVoicePlugin(Plugin):
    name = "generator_voice"

    def declare_dependencies(self) -> list[str]:
        return ["scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["audio_artifacts"]

    def run(self, context: SceneContext) -> SceneContext:
        script = context.prompt
        from ...project import parse_script
        s = parse_script(script)
        
        # We parse CLI options via environment or config for the harness wrapper
        opts = {
            "backend": self.config.get("backend", "kokoro"),
            "voice": self.config.get("kokoro_voice", "am_eric"),
            "speed": float(self.config.get("kokoro_speed", 1.0)),
            "lufs": float(self.config.get("lufs", cfg.LUFS)),
            "profile": self.config.get("profile", "tts"),
            "pauses": {
                "sentence": cfg.env_int("P2R_PAUSE_SENTENCE_MS", cfg.PAUSE_SENTENCE_MS),
                "question": cfg.PAUSE_QUESTION_MS,
                "clause": cfg.PAUSE_CLAUSE_MS,
                "paragraph": cfg.env_int("P2R_PAUSE_PARAGRAPH_MS", cfg.PAUSE_PARAGRAPH_MS),
            },
        }
        
        try:
            voice.build(context.project_dir, s, opts)
        except SystemExit as exc:
            cfg.warn(f"voice generation failed: {exc}")
            raise
            
        for entry in context.scene_plan:
            base = context.project_dir / "build" / "voice" / entry.stem
            context.audio_artifacts[entry.stem] = AudioArtifact(
                stem=entry.stem,
                raw_wav=base / "raw.wav" if (base / "raw.wav").exists() else None,
                sentences_json=base / "sentences.json" if (base / "sentences.json").exists() else None,
                meta_json=base / "meta.json" if (base / "meta.json").exists() else None,
            )
        return context


class GeneratorAlignPlugin(Plugin):
    name = "generator_align"

    def declare_dependencies(self) -> list[str]:
        return ["audio_artifacts"]

    def declare_effects(self) -> list[str]:
        # planner_audio consumes this through align.load().
        return ["alignment_artifact"]

    def run(self, context: SceneContext) -> SceneContext:
        from ...project import parse_script
        s = parse_script(context.prompt)
        
        try:
            align.align(context.project_dir, s)
        except SystemExit as exc:
            cfg.warn(f"alignment failed: {exc}")
            raise
            
        return context


class GeneratorTimelinePlugin(Plugin):
    name = "generator_timeline"

    def declare_dependencies(self) -> list[str]:
        return ["render_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["timeline_plan"]

    def run(self, context: SceneContext) -> SceneContext:
        from ...project import parse_script
        s = parse_script(context.prompt)
        
        try:
            timeline.build(context.project_dir, s)
        except SystemExit as exc:
            cfg.warn(f"timeline planning failed: {exc}")
            raise
            
        return context


class RendererEncodePlugin(Plugin):
    name = "renderer_encode"

    def declare_dependencies(self) -> list[str]:
        return ["timeline_plan"]

    def declare_effects(self) -> list[str]:
        return ["video_artifacts"]

    def run(self, context: SceneContext) -> SceneContext:
        configured_jobs = self.config.get("jobs")
        jobs = int(configured_jobs) if configured_jobs is not None else cfg.env_int("P2R_ENCODE_JOBS", cfg.default_encode_jobs())
        
        try:
            left = encode.encode(context.project_dir, limit=None, jobs=jobs)
            if left != 0:
                raise SystemExit("encode did not finish all clips")
        except SystemExit as exc:
            cfg.warn(f"encoding failed: {exc}")
            raise
            
        for entry in context.scene_plan:
            clip = context.project_dir / "build" / "clips" / f"{entry.stem}.mp4"
            if clip.exists():
                if entry.stem not in context.video_artifacts:
                    context.video_artifacts[entry.stem] = VideoArtifact(stem=entry.stem)
                context.video_artifacts[entry.stem].clip_mp4 = clip
                
        return context


class RendererFinishPlugin(Plugin):
    name = "renderer_finish"

    def declare_dependencies(self) -> list[str]:
        return ["video_artifacts"]

    def declare_effects(self) -> list[str]:
        return ["final_video"]

    def run(self, context: SceneContext) -> SceneContext:
        from ...project import parse_script
        s = parse_script(context.prompt)
        
        burn = bool(self.config.get("burn", False))
        
        try:
            finish.finish(context.project_dir, s, burn=burn)
        except SystemExit as exc:
            cfg.warn(f"finishing failed: {exc}")
            raise
            
        final = context.project_dir / "out" / "final.mp4"
        srt = context.project_dir / "out" / "captions.srt"
        for entry in context.scene_plan:
            if entry.stem not in context.video_artifacts:
                context.video_artifacts[entry.stem] = VideoArtifact(stem=entry.stem)
            context.video_artifacts[entry.stem].final_mp4 = final if final.exists() else None
            context.video_artifacts[entry.stem].captions_srt = srt if srt.exists() else None
            
        return context


class VerifierFinalQCPlugin(Plugin):
    name = "verifier_final_qc"

    def declare_dependencies(self) -> list[str]:
        return ["final_video"]

    def declare_effects(self) -> list[str]:
        return ["final_qc"]

    def run(self, context: SceneContext) -> SceneContext:
        from ...project import parse_script
        from ... import qc
        script = parse_script(context.prompt)
        strict = bool(self.config.get("strict", False))
        status = qc.check(context.project_dir, script, strict=strict)
        if status:
            context.check_results[self.name] = [{
                "status": "fail",
                "finding_type": "final_qc_failure",
                "detail": "final QC reported a non-shippable result; inspect out/qc.json",
            }]
        else:
            context.check_results[self.name] = [{
                "status": "pass",
                "detail": "final QC reported a shippable result",
            }]
        return context

    def _default_gate(self) -> bool:
        return True


class GeneratorPublishPlugin(Plugin):
    name = "generator_publish"

    def declare_dependencies(self) -> list[str]:
        return ["final_qc"]

    def declare_effects(self) -> list[str]:
        return ["publish_packet"]

    def run(self, context: SceneContext) -> SceneContext:
        from ...project import parse_script
        s = parse_script(context.prompt)
        
        try:
            publish.build_packet(context.project_dir, s)
        except SystemExit as exc:
            cfg.warn(f"publishing failed: {exc}")
            raise
            
        return context
