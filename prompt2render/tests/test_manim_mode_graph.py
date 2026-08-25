from prompt2render.harness.loader import build_plugins
from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin


def test_manim_graph_has_one_renderer_and_no_still_downstream():
    cfg = {
        "renderer_manim": {"enabled": True},
        # renderer_stills and renderer_manim both declare the render_artifacts
        # effect, so exactly one may be enabled -- this mirrors what the real
        # CLI's --manim flag does (see prompt2render.py's cfg_dict.setdefault
        # calls for renderer_stills/renderer_manim).
        "renderer_stills": {"enabled": False},
        "generator_timeline": {"enabled": True},
        "renderer_encode": {"enabled": True},
        "renderer_finish": {"enabled": True},
        "verifier_audio": {"enabled": True},
        "verifier_final_qc": {"enabled": True},
        "generator_publish": {"enabled": True},
    }
    plugins = build_plugins(config=cfg)
    # generator_manim has no registry entry of its own (it's an alternative
    # implementation swapped in for generator_code, same as the CLI does);
    # renderer_manim, unlike the old diagnosis-log-era code, is already its
    # own correctly-built registry entry and needs no post-hoc replacement.
    plugins = [GeneratorManimPlugin() if p.name == "generator_code" else p for p in plugins]
    incompatible = {
        "generator_timeline", "renderer_encode", "renderer_finish",
        "verifier_audio", "verifier_final_qc", "generator_publish",
    }
    plugins = [p for p in plugins if p.name not in incompatible]
    names = [p.name for p in plugins]
    assert names.count("renderer_manim") == 1
    assert "renderer_stills" not in names
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

def test_verifier_semantic_uses_multimodal_preview_if_present(tmp_path, monkeypatch):
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
    
    # We want to check the plugin routes the preview image through
    # llm.complete() — the shared call site with deterministic key/model
    # rotation — rather than a raw, unprotected client call that has no
    # retry/fallback on a 429.
    plugin = VerifierSemanticPlugin()

    from unittest.mock import MagicMock
    import prompt2render.harness.plugins.verifier_semantic.__init__ as sem

    monkeypatch.setattr(sem.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(sem.llm, "client", lambda k: MagicMock())

    mock_complete = MagicMock(return_value='{"status": "pass"}')
    monkeypatch.setattr(sem.llm, "complete", mock_complete)

    plugin.run(ctx)

    mock_complete.assert_called_once()
    kwargs = mock_complete.call_args.kwargs
    assert kwargs["image_base64"] is not None
    import base64
    assert base64.b64decode(kwargs["image_base64"]) == b"fake_png_data"

def test_manim_normalize_invalid_escapes():
    from prompt2render.harness.plugins.renderer_manim import _normalize_manim19
    # \& should become \\& so it's a valid string literal
    code = r'Text("Apples \& Oranges")'
    norm = _normalize_manim19(code)
    assert norm == r'Text("Apples \\& Oranges")'
