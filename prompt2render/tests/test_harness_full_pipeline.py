from __future__ import annotations

import pytest
from pathlib import Path
import json

from prompt2render.harness.context import SceneContext
from prompt2render.harness.loader import build_plugins
from prompt2render.harness.runner import HarnessRunner
from prompt2render.harness.logging_ import StructuredLogger
from prompt2render.project import Script, Section
from prompt2render import cfg

# Mocking the heavy pipeline steps so we can test the orchestration
@pytest.fixture
def mock_pipeline(monkeypatch):
    import prompt2render.voice
    import prompt2render.align
    import prompt2render.timeline
    import prompt2render.encode
    import prompt2render.finish
    import prompt2render.publish
    import prompt2render.stills
    import prompt2render.qc
    import prompt2render.llm

    # planner_pedagogy/reviser_script/verifier_pedagogy/planner_llm/
    # planner_visual all sit ahead of generator_code in the dependency graph
    # (storyboard_verified/animation_plan require them) and each calls
    # llm.keys() -- which sys.exit()s outright when no real API key is
    # configured, rather than returning an empty list. Faking a key plus an
    # empty completion lets every one of those stages take its own
    # deterministic-fallback path instead of crashing, matching this test's
    # actual goal of exercising artifact flow, not LLM planning quality.
    monkeypatch.setattr(prompt2render.llm, "keys", lambda: ["fake-test-key"])
    monkeypatch.setattr(prompt2render.llm, "complete", lambda *args, **kwargs: "")
    
    def mock_voice_build(proj, script, opts, **kwargs):
        (proj / "build" / "voice" / "01").mkdir(parents=True, exist_ok=True)
        (proj / "build" / "voice" / "01" / "raw.wav").touch()
        (proj / "build" / "voice" / "01" / "sentences.json").touch()
        return proj / "build" / "master.wav"
        
    def mock_align(proj, script, **kwargs):
        (proj / "build" / "align").mkdir(parents=True, exist_ok=True)
        (proj / "build" / "align" / "01.json").write_text('{"sentences": [{"start": 0.0, "end": 1.0, "text": "Test."}], "source": "align"}')
        
    import prompt2render.align
    original_load = prompt2render.align.load
    def _mock_load(p, stem):
        if stem == "01":
            return {"sentences": [{"start": 0.0, "end": 1.0, "text": "Test."}], "source": "align"}
        return original_load(p, stem)
    monkeypatch.setattr(prompt2render.align, "load", _mock_load)
        
    def mock_timeline_build(proj, script, **kwargs):
        (proj / "build").mkdir(parents=True, exist_ok=True)
        (proj / "build" / "plan.json").write_text('{"clips": []}')
        return proj / "build" / "plan.json"
        
    def mock_encode(proj, **kwargs):
        (proj / "build" / "clips").mkdir(parents=True, exist_ok=True)
        (proj / "build" / "clips" / "01.mp4").touch()
        return 0
        
    def mock_finish(proj, script, **kwargs):
        (proj / "out").mkdir(parents=True, exist_ok=True)
        (proj / "out" / "final.mp4").touch()
        (proj / "out" / "captions.srt").touch()
        return proj / "out" / "final.mp4"
        
    def mock_publish(proj, script):
        (proj / "out").mkdir(parents=True, exist_ok=True)
        (proj / "out" / "upload.md").touch()
        return proj / "out" / "upload.md"
        
    monkeypatch.setattr(prompt2render.voice, "build", mock_voice_build)
    monkeypatch.setattr(prompt2render.align, "align", mock_align)
    monkeypatch.setattr(prompt2render.timeline, "build", mock_timeline_build)
    monkeypatch.setattr(prompt2render.encode, "encode", mock_encode)
    monkeypatch.setattr(prompt2render.finish, "finish", mock_finish)
    monkeypatch.setattr(prompt2render.publish, "build_packet", mock_publish)
    monkeypatch.setattr(prompt2render.qc, "check", lambda *args, **kwargs: 0)
    
    # We also need to mock scenes and stills since we're running the full pipeline
    import prompt2render.scenes
    monkeypatch.setattr(prompt2render.scenes, "generate_all", lambda *args, **kwargs: None)
    monkeypatch.setattr(prompt2render.stills, "render_many", lambda *args, **kwargs: None)
    monkeypatch.setattr(prompt2render.stills, "scene_path", lambda proj, stem: proj / "build" / "scenes" / f"scene_{stem}.py")
    monkeypatch.setattr(prompt2render.stills, "stills_dir", lambda proj, stem: proj / "build" / "scenes" / stem)
    monkeypatch.setattr(prompt2render.stills, "is_current", lambda *args, **kwargs: True)
    monkeypatch.setattr(prompt2render.stills, "audit_record", lambda *args, **kwargs: None)

    # generator_code imports generate/is_current/scene_path/stills_dir directly
    # (`from ....scenes import generate`, `from ....stills import is_current, ...`),
    # so patching the attribute on prompt2render.scenes/prompt2render.stills above
    # does not reach generator_code's own already-bound names -- patch those too,
    # on the plugin module that actually holds them.
    import prompt2render.harness.plugins.generator_code as generator_code_module

    monkeypatch.setattr(generator_code_module, "generate", lambda *args, **kwargs: None)
    monkeypatch.setattr(generator_code_module, "is_current", lambda *args, **kwargs: True)
    monkeypatch.setattr(generator_code_module, "scene_path", lambda proj, stem: proj / "build" / "scenes" / f"scene_{stem}.py")
    monkeypatch.setattr(generator_code_module, "stills_dir", lambda proj, stem: proj / "build" / "scenes" / stem)


def test_full_pipeline_harness_orchestration(tmp_path: Path, mock_pipeline):
    script_path = tmp_path / "script.md"
    script_path.write_text("""---
title: Test
---
## 1 - Intro
> ANIM: title card

Test narration.
""")
    
    config = {
        "generator_voice": {"enabled": True},
        "generator_align": {"enabled": True},
        "chunker_scene": {"enabled": True},
        "planner_audio": {"enabled": True},
        "generator_code": {"enabled": True},
        # generator_manim declares the same code_artifacts effect as
        # generator_code (Tier 2 Phase 8-9: now a real REGISTRY entry, no
        # longer hot-swapped in by the CLI) -- must stay off here, same
        # reasoning as renderer_manim below.
        "generator_manim": {"enabled": False},
        "renderer_stills": {"enabled": True},
        # renderer_manim declares the same render_artifacts effect as
        # renderer_stills; this test exercises the stills-based artifact
        # flow, so the alternative Manim backend must stay off.
        "renderer_manim": {"enabled": False},
        "generator_timeline": {"enabled": True},
        "renderer_encode": {"enabled": True},
        "renderer_finish": {"enabled": True},
        # renderer_manim_finish/verifier_manim_final_qc declare the same
        # final_video/check_results effects as their stills counterparts.
        "renderer_manim_finish": {"enabled": False},
        "verifier_manim_final_qc": {"enabled": False},
        "generator_publish": {"enabled": True},
        # Disable verifiers for this test to focus on artifact flow
        "verifier_semantic": {"enabled": False},
        "verifier_execution": {"enabled": False},
        "verifier_spatial": {"enabled": False},
        "verifier_lifecycle": {"enabled": False},
        "verifier_audio": {"enabled": False},
        "verifier_final_qc": {"enabled": True},
        "feedback_hitl": {"enabled": False},
    }
    
    plugins = build_plugins(config=config)
    
    # Ensure the new plugins are in the resolved order
    plugin_names = [p.name for p in plugins]
    assert "generator_voice" in plugin_names
    assert "generator_align" in plugin_names
    assert "generator_timeline" in plugin_names
    assert "renderer_encode" in plugin_names
    assert "renderer_finish" in plugin_names
    assert "generator_publish" in plugin_names
    
    ctx = SceneContext(prompt=script_path, project_dir=tmp_path)
    logger = StructuredLogger(tmp_path / "log.jsonl")
    runner = HarnessRunner(plugins, logger)
    
    # Run the harness
    ctx = runner.run(ctx)
    
    # Verify the artifacts were collected into the context
    assert "01" in ctx.audio_artifacts
    assert ctx.audio_artifacts["01"].raw_wav is not None
    
    assert "01" in ctx.narration
    assert ctx.narration["01"].source == "align"
    
    assert "01" in ctx.video_artifacts
    assert ctx.video_artifacts["01"].clip_mp4 is not None
    assert ctx.video_artifacts["01"].final_mp4 is not None
    
    # Verify the history recorded the execution of the new stages
    history_plugins = [h.plugin for h in ctx.history]
    assert "generator_voice" in history_plugins
    assert "generator_timeline" in history_plugins
    assert "renderer_finish" in history_plugins
