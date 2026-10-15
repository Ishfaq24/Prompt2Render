"""Full end-to-end production builder for Machine Learning in Kashmiri (کٲشُر).

Generates:
1. projects/machine-learning-kashmiri/script.md
2. High-fidelity Kashmiri TTS audio for all 5 sections (audio/01.wav - 05.wav)
3. Precise audio durations and audio_map.json
4. Production-grade Manim CE scenes (scenes/scene_01.py - scene_05.py)
5. Synchronized subtitles (out/captions.srt)
6. Rendered video sections (sections/01.mp4 - 05.mp4)
7. Concatenated and mastered audio to -14 LUFS YouTube standard
8. Multiplexed broadcast video (out/final.mp4)
9. Release packet (out/upload.md)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from prompt2render import cfg, visuals
from prompt2render.multilingual.voice_service import OnlineTTSProvider

PROJECT_SLUG = "machine-learning-kashmiri"
PROJ_DIR = ROOT / "projects" / PROJECT_SLUG

SECTIONS_DATA = [
    {
        "index": 1,
        "stem": "01",
        "title": "مشین لرننگ کیا چھُ؟ (What is Machine Learning?)",
        "title_en": "What is Machine Learning? Paradigm Shift",
        "anim": "Split comparison between Traditional Programming (Rules + Data = Output) and Machine Learning (Data + Answers = Learned Model)",
        "sentences": [
            "سلام! اَز ہؠچھَو اَسؠ کہ مشین لرننگ کیا چھُ تہٕ یہِ کِتھ پٲٹھؠ چھُ کٲم کران۔",
            "روایتی پروگرامنگ مَنٛز چھُ اِنسان کمپیوٹرس واضح قواعد تہٕ ڈیٹا دِوان، یمہِ سٟتؠ جواب حٲصل گژھان چھُ۔",
            "مگر مشین لرننگ مَنٛز چھُ کمپیوٹر ڈیٹا تہٕ جواباتن ہٕنٛدِ مشاہدٕ سٟتؠ خود بخود قواعِد تلاش کران۔",
            "اَمی کِنؠ چھِ کمپیوٹر وقتَس سٟتؠ سٟتؠ پانہِ سؠکھان تہٕ نٔون مسائلن ہُنٛد حل کڈان۔"
        ]
    },
    {
        "index": 2,
        "stem": "02",
        "title": "مشین لرننگ ہٕنٛدی ترٛے قسٕم (Three Paradigms of Machine Learning)",
        "title_en": "Three Paradigms: Supervised, Unsupervised & Reinforcement Learning",
        "anim": "Three cards displaying Supervised Learning (labeled pairs), Unsupervised Learning (clustering), and Reinforcement Learning (reward loop)",
        "sentences": [
            "مشین لرننگ چھِ بُنیادی طور ترٛؠن اہم قِسمَن مَنٛز تقسیٖم گژھان۔",
            "گوڈنیک چھُ سُوپر وائزڈ لرننگ، یَتھ مَنٛز ماڈلس لیبلڈ ڈیٹا دِنہٕ چھُ یِوان، مِثال کے طور پٲٹھؠ قیمتن ہُنٛد اندازٕ لگاوُن یا امیج کلاسیفیکیشن۔",
            "دویم چھُ اَن سُوپر وائزڈ لرننگ، یَتھ مَنٛز کمپیوٹر بغیر کانہہ لیبل ڈیٹا مَنٛز چھُپیومٕتؠ پیٹرن تہٕ کلسٹرس لَبھان۔",
            "تہٕ ترٛیم چھُ ری اِنفورسمنٹ لرننگ، یَتھ مَنٛز اَکھ ایجنٹ ماحولَس مَنٛز اِنعام تہٕ سزایہِ سٟتؠ سؠکھان چھُ۔"
        ]
    },
    {
        "index": 3,
        "stem": "03",
        "title": "ماڈل کِتھ پٲٹھؠ چھُ سؠکھان؟ لاس فنکشن تہٕ گریڈینٹ ڈیسینٹ (How Models Learn)",
        "title_en": "Loss Function Optimization & Gradient Descent",
        "anim": "Convex Loss parabola J(w) with tangent gradient slope and optimizer ball stepping iteratively down to minimum error",
        "sentences": [
            "ماڈل کِتھ پٲٹھؠ چھُ سؠکھان؟ اَتھ عملہِ مَنٛز چھُ لاس فَنکشن تہٕ گریڈینٹ ڈیسینٹ سارِوٕے کھۄتہٕ اہم کردار ادا کران۔",
            "ماڈل چھُ اَکھ پیش گوئی کران، تہٕ لاس فنکشن چھُ یہِ ناپان زِ ماڈلٕک جواب تہٕ اصل جوابس مَنٛز کِتیا غَلطی یا فرق چھُ۔",
            "اَمہِ پتہٕ چھُ کمپیوٹر گریڈینٹ ڈیسینٹ زریعہٕ ماڈلٕک پیرامیٹرز یعنی ویٹس ایڈجسٹ کران۔",
            "ہر قدمَس سٟتؠ چھِ غلطی کم گژھان، ییتھ کٔنؠ اَکھ بال پھیران ڈھلوان پؠٹھٕ بۄن یِوان تہٕ کم ترین مقامَس پؠٹھ رُکان۔"
        ]
    },
    {
        "index": 4,
        "stem": "04",
        "title": "اوورفِٹِنٛگ بمقابلہ انڈرفِٹِنٛگ (Overfitting vs Underfitting)",
        "title_en": "Underfitting, Balanced Generalization, and Overfitting",
        "anim": "Three regression subplots comparing high bias underfitting, balanced generalization, and high variance overfitting",
        "sentences": [
            "ماڈل ٹریننگ دوران چھِ زٕ اَہَم مَسلہٕ پیش یِوان: اَنڈرفِٹِنٛگ تہٕ اوورفِٹِنٛگ۔",
            "انڈرفٹنگ تِلہِ چھُ گژھان ییلہِ ماڈل سؠٹھا سادہ آسہِ تہٕ ڈیٹا ہُنٛد بنیادی نمونہٕ سمجھی نہِ، یَتھ ہائی بائس ونان چھِ۔",
            "اوورفٹنگ تِلہِ چھُ گژھان ییلہِ ماڈل ڈیٹا ہٕنٛز سارِوٕے آواز تہٕ شور رٹہٕ مارِ، تہٕ نٔوس ڈیٹا ہَس پؠٹھ ناکام گژھِ، یَتھ ہائی ویرینس ونان چھِ۔",
            "اَمہِ موجوب چھُ سانین مقصد اَکھ متوازن ماڈل بناوُن یُس اصل طریقہٕ سٟتؠ جنرلائز کٔرِ۔"
        ]
    },
    {
        "index": 5,
        "stem": "05",
        "title": "اصل دُنیاہَس مَنٛز استعمال تہٕ خلاصہٕ (Real-World Applications & Summary)",
        "title_en": "Real-World Impact & Applications of Machine Learning",
        "anim": "Showcase grid of real-world AI applications including Medical Imaging, Kashmiri Language AI, Autonomous Vehicles, and Summary Badges",
        "sentences": [
            "مشین لرننگ ہُنٛد اِستعمال چھُ اَز کل سانہِ روزمرہ زندگی مَنٛز ہر شعبس مَنٛز گژھان۔",
            "صحت عامہ مَنٛز ایکسرے تہٕ ایم آر آئی اسکینن ہٕنٛز جانچ، خود مختار گاڑؠن ہٕنٛز ڈرائیونگ، تہٕ کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ کرُن اَمیک بہترین مثال چھِ۔",
            "مشین لرننگ چھِ دُنیاہَس بدلاوان، تہٕ یہِ سؠکھُن چھُ مستقبل ہٕنٛدِ خٲطرٕ اَکھ لاجواب صلاحیت۔",
            "اَتھ ویڈیو ہَس مَنٛز شٲمل گژھنہٕ خٲطرٕ بٔڑؠ مہربٲنی، شُکریہ!"
        ]
    }
]

def build_script_markdown() -> str:
    lines = [
        "---",
        "title: \"Machine Learning in Kashmiri: Complete Intuition & Architecture\"",
        "topic: Machine Learning, Supervised Learning, Unsupervised Learning, Reinforcement Learning, Loss Function, Gradient Descent, Overfitting, Generalization",
        "audience: undergraduate computer science & Kashmiri speaking students",
        "aspect: 16:9",
        "language: ks",
        "audio_language: ks",
        "renderer: manim",
        "---",
        ""
    ]
    for sec in SECTIONS_DATA:
        lines.append(f"## {sec['index']} - {sec['title']}")
        lines.append(f"> ANIM: {sec['anim']}")
        lines.append("")
        lines.append(" ".join(sec["sentences"]))
        lines.append("")
    return "\n".join(lines)

def synthesize_section_audio(tts: OnlineTTSProvider, sentences: list[str]) -> tuple[np.ndarray, int]:
    pcm_chunks = []
    sr = 24000
    pause_samples = int(sr * 0.40)  # 400ms natural sentence pause
    pause_pcm = np.zeros(pause_samples, dtype=np.float32)

    for i, sent in enumerate(sentences):
        print(f"    Synthesizing sentence {i+1}/{len(sentences)}...")
        samples, sr = tts.synthesise_sentence(sent, lang_code="ks")
        pcm_chunks.append(samples)
        if i < len(sentences) - 1:
            pcm_chunks.append(pause_pcm)

    lead = np.zeros(int(sr * 0.30), dtype=np.float32)
    tail = np.zeros(int(sr * 0.50), dtype=np.float32)
    full_pcm = np.concatenate([lead, *pcm_chunks, tail])
    return full_pcm, sr

def write_wav(path: Path, pcm: np.ndarray, sr: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    i16 = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(i16.tobytes())

def generate_subtitles(sections: list[dict], audio_durations: dict[str, float]) -> str:
    def fmt_time(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milli = int(round((seconds - int(seconds)) * 1000))
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{milli:03d}"

    blocks = []
    cue_idx = 1
    clock = 0.0

    for sec in sections:
        stem = sec["stem"]
        dur = audio_durations[stem]
        sents = sec["sentences"]
        total_chars = sum(len(s) for s in sents)
        cur_t = clock
        for s in sents:
            prop = len(s) / max(1, total_chars)
            sent_dur = dur * prop
            start_str = fmt_time(cur_t)
            end_str = fmt_time(cur_t + sent_dur)
            blocks.append(f"{cue_idx}\n{start_str} --> {end_str}\n{s.strip()}\n")
            cue_idx += 1
            cur_t += sent_dur
        clock += dur

    return "\n".join(blocks)

if __name__ == "__main__":
    print(f"===========================================================")
    print(f" Prompt2Render: Machine Learning Video in Kashmiri (کٲشُر)")
    print(f"===========================================================")
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    (PROJ_DIR / "audio").mkdir(exist_ok=True)
    (PROJ_DIR / "scenes").mkdir(exist_ok=True)
    (PROJ_DIR / "sections").mkdir(exist_ok=True)
    (PROJ_DIR / "build").mkdir(exist_ok=True)
    (PROJ_DIR / "out").mkdir(exist_ok=True)

    # 1. Write script.md
    script_path = PROJ_DIR / "script.md"
    script_content = build_script_markdown()
    script_path.write_text(script_content, encoding="utf-8")
    print(f"[Stage 1/6] Generated script.md ({len(SECTIONS_DATA)} sections)")

    # 2. Synthesize audio
    tts = OnlineTTSProvider()
    durations = {}
    master_pcm_list = []
    sr = 24000
    cum_time = 0.0
    audio_map = {"sections": {}}

    print(f"[Stage 2/6] Synthesizing Kashmiri Audio Narration for all sections...")
    for sec in SECTIONS_DATA:
        stem = sec["stem"]
        wav_path = PROJ_DIR / "audio" / f"{stem}.wav"
        print(f"  Section {stem}: {sec['title_en']}")
        pcm, sr = synthesize_section_audio(tts, sec["sentences"])
        dur = len(pcm) / sr
        write_wav(wav_path, pcm, sr)
        durations[stem] = dur
        master_pcm_list.append(pcm)
        audio_map["sections"][stem] = {"start": round(cum_time, 3), "dur": round(dur, 3)}
        cum_time += dur
        print(f"    -> Duration: {dur:.2f}s ({dur/60:.2f} min)")

    total_sec = cum_time
    print(f"\nTotal Programme Duration: {total_sec:.2f}s ({total_sec/60:.2f} minutes)")

    amap_path = PROJ_DIR / "build" / "audio_map.json"
    amap_path.write_text(json.dumps(audio_map, indent=2), encoding="utf-8")

    master_pcm = np.concatenate(master_pcm_list)
    master_wav = PROJ_DIR / "build" / "master.wav"
    write_wav(master_wav, master_pcm, sr)
    print(f"[Stage 2/6 Complete] Master audio saved to {master_wav}")

    # 3. Generate captions
    srt_content = generate_subtitles(SECTIONS_DATA, durations)
    srt_file = PROJ_DIR / "out" / "captions.srt"
    srt_file.write_text(srt_content, encoding="utf-8")
    print(f"[Stage 3/6] Captions generated at {srt_file}")
