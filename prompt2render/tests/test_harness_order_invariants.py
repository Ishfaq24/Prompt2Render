from prompt2render.harness.loader import build_plugins


def test_enabled_manim_renderer_still_waits_for_code_and_timeline_waits_for_audio():
    config = {
        "renderer_manim": {"enabled": True},
        "renderer_stills": {"enabled": False},
        "verifier_semantic": {"enabled": False},
        "verifier_spatial": {"enabled": False},
        "verifier_lifecycle": {"enabled": False},
        "verifier_audio": {"enabled": False},
        "feedback_hitl": {"enabled": False},
        "verifier_final_qc": {"enabled": False},
        "generator_publish": {"enabled": False},
    }
    names = [plugin.name for plugin in build_plugins(config=config)]
    assert names.index("generator_code") < names.index("renderer_manim")
    assert names.index("generator_voice") < names.index("generator_align")
    assert names.index("generator_align") < names.index("planner_audio")
    assert names.index("renderer_manim") < names.index("generator_timeline")
