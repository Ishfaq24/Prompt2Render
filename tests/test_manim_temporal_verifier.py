import pytest
from unittest.mock import patch, MagicMock

def test_verifier_temporal_detects_mismatch(tmp_path):
    from prompt2render.harness.plugins.verifier_temporal import VerifierTemporalPlugin
    from prompt2render.harness.context import SceneContext, ScenePlanEntry
    
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]
    
    from prompt2render.harness.context import CodeArtifact
    code_file = tmp_path / "scene_01.py"
    code_file.write_text("self.wait(1)")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code_file)
    
    # Mock clip path
    clip_dir = tmp_path / "build" / "manim" / "videos" / "scene_01" / "1080p30"
    clip_dir.mkdir(parents=True)
    clip_path = clip_dir / "Scene01.mp4"
    clip_path.touch()
    
    plugin = VerifierTemporalPlugin()
    
    with patch("prompt2render.align.load") as mock_load:
        # Mock narration to require exactly 10.0 seconds
        mock_load.return_value = {"sentences": [{"dur": 5.0, "text": "A"}, {"dur": 5.0, "text": "B"}]}
        
        with patch("subprocess.run") as mock_run:
            # Mock FFprobe returning 8.0 seconds (2.0 seconds too short)
            mock_result = MagicMock()
            mock_result.stdout = "8.0\n"
            mock_run.return_value = mock_result
            
            plugin.run(ctx)
            
            findings = ctx.check_results.get("verifier_temporal", [])
            assert len(findings) == 1
            assert findings[0]["status"] == "fail"
            assert findings[0]["finding_type"] == "temporal_mismatch"
            assert "narration requires 10.00s" in findings[0]["detail"]
            assert "rendered animation is 8.00s" in findings[0]["detail"]

def test_verifier_temporal_detects_missing_wait(tmp_path):
    from prompt2render.harness.plugins.verifier_temporal import VerifierTemporalPlugin
    from prompt2render.harness.context import SceneContext, ScenePlanEntry
    
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]
    
    from prompt2render.harness.context import CodeArtifact
    code_file = tmp_path / "scene_01.py"
    code_file.write_text("self.play(Create(Circle()))")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code_file)
    
    clip_dir = tmp_path / "build" / "manim" / "videos" / "scene_01" / "1080p30"
    clip_dir.mkdir(parents=True)
    clip_path = clip_dir / "Scene01.mp4"
    clip_path.touch()
    
    plugin = VerifierTemporalPlugin()
    
    with patch("prompt2render.align.load") as mock_load:
        # Two sentences with a real inter-sentence gap: cue-sync is necessary here
        mock_load.return_value = {"sentences": [
            {"start": 0.0, "end": 2.0, "dur": 2.0, "text": "A"},
            {"start": 2.5, "end": 5.0, "dur": 2.5, "text": "B"},
        ]}
        
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "5.0\n"
            mock_run.return_value = mock_result
            
            plugin.run(ctx)
            
            findings = ctx.check_results.get("verifier_temporal", [])
            assert len(findings) == 1
            assert findings[0]["status"] == "fail"
            assert findings[0]["finding_type"] == "temporal_mismatch"
            assert "self.wait" in findings[0]["detail"]

def test_verifier_temporal_passes_match(tmp_path):
    from prompt2render.harness.plugins.verifier_temporal import VerifierTemporalPlugin
    from prompt2render.harness.context import SceneContext, ScenePlanEntry
    
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]
    
    from prompt2render.harness.context import CodeArtifact
    code_file = tmp_path / "scene_01.py"
    code_file.write_text("self.wait(1)")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code_file)
    
    clip_dir = tmp_path / "build" / "manim" / "videos" / "scene_01" / "1080p30"
    clip_dir.mkdir(parents=True)
    clip_path = clip_dir / "Scene01.mp4"
    clip_path.touch()
    
    plugin = VerifierTemporalPlugin()
    
    with patch("prompt2render.align.load") as mock_load:
        mock_load.return_value = {"sentences": [{"dur": 10.0, "text": "A"}]}
        
        with patch("subprocess.run") as mock_run:
            # Mock FFprobe returning 10.5 seconds (within 1.5s tolerance)
            mock_result = MagicMock()
            mock_result.stdout = "10.5\n"
            mock_run.return_value = mock_result
            
            plugin.run(ctx)
            
            findings = ctx.check_results.get("verifier_temporal", [])
            assert len(findings) == 1
            assert findings[0]["status"] == "pass"
            assert findings[0]["finding_type"] == "temporal_match"
