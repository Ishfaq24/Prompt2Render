"""Unit tests for multi-speaker narration, speaker tagging, and Kokoro voice routing."""

import pytest
import numpy as np
from prompt2render import project, textseg, voice


def test_parse_front_matter_voices_json():
    raw = """---
title: "Quantum Physics"
voice: "af_heart"
voices: {"Narrator": "am_adam", "Student": "af_bella"}
---
# Content
"""
    meta, body = project._parse_front_matter(raw)
    assert meta["title"] == "Quantum Physics"
    assert meta["voice"] == "af_heart"
    assert meta["voices"] == {"Narrator": "am_adam", "Student": "af_bella"}


def test_parse_front_matter_voices_yaml_indent():
    raw = """---
title: "History of Computing"
voice: "af_heart"
voices:
  Narrator: am_adam
  Student: af_bella
---
# Content
"""
    meta, body = project._parse_front_matter(raw)
    assert meta["title"] == "History of Computing"
    assert meta["voice"] == "af_heart"
    assert meta["voices"] == {"Narrator": "am_adam", "Student": "af_bella"}


def test_parse_front_matter_speakers_yaml():
    raw = """---
title: "Podcast Ep 1"
speakers:
  Host: am_adam
  Guest: af_sky
---
# Content
"""
    meta, body = project._parse_front_matter(raw)
    assert meta["title"] == "Podcast Ep 1"
    assert meta["speakers"] == {"Host": "am_adam", "Guest": "af_sky"}


def test_textseg_sentences_bracket_speakers():
    narration = """[Narrator]: Welcome to the show. We will examine sorting algorithms.

[Student]: What is QuickSort?

[Narrator]: QuickSort is a divide-and-conquer algorithm. [Student]: Is it fast?
"""
    sents = textseg.sentences(narration)
    assert len(sents) == 5

    assert sents[0].speaker == "Narrator"
    assert sents[0].text == "Welcome to the show."

    # Inherits from previous sentence in same paragraph
    assert sents[1].speaker == "Narrator"
    assert sents[1].text == "We will examine sorting algorithms."

    assert sents[2].speaker == "Student"
    assert sents[2].text == "What is QuickSort?"

    assert sents[3].speaker == "Narrator"
    assert sents[3].text == "QuickSort is a divide-and-conquer algorithm."

    assert sents[4].speaker == "Student"
    assert sents[4].text == "Is it fast?"


def test_textseg_sentences_known_speakers_no_bracket():
    narration = """Host: Welcome to the podcast.

Guest: Thank you for having me.
"""
    sents = textseg.sentences(narration, known_speakers={"Host", "Guest"})
    assert len(sents) == 2
    assert sents[0].speaker == "Host"
    assert sents[0].text == "Welcome to the podcast."
    assert sents[1].speaker == "Guest"
    assert sents[1].text == "Thank you for having me."


def test_textseg_fit_to_synthesiser_preserves_speaker():
    sent = textseg.Sentence(
        i=0,
        text="This is a long sentence; and this is the second part.",
        speaker="Narrator",
    )
    # Measure function that forces split: anything > 5 phonemes splits
    pieces = textseg.fit_to_synthesiser(sent, lambda t: len(t), limit=30)
    assert len(pieces) > 1
    for p in pieces:
        assert p.speaker == "Narrator"


def test_voice_settings_with_script():
    class DummyScript:
        meta = {
            "voice": "af_bella",
            "voices": {"Narrator": "am_adam", "Student": "af_bella"},
        }
    
    # 1. Defaults to script meta
    opts = voice.settings(script=DummyScript())
    assert opts["voice"] == "af_bella"
    assert opts["voices"] == {"Narrator": "am_adam", "Student": "af_bella"}

    # 2. CLI flag overrides default voice
    class DummyArgs:
        voice = "am_michael"
    opts2 = voice.settings(args=DummyArgs(), script=DummyScript())
    assert opts2["voice"] == "am_michael"
    assert opts2["voices"] == {"Narrator": "am_adam", "Student": "af_bella"}


def test_voice_meta_includes_voices():
    meta1 = voice._meta("kokoro", "af_heart", 1.0, "Hello", {}, 1, 100,
                        speaker_voices={"Narrator": "am_adam"})
    meta2 = voice._meta("kokoro", "af_heart", 1.0, "Hello", {}, 1, 100,
                        speaker_voices={"Narrator": "af_bella"})
    
    # Different speaker voices produce different meta dicts, invalidating stale cache
    assert meta1["voices"] != meta2["voices"]
    assert meta1 != meta2


def test_voice_synthesise_multi_speaker(monkeypatch: pytest.MonkeyPatch):
    class FakeKokoro:
        def get_voices(self):
            return ["am_eric", "am_adam", "af_bella"]
        
        def create(self, text, voice="am_eric", speed=1.0, lang="en-us"):
            # Return dummy audio array and sample rate
            return np.zeros(2400, dtype=np.float32), 24000

    fake_k = FakeKokoro()
    monkeypatch.setattr(voice, "kokoro", lambda: fake_k)

    captured_voices = []
    def fake_synth_one(args):
        text, v, speed = args
        captured_voices.append((text, v))
        return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr(voice, "_synth_one", fake_synth_one)

    sents = [
        textseg.Sentence(i=0, text="Hello from narrator.", speaker="Narrator"),
        textseg.Sentence(i=1, text="Hello from student.", speaker="Student"),
        textseg.Sentence(i=2, text="Default voice line.", speaker=None),
    ]

    spk_map = {"Narrator": "am_adam", "Student": "af_bella"}
    pcm, cues = voice.synthesise(
        sents,
        voice="am_eric",
        speed=1.0,
        pauses={"sentence": 300, "paragraph": 500, "clause": 150, "question": 350},
        speaker_voices=spk_map,
    )

    assert len(cues) == 3
    assert cues[0].speaker == "Narrator"
    assert cues[1].speaker == "Student"
    assert cues[2].speaker is None

    # Check routed voices
    assert captured_voices[0] == ("Hello from narrator.", "am_adam")
    assert captured_voices[1] == ("Hello from student.", "af_bella")
    assert captured_voices[2] == ("Default voice line.", "am_eric")


def test_align_spread_preserves_speaker():
    from prompt2render import align
    sents = [
        textseg.Sentence(i=0, text="First statement.", speaker="Teacher", words=textseg.words("First statement.")),
        textseg.Sentence(i=1, text="Second query.", speaker="Student", words=textseg.words("Second query.")),
    ]
    out = align._spread(sents, 5.0)
    assert len(out) == 2
    assert out[0]["speaker"] == "Teacher"
    assert out[1]["speaker"] == "Student"


def test_align_clamp_to_prior_copies_speaker():
    from prompt2render import align
    sents = [
        {"i": 0, "text": "A", "start": 0.0, "end": 1.0, "words": []},
        {"i": 1, "text": "B", "start": 1.0, "end": 2.0, "words": []},
    ]
    priors = [
        voice.Cue(i=0, text="A", start=0.0, end=1.0, speaker="Teacher"),
        voice.Cue(i=1, text="B", start=1.0, end=2.0, speaker="Student"),
    ]
    clamped = align.clamp_to_prior(sents, priors)
    assert clamped[0]["speaker"] == "Teacher"
    assert clamped[1]["speaker"] == "Student"


def test_captions_write_srt_speaker_prefix(tmp_path):
    from prompt2render import captions
    class DummyScript:
        sections = []
    
    # Mock cards_for
    cards = [
        {"start": 0.0, "end": 2.0, "text": "Welcome to class.", "speaker": "Teacher"},
        {"start": 2.2, "end": 4.5, "text": "What is an array?", "speaker": "Student"},
        {"start": 4.6, "end": 6.0, "text": "[Student] Already prefixed.", "speaker": "Student"},
    ]
    dst = tmp_path / "captions.srt"
    
    # Monkeypatch cards_for
    import unittest.mock as mock
    with mock.patch("prompt2render.captions.cards_for", return_value=cards):
        captions.write_srt(tmp_path, DummyScript(), dst)
    
    content = dst.read_text(encoding="utf-8")
    assert "[Teacher] Welcome to class." in content
    assert "[Student] What is an array?" in content
    assert "[Student] Already prefixed." in content
    # Ensure no double prefix
    assert "[Student] [Student]" not in content


def test_captions_write_ass_speaker_and_style(tmp_path):
    from prompt2render import captions
    class DummyScript:
        sections = []
    
    cards = [
        {"start": 0.0, "end": 2.0, "text": "Hello.", "words": [], "speaker": "Teacher"},
        {"start": 2.0, "end": 4.0, "text": "Hi.", "words": [], "speaker": "Student"},
    ]
    dst = tmp_path / "captions.ass"
    
    import unittest.mock as mock
    with mock.patch("prompt2render.captions.cards_for", return_value=cards):
        captions.write_ass(tmp_path, DummyScript(), dst)
    
    content = dst.read_text(encoding="utf-8")
    assert "Style: Teacher," in content
    assert "Style: Student," in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Teacher,Teacher,0,0,0,,Hello." in content
    assert "Dialogue: 0,0:00:02.00,0:00:04.00,Student,Student,0,0,0,,Hi." in content


def test_multilingual_edge_tts_speaker_voices():
    from prompt2render.multilingual.voice_service import EdgeTTSProvider
    provider = EdgeTTSProvider()
    
    # Defaults for English
    assert provider.resolve_voice("en", "Hello", speaker="Teacher") == "en-US-ChristopherNeural"
    assert provider.resolve_voice("en", "Why?", speaker="Student") == "en-US-JennyNeural"
    
    # Defaults for Urdu
    assert provider.resolve_voice("ur", "آداب", speaker="Teacher") == "ur-PK-AsadNeural"
    assert provider.resolve_voice("ur", "سوال", speaker="Student") == "ur-PK-UzmaNeural"
    
    # Defaults for Hindi
    assert provider.resolve_voice("hi", "नमस्ते", speaker="Teacher") == "hi-IN-MadhurNeural"
    assert provider.resolve_voice("hi", "सवाल", speaker="Student") == "hi-IN-SwaraNeural"
    
    # Custom mapping override
    custom_map = {"Teacher": "en-GB-RyanNeural", "Student": "en-GB-SoniaNeural"}
    assert provider.resolve_voice("en", "Test", speaker="Teacher", speaker_voices=custom_map) == "en-GB-RyanNeural"
    assert provider.resolve_voice("en", "Test", speaker="Student", speaker_voices=custom_map) == "en-GB-SoniaNeural"


def test_scenes_build_prompt_includes_speaker_tag():
    from prompt2render import scenes
    class DummySec:
        index = 1
        title = "Introduction"
        anim = "Show array"
    
    class DummyScript:
        title = "Pointers"
        meta = {"audience": "undergrads"}
    
    sents = [
        {"start": 0.0, "end": 2.0, "text": "Pointers hold memory addresses.", "speaker": "Teacher"},
        {"start": 2.5, "end": 5.0, "text": "Can a pointer be null?", "speaker": "Student"},
    ]
    prompt = scenes.build_prompt(DummyScript(), DummySec(), sents)
    assert "[Teacher] Pointers hold memory addresses." in prompt
    assert "[Student] Can a pointer be null?" in prompt
    assert "MULTI-VOICE PEDAGOGICAL DIALOGUE" in prompt


def test_draft_build_prompt_dialogue_rules():
    from prompt2render import draft
    class DummySec:
        index = 1
        title = "Stack Frames"
        anim = "Push frame"
        narration = ""
    
    class DummyScript:
        title = "Call Stack"
        meta = {"topic": "Call Stack", "audience": "students", "voices": {"Teacher": "af_heart", "Student": "am_adam"}}
        sections = [DummySec()]
    
    prompt = draft.build_prompt(DummyScript(), [DummySec()], dialogue=True)
    assert "PEDAGOGICAL DIALOGUE (MANDATORY FORMAT)" in prompt
    assert "[Teacher]" in prompt
    assert "[Student]" in prompt

