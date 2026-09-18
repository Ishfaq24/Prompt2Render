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
