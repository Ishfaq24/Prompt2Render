from prompt2render.harness.loader import build_plugins
from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin, RendererManimPlugin


def test_manim_graph_has_one_renderer_and_no_still_downstream():
    # In the real CLI, --manim filters out renderer_stills and incompatible plugins 
    # BEFORE calling build_plugins. The test was calling build_plugins first,
    # causing a DependencyError due to duplicate effect producers (like check_results).
    cfg = {
        "renderer_manim": {"enabled": True},
        "generator_timeline": {"enabled": False},
        "renderer_encode": {"enabled": False},
        "renderer_finish": {"enabled": False},
        "verifier_audio": {"enabled": False},
        "verifier_final_qc": {"enabled": False},
        "generator_publish": {"enabled": False},
        "renderer_stills": {"enabled": False},
    }
    
    # We mock the CLI replacement behavior before building
    from prompt2render.harness.plugins import REGISTRY
    from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin, RendererManimPlugin
    
    # Temporarily swap generator_code in registry
    old_gen = REGISTRY.get("generator_code")
    REGISTRY["generator_code"] = GeneratorManimPlugin
    
    try:
        plugins = build_plugins(config=cfg)
        names = [p.name for p in plugins]
        assert names.count("renderer_manim") == 1
        assert "generator_manim" in names
        assert "renderer_stills" not in names
        assert names.index("generator_manim") < names.index("renderer_manim")
    finally:
        if old_gen:
            REGISTRY["generator_code"] = old_gen


def test_manim_graph_verifies_before_rendering():
    """renderer_manim must be structurally unable to run before
    verifier_execution, not merely by accident of registry list order.

    renderer_manim and verifier_execution are both plain consumers of
    code_artifacts, so without an explicit dependency edge between them the
    topological sort treats them as an unordered tie, broken only by
    whichever position each plugin happens to occupy in the input list.
    Feeding resolve_order() an ADVERSARIAL input order — renderer_manim
    listed before verifier_execution — proves it's the dependency edge doing
    the work, not a coincidence of registry order (verifier_execution simply
    happens to be registered earlier than renderer_manim today; a test that
    went through the real registry/build_plugins would pass even without
    the fix and catch nothing).
    """
    from prompt2render.harness.loader import resolve_order
    from prompt2render.harness.plugin import Plugin
    from prompt2render.harness.plugins.verifier_execution import VerifierExecutionPlugin

    class DummyCodeProducer(Plugin):
        # Stands in for generator_manim: only its code_artifacts effect
        # matters here, not its actual (LLM-backed) generation logic.
        name = "generator_manim"

        def declare_dependencies(self):
            return []

        def declare_effects(self):
            return ["code_artifacts"]

        def run(self, context):
            return context

    renderer = RendererManimPlugin({"enabled": True, "gate_override": True})
    verifier = VerifierExecutionPlugin({"enabled": True})
    generator = DummyCodeProducer()

    ordered = resolve_order([renderer, verifier, generator])
    names = [p.name for p in ordered]

    assert names.index("verifier_execution") < names.index("renderer_manim")


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
    
    # We refactored verifier_semantic to use llm.complete directly.
    # Let's mock llm.complete and verify it gets called with image_base64
    mock_complete = MagicMock(return_value='{"status": "pass"}')
    original_complete = getattr(sem.llm, "complete", None)
    setattr(sem.llm, "complete", mock_complete)
    sem.llm.keys = lambda: ["fake_key"]
    
    plugin.run(ctx)
    
    if original_complete:
        setattr(sem.llm, "complete", original_complete)
        
    # Verify llm.complete was called with image_base64
    mock_complete.assert_called_once()
    kwargs = mock_complete.call_args.kwargs
    assert "image_base64" in kwargs
    assert kwargs["image_base64"] == "ZmFrZV9wbmdfZGF0YQ=="  # base64 for 'fake_png_data'

def test_manim_normalize_invalid_escapes():
    from prompt2render.harness.plugins.renderer_manim import _normalize_manim19
    # \& should become \\& so it's a valid string literal
    code = r'Text("Apples \& Oranges")'
    norm = _normalize_manim19(code)
    assert norm == r'Text("Apples \\& Oranges")'
