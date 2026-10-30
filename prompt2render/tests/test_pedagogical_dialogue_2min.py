"""End-to-End 2-Minute Test Suite for Multi-Voice Pedagogical Dialogue.

Validates the full pedagogical teacher-student pipeline:
- 2-minute Socratic dialogue script pacing and word targets (~240-280 words)
- Speaker tag parsing and alternation dynamics
- Kokoro & Edge-TTS multi-voice dispatch
- Forced alignment preserving speaker metadata
- SRT and ASS subtitles with speaker attribution and color styles
- SceneKit/Manim prompt generation with dialogue awareness
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock
import numpy as np
import pytest

from prompt2render import align, captions, project, scenes, textseg, voice
from prompt2render.multilingual.voice_service import EdgeTTSProvider, MultilingualVoiceManager


DEMO_SCRIPT_PATH = Path("projects/pedagogical-dialogue-demo/script.md")


def test_2min_dialogue_script_structure():
    """Verify the 2-minute pedagogical dialogue demo script matches 2-minute constraints."""
    assert DEMO_SCRIPT_PATH.exists(), f"Demo script missing at {DEMO_SCRIPT_PATH}"
    script = project.parse_script(DEMO_SCRIPT_PATH)

    assert script.title == "Binary Search: The Power of Logarithmic Halving"
    assert "voices" in script.meta
    assert script.meta["voices"] == {"Teacher": "af_heart", "Student": "am_adam"}
    assert len(script.sections) == 2

    # Pacing check: 2 minutes at 120-140 wpm target requires ~220-280 total words
    total_words = script.word_count
    assert 200 <= total_words <= 300, f"Expected ~240-280 words for 2m dialogue, found {total_words}"

    for sec in script.sections:
        assert sec.title
        assert sec.anim
        assert len(sec.narration.split()) >= 90, f"Section {sec.stem} narration too short"


def test_2min_dialogue_speaker_alternation():
    """Verify that both sections feature alternating Teacher-Student discourse."""
    script = project.parse_script(DEMO_SCRIPT_PATH)
    known = set(script.meta["voices"].keys())

    for sec in script.sections:
        sents = textseg.sentences(sec.narration, known_speakers=known)
        speakers = [s.speaker for s in sents]

        # Both speakers must be present in every section
        assert "Teacher" in speakers, f"Section {sec.stem} lacks Teacher lines"
        assert "Student" in speakers, f"Section {sec.stem} lacks Student lines"

        # Check alternation: conversation must actively transition back and forth
        switches = sum(1 for a, b in zip(speakers, speakers[1:]) if a != b)
        assert switches >= 3, f"Section {sec.stem} only has {switches} speaker transitions"


def test_2min_dialogue_kokoro_voice_dispatch(monkeypatch: pytest.MonkeyPatch):
    """Simulate synthesis across all sentences and verify per-speaker Kokoro voice routing."""
    script = project.parse_script(DEMO_SCRIPT_PATH)
    known = set(script.meta["voices"].keys())

    class FakeKokoro:
        def get_voices(self):
            return ["af_heart", "am_adam"]

        def create(self, text, voice="af_heart", speed=1.0, lang="en-us"):
            return np.zeros(2400, dtype=np.float32), 24000

    monkeypatch.setattr(voice, "kokoro", lambda: FakeKokoro())

    recorded_dispatches: list[tuple[str, str, str]] = []

    def fake_synth_one(args):
        text, v, speed = args
        recorded_dispatches.append((text, v, "Teacher" if v == "af_heart" else "Student"))
        # Return 0.5s of audio per sentence
        return np.zeros(12000, dtype=np.float32), 24000

    monkeypatch.setattr(voice, "_synth_one", fake_synth_one)

    all_cues = []
    total_samples = 0
    spk_map = script.meta["voices"]

    for sec in script.sections:
        sents = textseg.sentences(sec.narration, known_speakers=known)
        pcm, cues = voice.synthesise(
            sents,
            voice="af_heart",
            speed=1.0,
            pauses={"sentence": 300, "paragraph": 500, "clause": 150, "question": 350},
            speaker_voices=spk_map,
        )
        total_samples += len(pcm)
        all_cues.extend(cues)

    # Verify that both voices were actually called
    dispatched_voices = {v for _, v, _ in recorded_dispatches}
    assert "af_heart" in dispatched_voices
    assert "am_adam" in dispatched_voices

    # Verify that each Cue preserved its speaker
    assert any(c.speaker == "Teacher" for c in all_cues)
    assert any(c.speaker == "Student" for c in all_cues)


def test_2min_dialogue_multilingual_voice_resolution():
    """Verify Edge-TTS voice pairing for multilingual dialogue in English, Urdu, and Hindi."""
    provider = EdgeTTSProvider()

    # English Teacher/Student default pair
    assert provider.resolve_voice("en", "Listen carefully", speaker="Teacher") == "en-US-ChristopherNeural"
    assert provider.resolve_voice("en", "Why is that?", speaker="Student") == "en-US-JennyNeural"

    # Hindi Teacher/Student pair
    assert provider.resolve_voice("hi", "ध्यान से देखें", speaker="Teacher") == "hi-IN-MadhurNeural"
    assert provider.resolve_voice("hi", "ऐसा क्यों?", speaker="Student") == "hi-IN-SwaraNeural"

    # Urdu Teacher/Student pair
    assert provider.resolve_voice("ur", "غور سے دیکھیں", speaker="Teacher") == "ur-PK-AsadNeural"
    assert provider.resolve_voice("ur", "کیا وجہ ہے؟", speaker="Student") == "ur-PK-UzmaNeural"

    # Script-level custom voice map override
    custom_voices = {"Teacher": "en-US-GuyNeural", "Student": "en-US-AriaNeural"}
    assert provider.resolve_voice("en", "Line", speaker="Teacher", speaker_voices=custom_voices) == "en-US-GuyNeural"
    assert provider.resolve_voice("en", "Line", speaker="Student", speaker_voices=custom_voices) == "en-US-AriaNeural"


def test_2min_dialogue_alignment_pipeline():
    """Verify that forced alignment spreads sentences across 2 minutes preserving speaker tags."""
    script = project.parse_script(DEMO_SCRIPT_PATH)
    known = set(script.meta["voices"].keys())

    # Section 1: 60.0s target duration
    sec1 = script.sections[0]
    sents1 = textseg.sentences(sec1.narration, known_speakers=known)
    aligned1 = align._spread(sents1, 60.0)

    assert len(aligned1) == len(sents1)
    assert aligned1[0]["start"] == 0.0
    assert aligned1[-1]["end"] == 60.0
    assert all("speaker" in item and item["speaker"] in {"Teacher", "Student"} for item in aligned1)

    # Section 2: 60.0s target duration
    sec2 = script.sections[1]
    sents2 = textseg.sentences(sec2.narration, known_speakers=known)
    aligned2 = align._spread(sents2, 60.0)

    assert len(aligned2) == len(sents2)
    assert aligned2[0]["start"] == 0.0
    assert aligned2[-1]["end"] == 60.0
    assert all("speaker" in item and item["speaker"] in {"Teacher", "Student"} for item in aligned2)


def test_2min_dialogue_subtitles_srt_and_ass(tmp_path: Path):
    """Verify that SRT and ASS subtitles format speaker tags and separate styles."""
    script = project.parse_script(DEMO_SCRIPT_PATH)
    known = set(script.meta["voices"].keys())

    sents1 = textseg.sentences(script.sections[0].narration, known_speakers=known)
    aligned1 = align._spread(sents1, 60.0)

    # Mock cards_for with the aligned sentences
    mock_cards = [
        {"start": s["start"], "end": s["end"], "text": s["text"], "speaker": s["speaker"], "words": []}
        for s in aligned1
    ]

    srt_path = tmp_path / "captions.srt"
    ass_path = tmp_path / "captions.ass"

    with mock.patch("prompt2render.captions.cards_for", return_value=mock_cards):
        captions.write_srt(tmp_path, script, srt_path)
        captions.write_ass(tmp_path, script, ass_path)

    # Validate SRT content has [Teacher] and [Student]
    srt_content = srt_path.read_text(encoding="utf-8")
    assert "[Teacher]" in srt_content
    assert "[Student]" in srt_content
    assert "one million numbers" in srt_content

    # Validate ASS content has Teacher and Student styles and actors
    ass_content = ass_path.read_text(encoding="utf-8")
    assert "Style: Teacher," in ass_content
    assert "Style: Student," in ass_content
    assert "Dialogue: 0," in ass_content
    assert ",Teacher,Teacher," in ass_content
    assert ",Student,Student," in ass_content


def test_2min_dialogue_scene_prompt_generation():
    """Verify that scenes.build_prompt injects speaker cues and dialogue rules."""
    script = project.parse_script(DEMO_SCRIPT_PATH)
    known = set(script.meta["voices"].keys())

    sec1 = script.sections[0]
    sents1 = textseg.sentences(sec1.narration, known_speakers=known)
    aligned1 = align._spread(sents1, 60.0)

    prompt = scenes.build_prompt(script, sec1, aligned1)

    # Must contain tagged cues
    assert "[Teacher]" in prompt
    assert "[Student]" in prompt
    # Must contain pedagogical dialogue instructions
    assert "MULTI-VOICE PEDAGOGICAL DIALOGUE" in prompt
    assert "Student speaks/asks a question" in prompt
    assert "Teacher explains" in prompt


def test_2min_dialogue_cli_scaffolding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test CLI scaffolding of a dialogue project with custom speakers."""
    from prompt2render import cli

    class DummyArgs:
        slug = "cli-test-dialogue"
        title = "CLI Test Dialogue"
        minutes = 2.0
        sections = 2
        ai = False
        aspect = "16:9"
        dialogue = True
        speakers = "Teacher=af_nicole,Student=am_michael"

    # Route project directory to tmp_path
    monkeypatch.setattr(cli.cfg, "PROJECTS", tmp_path)

    cli.cmd_new(DummyArgs())

    created_script = tmp_path / "cli-test-dialogue" / "script.md"
    assert created_script.exists()

    content = created_script.read_text(encoding="utf-8")
    assert "voices:" in content
    assert "Teacher: af_nicole" in content
    assert "Student: am_michael" in content
