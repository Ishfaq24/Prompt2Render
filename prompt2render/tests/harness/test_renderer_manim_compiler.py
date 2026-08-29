"""Tests for the Phase 2 deterministic Manim construct() compiler.

No LLM/Manim invoked — these exercise the pure compiler functions directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.animation_ir import from_storyboard_plan
from prompt2render.harness.context import SceneContext
from prompt2render.harness.plugins.renderer_manim import (
    _compile_construct_method,
    _state_cue_timings,
    _states_from_semantic_ir,
    _storyboard_states_for,
)
from prompt2render.harness.semantic_plan import annotate


# ------------------------------------------------------------------ _state_cue_timings --

def test_state_cue_timings_telescopes_to_total_duration():
    sentences = [{"start": 0.0, "end": 4.0}, {"start": 4.5, "end": 9.0}, {"start": 9.5, "end": 12.0}]
    states = [{"cue": 0}, {"cue": 1}, {"cue": 2}]
    timings = _state_cue_timings(states, sentences, duration=12.0)
    assert len(timings) == 3
    total = sum(t["run_time"] + t["wait"] for t in timings)
    assert abs(total - 12.0) < 1e-6


def test_state_cue_timings_empty_states_returns_empty():
    assert _state_cue_timings([], [{"start": 0, "end": 1}], duration=5.0) == []


def test_state_cue_timings_uses_true_end_not_duration_when_gaps_exist():
    # Regression: a real e2e run showed every generated Manim clip falling
    # ~2-3s short of its narration target. Root cause: `duration` (passed
    # in from _load_timing) is sum(sentence durations), which EXCLUDES
    # inter-sentence gaps -- e.g. real align data for one section had
    # sum(dur)=50.20s but the true last-sentence-end was 52.12s (1.92s of
    # accumulated inter-sentence silence). The old code used `duration` as
    # the last state's slot boundary as if it were an absolute timestamp,
    # silently truncating the final state's slot by the sum of every gap
    # in the section. Real fixture below, from that same section.
    sentences = [
        {"start": 0.00, "end": 9.13},
        {"start": 9.45, "end": 14.46},
        {"start": 14.78, "end": 24.62},
        {"start": 24.94, "end": 31.34},
        {"start": 31.66, "end": 40.77},
        {"start": 41.09, "end": 43.97},
        {"start": 44.29, "end": 52.12},
    ]
    duration = 50.20  # sum(dur) -- what _load_timing actually computes
    states = [{"cue": 0}, {"cue": 3}, {"cue": 6}]
    timings = _state_cue_timings(states, sentences, duration)
    total = sum(t["run_time"] + t["wait"] for t in timings)
    # Must telescope to the TRUE end (52.12), not the gap-excluding
    # `duration` (50.20) -- that 1.92s is exactly the bug's shortfall.
    assert abs(total - 52.12) < 1e-6
    assert abs(total - duration) > 1.0


def test_state_cue_timings_no_sentences_falls_back_to_zero_starts():
    states = [{"cue": 0}, {"cue": 1}]
    timings = _state_cue_timings(states, None, duration=10.0)
    assert len(timings) == 2
    # With no sentence data every state's cue resolves to start=0, so the
    # first state's slot swallows the whole duration and the second gets a
    # zero-length (still >=0.1 floor) run_time.
    assert timings[0]["run_time"] > 0


# ------------------------------------------------------------------ _compile_construct_method --

def test_compile_construct_emits_grouped_play_and_wait():
    states = [
        {"name": "intro", "motion": [{"op": "Create", "target": "circle"}, {"op": "FadeIn", "target": "label"}]},
    ]
    # run_time (2.0) is within Create's natural duration cap (1.4), so it is
    # NOT capped here -- this test is about grouping/formatting, not capping.
    timings = [{"run_time": 1.2, "wait": 1.5}]
    source = _compile_construct_method(states, timings)
    assert "def construct(self):" in source
    assert "self._state_intro()" in source
    assert "self.play(Create(self.circle), FadeIn(self.label), run_time=1.20)" in source
    assert "self.wait(1.50)" in source


def test_compile_construct_no_motion_folds_wait_into_run_time_budget():
    states = [{"name": "hold", "motion": []}]
    timings = [{"run_time": 2.0, "wait": 1.0}]
    source = _compile_construct_method(states, timings)
    assert "self.play(" not in source
    assert "self.wait(3.00)" in source


def test_layout_contract_requires_safe_zones_and_relative_anchors():
    from prompt2render.harness.plugins.renderer_manim import _layout_contract

    contract = _layout_contract()
    assert "Caption zone" in contract
    assert "same caption mobject" in contract.lower()
    assert "next_to(existing_mobject" in contract
    assert "caption band" in contract.lower()


def test_compile_construct_suppresses_tiny_wait():
    # run_time is already at Create's natural cap (1.4), so no capping
    # occurs and the leftover wait genuinely stays tiny.
    states = [{"name": "s", "motion": [{"op": "Create", "target": "c"}]}]
    timings = [{"run_time": 1.4, "wait": 0.02}]
    source = _compile_construct_method(states, timings)
    assert "self.wait(" not in source


def test_compile_construct_caps_run_time_at_natural_duration():
    # Regression: a real e2e run showed run_time values of 15-30s for a
    # SINGLE Create() of one object, because run_time was simply 85% of the
    # whole narration slot with no ceiling -- rendering as a near-motionless
    # crawl instead of an animation. A wide slot must not stretch the
    # animation; the excess time must become self.wait() instead.
    states = [{"name": "s", "motion": [{"op": "Create", "target": "c"}]}]
    timings = [{"run_time": 20.89, "wait": 3.69}]
    source = _compile_construct_method(states, timings)
    assert "self.play(Create(self.c), run_time=1.40)" in source
    # The capped-away time (20.89 - 1.40) is preserved, not dropped -- it
    # folds into wait so the total slot duration is unchanged.
    assert "self.wait(23.18)" in source


def test_compile_construct_run_time_cap_uses_slowest_simultaneous_op():
    # Ops in one self.play(...) run concurrently, so the cap for a group is
    # the slowest single op's natural duration, not their sum.
    states = [{
        "name": "s",
        "motion": [{"op": "FadeOut", "target": "a"}, {"op": "Create", "target": "b"}],
    }]
    timings = [{"run_time": 10.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert "run_time=1.40)" in source  # max(FadeOut=0.6, Create=1.4)
    assert "self.wait(8.60)" in source


def test_compile_construct_transform_and_moveto_templates():
    states = [{
        "name": "morph",
        "motion": [
            {"op": "Transform", "target": "square", "into": "circle"},
            {"op": "MoveTo", "target": "label", "anchor": "circle"},
        ],
    }]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert "Transform(self.square, self.circle)" in source
    assert "self.label.animate.move_to(self.circle)" in source


def test_compile_construct_raises_on_unknown_op():
    states = [{"name": "s", "motion": [{"op": "Spin", "target": "c"}]}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    try:
        _compile_construct_method(states, timings)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown motion op" in str(exc)


def test_compile_construct_raises_on_missing_required_key():
    states = [{"name": "s", "motion": [{"op": "Transform", "target": "c"}]}]  # missing "into"
    timings = [{"run_time": 1.0, "wait": 0.0}]
    try:
        _compile_construct_method(states, timings)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "missing required key" in str(exc)


def test_compile_construct_empty_states_emits_pass():
    source = _compile_construct_method([], [])
    assert "pass" in source


def test_compile_construct_adds_object_built_via_local_variable_then_assigned():
    # Regression: a real e2e run showed a state whose setup method built a
    # diagram via a local variable across a couple of statements
    # (`group = VGroup(...); group.arrange(...).move_to(...); self.diagram
    # = group` -- ordinary, natural code) rather than one direct
    # `self.diagram = VGroup(...)` assignment. Direct-only Call detection
    # missed it entirely, so it never got a default entrance and never
    # appeared on screen at all despite being fully constructed.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        group = VGroup(Circle(), Square())
        group.arrange(RIGHT, buff=0.2).move_to(ORIGIN)
        self.diagram = group
"""
    states = [{"name": "intro", "motion": []}]
    timings = [{"run_time": 1.0, "wait": 2.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "self.play(FadeIn(self.diagram), run_time=0.70)" in source


def test_compile_construct_adds_objects_from_empty_motion_state():
    # Regression: a real e2e run produced a completely black frame for a
    # section whose only state had an empty motion list. The storyboard
    # contract explicitly allows empty motion ("a state that introduces or
    # changes nothing"), but the LLM's setup method still legally assigns
    # self.title = Text(...) -- and assigning a Mobject to a Python
    # attribute does NOT add it to the Manim scene. Without this fix,
    # nothing the state constructs is ever rendered.
    setup_source = """
from manim import *
class Scene07(Scene):
    def _state_intro(self):
        self.title = Text("Hello")
"""
    states = [{"name": "intro", "motion": []}]
    timings = [{"run_time": 1.0, "wait": 2.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    # Default is a soft FadeIn, not an instant self.add() -- a fully
    # degraded storyboard (e.g. planner_llm._fallback(), which always
    # declares zero motion) must still animate, not render statically.
    # FadeIn's natural duration (0.7) caps the requested 1.0 down.
    assert "self.play(FadeIn(self.title), run_time=0.70)" in source
    assert "self.add(" not in source


def test_compile_construct_does_not_duplicate_fadein_for_introduced_target():
    # An object that a motion op already introduces (Create/Write/FadeIn)
    # must NOT also get a redundant default FadeIn -- Create already
    # brings it on screen.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.circle = Circle()
"""
    states = [{"name": "intro", "motion": [{"op": "Create", "target": "circle"}]}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert source.count("self.circle") == 1
    assert "Create(self.circle)" in source


def test_compile_construct_does_not_reintroduce_object_from_earlier_state():
    # An object created in an earlier state (continuity) and merely acted
    # on later (e.g. FadeOut) must not get a default FadeIn -- it's
    # already on screen.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.circle = Circle()

    def _state_outro(self):
        pass
"""
    states = [
        {"name": "intro", "motion": [{"op": "Create", "target": "circle"}]},
        {"name": "outro", "motion": [{"op": "FadeOut", "target": "circle"}]},
    ]
    timings = [{"run_time": 1.0, "wait": 0.0}, {"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "FadeIn(self.circle)" not in source
    assert "FadeOut(self.circle)" in source


def test_compile_construct_does_not_reintroduce_object_redundantly_reassigned_later():
    # Regression: a real e2e LLM run redundantly re-declared
    # `self.circle = Circle(...)` inside a LATER state's own setup method
    # (ordinary, harmless code redundancy an LLM commonly produces) rather
    # than leaving that method's body empty. Per-method-scoped detection
    # alone read that reassignment as "newly introduced" and added a
    # spurious default FadeIn, which combined with the same beat's own
    # FadeOut into a fade-out-then-back-in glitch instead of a clean
    # removal. Detection must track attributes seen in EARLIER states too.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.circle = Circle(radius=1.5, color=BLUE)

    def _state_outro(self):
        self.circle = Circle(radius=1.5, color=BLUE)
"""
    states = [
        {"name": "intro", "motion": [{"op": "Create", "target": "circle"}]},
        {"name": "outro", "motion": [{"op": "FadeOut", "target": "circle"}]},
    ]
    timings = [{"run_time": 1.0, "wait": 0.0}, {"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "FadeIn(self.circle)" not in source
    assert "FadeOut(self.circle)" in source
    # Exactly one play call for outro: FadeOut alone, not FadeOut+FadeIn.
    outro_play = [line for line in source.splitlines() if "FadeOut(self.circle)" in line]
    assert len(outro_play) == 1
    assert "FadeIn" not in outro_play[0]


def test_compile_construct_no_default_entrance_for_transform_or_fadeout_target():
    # Regression: a real e2e run showed a state whose storyboard motion was
    # `Transform(target=a, into=b)` + `FadeOut(target=c)`, where the setup
    # method constructs a, b, AND c (all real constructor calls). Only
    # Create/Write/FadeIn targets were excluded from getting a default
    # entrance, so b and c ALSO got a spurious default FadeIn layered into
    # the SAME self.play(...) call as their own FadeOut/Transform-into --
    # e.g. FadeOut(self.c) and FadeIn(self.c) simultaneously, which is
    # contradictory. Any attribute referenced by ANY op (target/into/
    # anchor) must be excluded, not just the three "entrance" ops.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_s(self):
        self.a = Circle()
        self.b = Square()
        self.c = Triangle()
"""
    states = [{
        "name": "s",
        "motion": [
            {"op": "Transform", "target": "a", "into": "b"},
            {"op": "FadeOut", "target": "c"},
        ],
    }]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "FadeIn(self.b)" not in source
    assert "FadeIn(self.c)" not in source
    assert "Transform(self.a, self.b)" in source
    assert "FadeOut(self.c)" in source


def test_compile_construct_uses_add_not_fadein_for_empty_vgroup():
    # Regression: a real e2e run crashed Manim's file writer animating
    # FadeIn on a statically-empty VGroup() -- a legitimate "progressive
    # construction" pattern (build a container across states via later
    # .add() calls) that this file's own prompt encourages. Empty
    # containers must get a plain self.add(), not FadeIn.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.digit_group = VGroup()
"""
    states = [{"name": "intro", "motion": []}]
    timings = [{"run_time": 1.0, "wait": 2.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "self.add(self.digit_group)" in source
    assert "FadeIn(self.digit_group)" not in source


def test_compile_construct_uses_fadein_for_non_empty_vgroup():
    # A VGroup constructed WITH content is not the empty-container pattern
    # -- it should still get the default FadeIn like any other object.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.grp = VGroup(Circle(), Square())
"""
    states = [{"name": "intro", "motion": []}]
    timings = [{"run_time": 1.0, "wait": 2.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "FadeIn(self.grp)" in source
    assert "self.add(self.grp)" not in source


def test_compile_construct_no_setup_source_skips_fadein_gracefully():
    # Backward compatible: omitting setup_source (as every earlier test in
    # this file does) must not error or change existing behavior.
    states = [{"name": "s", "motion": [{"op": "Create", "target": "c"}]}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert "self.add(" not in source
    assert source.count("FadeIn") == 0


# ------------------------------------------------------------------ _storyboard_states_for --

def test_storyboard_states_for_matches_by_stem():
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 1, "stem": "01", "states": [{"name": "a"}]}]}
    assert _storyboard_states_for(ctx, "01") == [{"name": "a"}]


def test_storyboard_states_for_falls_back_to_index_when_stem_missing():
    # Regression: planner_llm._fallback() historically omitted "stem" on
    # its section dicts (see test_planner_llm_motion.py), so a real e2e run
    # with the storyboard LLM call rate-limited produced sections with no
    # "stem" at all. A stem-only lookup silently found nothing for a
    # section that genuinely existed.
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 1, "states": [{"name": "a"}]}]}
    assert _storyboard_states_for(ctx, "01", index=1) == [{"name": "a"}]


def test_storyboard_states_for_returns_none_when_truly_absent():
    ctx = SceneContext()
    ctx.storyboard_plan = {"sections": [{"index": 2, "stem": "02", "states": []}]}
    assert _storyboard_states_for(ctx, "01", index=1) is None


def test_compile_construct_fades_in_first_caption():
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.caption_intro = Text("First beat.").move_to(DOWN * 3.15)
"""
    states = [{"name": "intro", "motion": []}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    assert "FadeIn(self.caption_intro)" in source
    assert "Transform" not in source


def test_compile_construct_transforms_later_captions_into_the_first():
    # Regression: a real e2e run showed the compiler-backed pipeline
    # dropping on-screen captions entirely once every scene's motion list
    # stopped referencing a "caption" target at all (the storyboard only
    # plans diagram content, not chrome). Caption handling must be
    # structural -- keyed off the `caption_<state name>` naming convention
    # -- not dependent on the storyboard's motion vocabulary, and every
    # later caption must Transform the ORIGINAL caption object rather than
    # independently fading in a second one (which would just reproduce the
    # stacked-caption overlap bug this compiler exists to prevent).
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.caption_intro = Text("First beat.").move_to(DOWN * 3.15)

    def _state_explain(self):
        self.caption_explain = Text("Second beat.").move_to(DOWN * 3.15)

    def _state_outro(self):
        self.caption_outro = Text("Third beat.").move_to(DOWN * 3.15)
"""
    states = [
        {"name": "intro", "motion": []},
        {"name": "explain", "motion": []},
        {"name": "outro", "motion": []},
    ]
    timings = [{"run_time": 1.0, "wait": 0.0}] * 3
    source = _compile_construct_method(states, timings, setup_source=setup_source)

    assert "FadeIn(self.caption_intro)" in source
    # Every later caption transforms the ORIGINAL identity object, never a
    # chain of new-into-new, and never a second independent FadeIn.
    assert "Transform(self.caption_intro, self.caption_explain)" in source
    assert "Transform(self.caption_intro, self.caption_outro)" in source
    assert "FadeIn(self.caption_explain)" not in source
    assert "FadeIn(self.caption_outro)" not in source
    assert source.index("FadeIn(self.caption_intro)") < source.index(
        "Transform(self.caption_intro, self.caption_explain)"
    )
    assert source.index("Transform(self.caption_intro, self.caption_explain)") < source.index(
        "Transform(self.caption_intro, self.caption_outro)"
    )


def test_compile_construct_caption_alongside_ordinary_motion():
    # A caption update must coexist in the SAME self.play(...) call as any
    # ordinary motion the storyboard did plan for that state, not replace it.
    setup_source = """
from manim import *
class Scene01(Scene):
    def _state_intro(self):
        self.circle = Circle()
        self.caption_intro = Text("First beat.").move_to(DOWN * 3.15)
"""
    states = [{"name": "intro", "motion": [{"op": "Create", "target": "circle"}]}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings, setup_source=setup_source)
    play_lines = [line for line in source.splitlines() if "self.play(" in line]
    assert len(play_lines) == 1
    assert "Create(self.circle)" in play_lines[0]
    assert "FadeIn(self.caption_intro)" in play_lines[0]


def test_compile_construct_multiple_states_in_cue_order():
    states = [
        {"name": "a", "motion": [{"op": "Create", "target": "x"}]},
        {"name": "b", "motion": [{"op": "FadeOut", "target": "x"}]},
    ]
    timings = [{"run_time": 1.0, "wait": 0.0}, {"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert source.index("self._state_a()") < source.index("self._state_b()")
    assert source.index("Create(self.x)") < source.index("FadeOut(self.x)")


# ---------------------------------- Tier 2 Phase 4: new Phase-3 ops render --

def test_next_to_compiles_to_relative_positioning():
    states = [{"name": "a", "motion": [{"op": "NextTo", "target": "b", "anchor": "a"}]}]
    timings = [{"run_time": 1.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert "self.b.animate.next_to(self.a)" in source


def test_circumscribe_grow_arrow_uncreate_rotate_all_compile():
    states = [{
        "name": "a",
        "motion": [
            {"op": "Circumscribe", "target": "x"},
            {"op": "GrowArrow", "target": "v"},
            {"op": "Uncreate", "target": "old"},
            {"op": "Rotate", "target": "sq"},
        ],
    }]
    timings = [{"run_time": 2.0, "wait": 0.0}]
    source = _compile_construct_method(states, timings)
    assert "Circumscribe(self.x)" in source
    assert "GrowArrow(self.v)" in source
    assert "Uncreate(self.old)" in source
    assert "Rotate(self.sq, angle=PI/2)" in source


# ------------------------------------------------ _states_from_semantic_ir --

def _ir_pair():
    plan = {
        "version": "2.0",
        "prompt_sha256": "deadbeef",
        "sections": [
            {
                "index": 1,
                "stem": "01",
                "title": "Intro",
                "states": [
                    {
                        "name": "introduce",
                        "cue": 0,
                        "visual": "Show a circle.",
                        "transition": "progressive reveal",
                        "values": [],
                        "motion": [{"op": "Create", "target": "circle"}],
                    },
                    {
                        "name": "pause",
                        "cue": 1,
                        "visual": "Let it sit.",
                        "transition": "hold",
                        "values": [],
                        "motion": [],
                    },
                ],
            }
        ],
    }
    animation_ir = from_storyboard_plan(plan)
    raw = {
        "sections": [
            {
                "index": 1,
                "states": [
                    {
                        "name": "introduce",
                        "hold": False,
                        "beats": [
                            {"phase": "ANTICIPATION", "op": "Circumscribe", "target": "circle"},
                            {"phase": "ACTION", "op": "Create", "target": "circle"},
                        ],
                    },
                    {"name": "pause", "hold": True, "beats": []},
                ],
            }
        ]
    }
    semantic_ir = annotate(animation_ir, raw)
    return animation_ir, semantic_ir


def test_states_from_semantic_ir_flattens_beats_in_phase_order():
    animation_ir, semantic_ir = _ir_pair()
    ctx = SceneContext(animation_ir=animation_ir, semantic_ir=semantic_ir)

    states = _states_from_semantic_ir(ctx, "01")

    assert states is not None
    introduce = states[0]
    assert introduce["visual"] == "Show a circle."
    assert introduce["transition"] == "progressive reveal"
    # ANTICIPATION (Circumscribe) must precede ACTION (Create), even though
    # the raw response above already listed them in that order -- the
    # adapter sorts by phase regardless of response order.
    ops = [op["op"] for op in introduce["motion"]]
    assert ops == ["Circumscribe", "Create"]


def test_states_from_semantic_ir_hold_state_has_empty_motion():
    animation_ir, semantic_ir = _ir_pair()
    ctx = SceneContext(animation_ir=animation_ir, semantic_ir=semantic_ir)

    states = _states_from_semantic_ir(ctx, "01")

    assert states[1]["name"] == "pause"
    assert states[1]["motion"] == []


def test_states_from_semantic_ir_returns_none_without_semantic_ir():
    animation_ir, _ = _ir_pair()
    ctx = SceneContext(animation_ir=animation_ir, semantic_ir=None)
    assert _states_from_semantic_ir(ctx, "01") is None


def test_states_from_semantic_ir_returns_none_without_animation_ir():
    _, semantic_ir = _ir_pair()
    ctx = SceneContext(animation_ir=None, semantic_ir=semantic_ir)
    assert _states_from_semantic_ir(ctx, "01") is None


def test_states_from_semantic_ir_returns_none_for_unmatched_stem():
    animation_ir, semantic_ir = _ir_pair()
    ctx = SceneContext(animation_ir=animation_ir, semantic_ir=semantic_ir)
    assert _states_from_semantic_ir(ctx, "99") is None
