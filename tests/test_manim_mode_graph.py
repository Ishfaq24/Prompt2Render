from prompt2render.harness.loader import build_plugins
from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin, RendererManimPlugin


def test_manim_graph_has_one_renderer_and_no_still_downstream():
    cfg = {
        "renderer_manim": {"enabled": True},
        "generator_timeline": {"enabled": True},
        "renderer_encode": {"enabled": True},
        "renderer_finish": {"enabled": True},
        "verifier_audio": {"enabled": True},
        "verifier_final_qc": {"enabled": True},
        "generator_publish": {"enabled": True},
    }
    plugins = build_plugins(config=cfg)
    plugins = [GeneratorManimPlugin() if p.name == "generator_code" else p for p in plugins]
    new_plugins = []
    for p in plugins:
        if p.name == "renderer_stills":
            new_plugins.append(RendererManimPlugin({"enabled": True, "gate_override": True}))
        elif p.name != "renderer_manim":
            new_plugins.append(p)
    incompatible = {
        "generator_timeline", "renderer_encode", "renderer_finish",
        "verifier_audio", "verifier_final_qc", "generator_publish",
    }
    plugins = [p for p in new_plugins if p.name not in incompatible]
    names = [p.name for p in plugins]
    assert names.count("renderer_manim") == 1
    assert "generator_manim" in names
    assert not incompatible.intersection(names)
    assert names.index("generator_manim") < names.index("renderer_manim")


def test_manim19_normalizer_repairs_common_llm_aliases():
    from prompt2render.harness.plugins.renderer_manim import _normalize_manim19
    code = 'Code(code_string="x", insert_line_numbers=True)\nlabel.to_corner(UP_LEFT)'
    fixed = _normalize_manim19(code)
    assert 'add_line_numbers=True' in fixed
    assert 'UP_LEFT' not in fixed
    assert 'UL' in fixed

def test_verifier_semantic_uses_multimodal_preview_if_present(tmp_path):
    from prompt2render.harness.plugins.verifier_semantic import VerifierSemanticPlugin
    from prompt2render.harness.context import SceneContext, ScenePlanEntry, CodeArtifact
    
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]
    
    # Mock code artifact
    code_file = tmp_path / "scene_01.py"
    code_file.write_text("pass")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code_file)
    
    # Mock preview image
    preview_dir = tmp_path / "build" / "manim" / "previews"
    preview_dir.mkdir(parents=True)
    preview_img = preview_dir / "Scene01.png"
    preview_img.write_bytes(b"fake_png_data")
    
    # We just want to check if the plugin tries to call the OpenAI client with image_url
    plugin = VerifierSemanticPlugin()
    
    # Patch the llm module locally to avoid real API calls
    import sys
    from unittest.mock import MagicMock
    import prompt2render.harness.plugins.verifier_semantic.__init__ as sem
    
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = '{"status": "pass"}'
    mock_client.chat.completions.create.return_value = mock_resp
    
    # Temporarily replace llm client behavior
    sem.llm.keys = lambda: ["fake_key"]
    sem.llm.client = lambda k: mock_client
    
    # Also remove llm.complete if present so it uses the OpenAI client path
    original_complete = getattr(sem.llm, "complete", None)
    if original_complete:
        delattr(sem.llm, "complete")
        
    plugin.run(ctx)
    
    if original_complete:
        setattr(sem.llm, "complete", original_complete)
        
    # Verify the client was called with the image
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = kwargs["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[1]["type"] == "image_url"
    assert "data:image/png;base64," in content[1]["image_url"]["url"]

def test_manim_normalize_invalid_escapes():
    from prompt2render.harness.plugins.renderer_manim import _normalize_manim19
    # \& should become \\& so it's a valid string literal
    code = r'Text("Apples \& Oranges")'
    norm = _normalize_manim19(code)
    assert norm == r'Text("Apples \\& Oranges")'
