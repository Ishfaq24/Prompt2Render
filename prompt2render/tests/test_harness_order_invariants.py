from prompt2render.harness.loader import build_plugins


def test_enabled_manim_renderer_still_waits_for_code_and_timeline_waits_for_audio():
    config = {
        # This test exercises generator_code (the default code generator,
        # still enabled) feeding renderer_manim (an alternative renderer) --
        # generator_manim/renderer_manim_finish/verifier_manim_final_qc
        # (Tier 2 Phase 8-9: now real REGISTRY entries) must stay off so
        # they don't collide with their stills-path counterparts below.
        "generator_manim": {"enabled": False},
        "renderer_manim": {"enabled": True},
        "renderer_manim_finish": {"enabled": False},
        "verifier_manim_final_qc": {"enabled": False},
        "renderer_stills": {"enabled": False},
        "verifier_semantic": {"enabled": False},
        "verifier_spatial": {"enabled": False},
        # Tier 3 Phase 11: new REGISTRY entry, would default enabled=True
        # here otherwise (same trap as the Manim-family plugins above).
        "observer_visual": {"enabled": False},
        "verifier_motion": {"enabled": False},
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
