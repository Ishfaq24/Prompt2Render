"""High-fidelity end-to-end production builder for Machine Learning in Kashmiri (v2).

Fixes applied:
1. Audio: Edge-TTS neural voice (`ur-IN-SalmanNeural`), 48kHz studio audio mastered to -14 LUFS.
2. Visuals: Complete geometry redesign with VGroup auto-stacking, generous margins, zero overlapping.
3. Video Quality: High-bitrate 1080p Full HD (CRF 17, preset slow, 8 Mbps video, 320 kbps audio).
"""
from __future__ import annotations

import asyncio
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

import edge_tts
from prompt2render import cfg

PROJECT_SLUG = "machine-learning-kashmiri"
PROJ_DIR = ROOT / "projects" / PROJECT_SLUG
SCENES_DIR = PROJ_DIR / "scenes"
SECTIONS_DIR = PROJ_DIR / "sections"
BUILD_DIR = PROJ_DIR / "build"
OUT_DIR = PROJ_DIR / "out"

SECTIONS_DATA = [
    {
        "index": 1,
        "stem": "01",
        "title": "مشین لرننگ کیا چھُ؟ (What is Machine Learning?)",
        "title_en": "What is Machine Learning? Paradigm Shift",
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
        "sentences": [
            "مشین لرننگ ہُنٛد اِستعمال چھُ اَز کل سانہِ روزمرہ زندگی مَنٛز ہر شعبس مَنٛز گژھان۔",
            "صحت عامہ مَنٛز ایکسرے تہٕ ایم آر آئی اسکینن ہٕنٛز جانچ، خود مختار گاڑؠن ہٕنٛز ڈرائیونگ، تہٕ کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ کرُن اَمیک بہترین مثال چھِ۔",
            "مشین لرننگ چھِ دُنیاہَس بدلاوان، تہٕ یہِ سؠکھُن چھُ مستقبل ہٕنٛدِ خٲطرٕ اَکھ لاجواب صلاحیت۔",
            "اَتھ ویڈیو ہَس مَنٛز شٲمل گژھنہٕ خٲطرٕ بٔڑؠ مہربٲنی، شُکریہ!"
        ]
    }
]

async def synth_sentence_neural(text: str, dst_mp3: Path, voice: str = "ur-IN-SalmanNeural") -> None:
    comm = edge_tts.Communicate(text, voice=voice, rate="-2%", pitch="+0Hz")
    await comm.save(str(dst_mp3))

def synthesize_section_audio_highdef(sentences: list[str], stem: str) -> tuple[np.ndarray, int]:
    sr = 48000
    pause_samples = int(sr * 0.35)
    pause_pcm = np.zeros(pause_samples, dtype=np.float32)

    pcm_chunks = []
    temp_dir = BUILD_DIR / "tts_chunks" / stem
    temp_dir.mkdir(parents=True, exist_ok=True)

    for i, sent in enumerate(sentences):
        print(f"    Synthesizing sentence {i+1}/{len(sentences)} with Neural voice...")
        mp3_file = temp_dir / f"sent_{i+1:02d}.mp3"
        wav_file = temp_dir / f"sent_{i+1:02d}.wav"
        asyncio.run(synth_sentence_neural(sent, mp3_file))
        
        # Decode to 48kHz float32
        subprocess.run([
            "ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-y",
            "-i", str(mp3_file),
            "-ar", "48000", "-ac", "1",
            str(wav_file)
        ], check=True)

        with wave.open(str(wav_file), "rb") as wf:
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            pcm_chunks.append(samples)

        if i < len(sentences) - 1:
            pcm_chunks.append(pause_pcm)

    lead = np.zeros(int(sr * 0.25), dtype=np.float32)
    tail = np.zeros(int(sr * 0.45), dtype=np.float32)
    full_pcm = np.concatenate([lead, *pcm_chunks, tail])
    return full_pcm, sr

def write_wav(path: Path, pcm: np.ndarray, sr: int = 48000) -> None:
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

def write_scene_files(durations: dict[str, float]) -> None:
    SCENES_DIR.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # SCENE 01: Clean Paradigm Shift (Zero Overlap)
    # -------------------------------------------------------------------------
    sc1 = f'''from manim import *

class Scene01(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = {durations['01']:.2f}

        # 1. Header Zone (y = 3.3 and 2.8)
        title = Text("Machine Learning: Paradigm Shift", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ کیا چھُ؟ (Rules vs Learning)", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title, shift=DOWN*0.15), FadeIn(subtitle), run_time=1.0)

        # 2. Left Card: Traditional Programming
        card_l = RoundedRectangle(corner_radius=0.2, width=5.4, height=4.2, stroke_color="#334155", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 3.2 + DOWN * 0.55)
        t_l = Text("Traditional Programming", font_size=16, weight=BOLD, color="#94A3B8").move_to(card_l.get_top() + DOWN * 0.35)
        s_l = Text("روایتی پروگرامنگ (قواعد دِنہٕ سٟتؠ)", font="Arial", font_size=11, color="#64748B").next_to(t_l, DOWN, buff=0.08)
        
        box_d = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#475569", fill_color="#1E293B", fill_opacity=0.9).move_to(LEFT * 3.2 + UP * 0.25)
        txt_d = Text("Data (ڈیٹا)", font="Arial", font_size=12, color=WHITE).move_to(box_d.get_center())

        box_r = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#6366F1", fill_color="#312E81", fill_opacity=0.9).move_to(LEFT * 3.2 + DOWN * 0.40)
        txt_r = Text("Rules (قواعد)", font="Arial", font_size=12, color="#A5B4FC").move_to(box_r.get_center())

        arr_l = Arrow(start=LEFT * 3.2 + DOWN * 0.75, end=LEFT * 3.2 + DOWN * 1.35, color="#94A3B8", buff=0.06)

        box_o = RoundedRectangle(corner_radius=0.1, width=3.6, height=0.55, color="#10B981", fill_color="#064E3B", fill_opacity=0.95).move_to(LEFT * 3.2 + DOWN * 1.8)
        txt_o = Text("Output (جواب)", font="Arial", font_size=12, weight=BOLD, color="#34D399").move_to(box_o.get_center())

        grp_left = VGroup(card_l, t_l, s_l, box_d, txt_d, box_r, txt_r, arr_l, box_o, txt_o)

        # 3. Right Card: Machine Learning
        card_r = RoundedRectangle(corner_radius=0.2, width=5.4, height=4.2, stroke_color="#38BDF8", stroke_width=2.5, fill_color="#082F49", fill_opacity=0.88).move_to(RIGHT * 3.2 + DOWN * 0.55)
        t_r = Text("Machine Learning", font_size=18, weight=BOLD, color="#38BDF8").move_to(card_r.get_top() + DOWN * 0.35)
        s_r = Text("مشین لرننگ (ڈیٹا پؠٹھٕ سؠکھُن)", font="Arial", font_size=11, color="#7DD3FC").next_to(t_r, DOWN, buff=0.08)

        box_md = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#0284C7", fill_color="#075985", fill_opacity=0.9).move_to(RIGHT * 3.2 + UP * 0.25)
        txt_md = Text("Historical Data (ڈیٹا)", font="Arial", font_size=12, color=WHITE).move_to(box_md.get_center())

        box_ma = RoundedRectangle(corner_radius=0.1, width=3.4, height=0.48, color="#10B981", fill_color="#064E3B", fill_opacity=0.9).move_to(RIGHT * 3.2 + DOWN * 0.40)
        txt_ma = Text("Answers (ماضی ہٕنٛدِ جواب)", font="Arial", font_size=12, color="#6EE7B7").move_to(box_ma.get_center())

        arr_r = Arrow(start=RIGHT * 3.2 + DOWN * 0.75, end=RIGHT * 3.2 + DOWN * 1.35, color="#38BDF8", buff=0.06)

        box_mo = RoundedRectangle(corner_radius=0.12, width=3.8, height=0.6, color="#F59E0B", fill_color="#78350F", fill_opacity=0.95).move_to(RIGHT * 3.2 + DOWN * 1.8)
        txt_mo = Text("Learned Model (ماڈل)", font="Arial", font_size=13, weight=BOLD, color="#FCD34D").move_to(box_mo.get_center())

        grp_right = VGroup(card_r, t_r, s_r, box_md, txt_md, box_ma, txt_ma, arr_r, box_mo, txt_mo)

        self.play(FadeIn(grp_left, shift=RIGHT*0.25), run_time=1.4)
        self.wait(1.0)
        self.play(FadeIn(grp_right, shift=LEFT*0.25), run_time=1.4)
        self.wait(2.0)

        # Subtle highlight on Learned Model
        ring = RoundedRectangle(corner_radius=0.15, width=4.0, height=0.75, color="#FBBF24", stroke_width=2.5).move_to(box_mo.get_center())
        self.play(Create(ring), run_time=1.0)
        self.play(FadeOut(ring), run_time=0.8)

        elapsed = 1.0 + 1.4 + 1.0 + 1.4 + 2.0 + 1.0 + 0.8
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''
    (SCENES_DIR / "scene_01.py").write_text(sc1, encoding="utf-8")

    # -------------------------------------------------------------------------
    # SCENE 02: Three Paradigms (Zero Overlap)
    # -------------------------------------------------------------------------
    sc2 = f'''from manim import *

class Scene02(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = {durations['02']:.2f}

        title = Text("Three Paradigms of Machine Learning", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("مشین لرننگ ہٕنٛدی ترٛے اہم قسٕم", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # Card 1: Supervised
        c1 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#0284C7", stroke_width=2.0, fill_color="#082F49", fill_opacity=0.9).move_to(LEFT * 4.2 + DOWN * 0.55)
        t1 = Text("Supervised", font_size=16, weight=BOLD, color="#38BDF8").move_to(c1.get_top() + DOWN * 0.35)
        s1 = Text("سُوپر وائزڈ (لیبلڈ ڈیٹا)", font="Arial", font_size=11, color="#7DD3FC").next_to(t1, DOWN, buff=0.08)
        pill1 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#0369A1", fill_color="#075985", fill_opacity=0.85).move_to(c1.get_center() + UP * 0.45)
        ptxt1 = Text("Input X -> Label Y", font_size=10, color=WHITE, weight=BOLD).move_to(pill1.get_center())
        # Visual
        d_a = Dot(point=c1.get_center() + LEFT*0.5 + DOWN*0.2, color="#38BDF8", radius=0.07)
        d_b = Dot(point=c1.get_center() + RIGHT*0.5 + DOWN*0.4, color="#F43F5E", radius=0.07)
        sep_l = Line(start=c1.get_center() + LEFT*0.8 + DOWN*0.6, end=c1.get_center() + RIGHT*0.8 + DOWN*0.0, color="#64748B", stroke_width=1.5)
        b_a1 = Text("• Classification", font_size=11, color="#CBD5E1").move_to(c1.get_bottom() + UP * 0.8)
        b_a2 = Text("• Regression", font_size=11, color="#CBD5E1").next_to(b_a1, DOWN, buff=0.12)
        grp1 = VGroup(c1, t1, s1, pill1, ptxt1, d_a, d_b, sep_l, b_a1, b_a2)

        # Card 2: Unsupervised
        c2 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#10B981", stroke_width=2.0, fill_color="#064E3B", fill_opacity=0.9).move_to(DOWN * 0.55)
        t2 = Text("Unsupervised", font_size=16, weight=BOLD, color="#34D399").move_to(c2.get_top() + DOWN * 0.35)
        s2 = Text("اَن سُوپر وائزڈ (بغیر لیبل)", font="Arial", font_size=11, color="#6EE7B7").next_to(t2, DOWN, buff=0.08)
        pill2 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#047857", fill_color="#065F46", fill_opacity=0.85).move_to(c2.get_center() + UP * 0.45)
        ptxt2 = Text("Unlabeled Patterns", font_size=10, color=WHITE, weight=BOLD).move_to(pill2.get_center())
        # Visual
        cir1 = Circle(radius=0.28, color="#34D399", fill_opacity=0.2).move_to(c2.get_center() + LEFT*0.5 + DOWN*0.3)
        cir2 = Circle(radius=0.28, color="#A78BFA", fill_opacity=0.2).move_to(c2.get_center() + RIGHT*0.5 + DOWN*0.3)
        b_b1 = Text("• Clustering", font_size=11, color="#CBD5E1").move_to(c2.get_bottom() + UP * 0.8)
        b_b2 = Text("• Dimensionality", font_size=11, color="#CBD5E1").next_to(b_b1, DOWN, buff=0.12)
        grp2 = VGroup(c2, t2, s2, pill2, ptxt2, cir1, cir2, b_b1, b_b2)

        # Card 3: Reinforcement
        c3 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#F59E0B", stroke_width=2.0, fill_color="#78350F", fill_opacity=0.9).move_to(RIGHT * 4.2 + DOWN * 0.55)
        t3 = Text("Reinforcement", font_size=16, weight=BOLD, color="#FBBF24").move_to(c3.get_top() + DOWN * 0.35)
        s3 = Text("ری اِنفورسمنٹ (انعام و سزا)", font="Arial", font_size=11, color="#FDE68A").next_to(t3, DOWN, buff=0.08)
        pill3 = RoundedRectangle(corner_radius=0.08, width=2.8, height=0.4, color="#B45309", fill_color="#92400E", fill_opacity=0.85).move_to(c3.get_center() + UP * 0.45)
        ptxt3 = Text("Agent <-> Reward", font_size=10, color=WHITE, weight=BOLD).move_to(pill3.get_center())
        # Visual
        carrow = CurvedArrow(start_point=c3.get_center() + LEFT*0.6 + DOWN*0.35, end_point=c3.get_center() + RIGHT*0.6 + DOWN*0.35, angle=TAU/3, color="#FBBF24")
        b_c1 = Text("• Policy & Rewards", font_size=11, color="#CBD5E1").move_to(c3.get_bottom() + UP * 0.8)
        b_c2 = Text("• Robotics & Games", font_size=11, color="#CBD5E1").next_to(b_c1, DOWN, buff=0.12)
        grp3 = VGroup(c3, t3, s3, pill3, ptxt3, carrow, b_c1, b_c2)

        self.play(FadeIn(grp1, shift=UP*0.2), run_time=1.2)
        self.wait(1.2)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.2)
        self.wait(1.2)
        self.play(FadeIn(grp3, shift=UP*0.2), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.2 + 1.2 + 1.2 + 1.2 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''
    (SCENES_DIR / "scene_02.py").write_text(sc2, encoding="utf-8")

    # -------------------------------------------------------------------------
    # SCENE 03: Loss & Gradient Descent (Zero Overlap)
    # -------------------------------------------------------------------------
    sc3 = f'''from manim import *

class Scene03(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = {durations['03']:.2f}

        title = Text("How Models Learn: Loss & Gradient Descent", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("لاس فنکشن (غلطی ناپن) تہٕ گریڈینٹ ڈیسینٹ", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # Left Card: Formulas
        card_f = RoundedRectangle(corner_radius=0.18, width=5.0, height=4.2, stroke_color="#334155", stroke_width=1.8, fill_color="#0F172A", fill_opacity=0.92).move_to(LEFT * 3.4 + DOWN * 0.55)
        f_top = Text("Optimization Objective", font_size=15, weight=BOLD, color="#38BDF8").move_to(card_f.get_top() + DOWN * 0.35)

        l_txt = Text("1. Mean Squared Error (Loss):", font_size=11, color="#94A3B8").move_to(card_f.get_top() + DOWN * 0.95 + LEFT * 0.4)
        l_mat = MathTex(r"J(w) = \\frac{{1}}{{N}} \\sum_{{i=1}}^{{N}} (y_i - \\hat{{y}}_i)^2", font_size=22, color=YELLOW_C).next_to(l_txt, DOWN, buff=0.18).align_to(l_txt, LEFT)

        u_txt = Text("2. Gradient Descent Step:", font_size=11, color="#94A3B8").move_to(card_f.get_top() + DOWN * 2.15 + LEFT * 0.4)
        u_mat = MathTex(r"w_{{new}} = w_{{old}} - \\alpha \\frac{{\\partial J}}{{\\partial w}}", font_size=22, color="#38BDF8").next_to(u_txt, DOWN, buff=0.18).align_to(u_txt, LEFT)

        badge_k = RoundedRectangle(corner_radius=0.1, width=4.2, height=0.45, color="#059669", fill_color="#064E3B", fill_opacity=0.9).move_to(card_f.get_bottom() + UP * 0.45)
        badge_txt = Text("ہر قدمَس سٟتؠ چھِ غلطی کم گژھان", font="Arial", font_size=11, color="#6EE7B7").move_to(badge_k.get_center())

        grp_left = VGroup(card_f, f_top, l_txt, l_mat, u_txt, u_mat, badge_k, badge_txt)
        self.play(FadeIn(grp_left), run_time=1.4)

        # Right Side: Parabola
        axes = Axes(
            x_range=[-2.2, 2.2, 1],
            y_range=[0, 5, 1],
            x_length=4.8,
            y_length=3.4,
            axis_config={{"color": "#64748B", "stroke_width": 1.8}},
            tips=False
        ).move_to(RIGHT * 3.4 + DOWN * 0.55)

        x_l = Text("Weight (w)", font="Segoe UI", font_size=11, color="#94A3B8").next_to(axes.x_axis, DOWN, buff=0.15).shift(RIGHT * 1.2)
        y_l = Text("Loss J(w)", font="Segoe UI", font_size=11, color="#94A3B8").next_to(axes.y_axis, UP, buff=0.12)

        curve = axes.plot(lambda x: x**2, x_range=[-2.0, 2.0], color="#38BDF8", stroke_width=3.0)
        min_dot = Dot(point=axes.c2p(0, 0), radius=0.07, color="#10B981")
        min_lbl = Text("Minimum w*", font="Segoe UI", font_size=10, color="#10B981", weight=BOLD).next_to(min_dot, UP, buff=0.25)

        self.play(Create(axes), FadeIn(x_l), FadeIn(y_l), Create(curve), run_time=1.5)
        self.play(FadeIn(min_dot), FadeIn(min_lbl), run_time=0.6)

        # Animated ball stepping down
        ball = Dot(point=axes.c2p(1.8, 3.24), radius=0.11, color="#F59E0B")
        ball_tag = Text("Initial Error", font_size=10, color="#FBBF24").next_to(ball, RIGHT, buff=0.1)
        self.play(FadeIn(ball), FadeIn(ball_tag), run_time=0.8)
        self.wait(0.8)

        # Step 1
        self.play(ball.animate.move_to(axes.c2p(1.1, 1.21)), FadeOut(ball_tag), run_time=1.0)
        # Step 2
        self.play(ball.animate.move_to(axes.c2p(0.5, 0.25)), run_time=1.0)
        # Step 3 (Minimum)
        self.play(ball.animate.move_to(axes.c2p(0.0, 0.0)), run_time=1.2)

        glow = Circle(radius=0.3, color="#10B981", stroke_width=2.5).move_to(axes.c2p(0, 0))
        self.play(Create(glow), run_time=0.8)
        self.play(FadeOut(glow), run_time=0.6)

        elapsed = 1.0 + 1.4 + 1.5 + 0.6 + 0.8 + 0.8 + 1.0 + 1.0 + 1.2 + 0.8 + 0.6
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''
    (SCENES_DIR / "scene_03.py").write_text(sc3, encoding="utf-8")

    # -------------------------------------------------------------------------
    # SCENE 04: Overfitting vs Underfitting (Zero Overlap)
    # -------------------------------------------------------------------------
    sc4 = f'''from manim import *
import numpy as np

class Scene04(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = {durations['04']:.2f}

        title = Text("Overfitting vs Underfitting (Generalization)", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("ماڈل پیچیدگی تہٕ متوازن جنرلائزیشن", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        pts_x = [-1.4, -0.9, -0.4, 0.1, 0.6, 1.1, 1.5]
        pts_y = [1.8, 0.9, 0.3, 0.1, 0.4, 1.1, 2.0]

        # Panel 1: Underfitting
        p1 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#EF4444", stroke_width=1.8, fill_color="#450A0A", fill_opacity=0.75).move_to(LEFT * 4.2 + DOWN * 0.55)
        t1 = Text("Underfitting", font_size=16, weight=BOLD, color="#F87171").move_to(p1.get_top() + DOWN * 0.35)
        s1 = Text("انڈرفِٹِنٛگ (زیادٕ سادٕ ماڈل)", font="Arial", font_size=10, color="#FECACA").next_to(t1, DOWN, buff=0.08)
        ax1 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={{"color": "#64748B", "stroke_width": 1.2}}, tips=False).move_to(p1.get_center() + DOWN * 0.2)
        dots1 = VGroup(*[Dot(ax1.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        line_u = ax1.plot(lambda x: 0.9, color="#EF4444", stroke_width=2.5)
        b1 = Text("High Bias (بڑی غلطی)", font="Arial", font_size=11, color="#F87171", weight=BOLD).move_to(p1.get_bottom() + UP * 0.45)
        grp1 = VGroup(p1, t1, s1, ax1, dots1, line_u, b1)

        # Panel 2: Good Fit
        p2 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#10B981", stroke_width=2.2, fill_color="#064E3B", fill_opacity=0.85).move_to(DOWN * 0.55)
        t2 = Text("Optimal Fit", font_size=16, weight=BOLD, color="#34D399").move_to(p2.get_top() + DOWN * 0.35)
        s2 = Text("متوازن ماڈل (اصل جنرلائزیشن)", font="Arial", font_size=10, color="#A7F3D0").next_to(t2, DOWN, buff=0.08)
        ax2 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={{"color": "#64748B", "stroke_width": 1.2}}, tips=False).move_to(p2.get_center() + DOWN * 0.2)
        dots2 = VGroup(*[Dot(ax2.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        curve_opt = ax2.plot(lambda x: 0.7 * x**2 + 0.15, color="#10B981", stroke_width=2.8)
        b2 = Text("Balanced & Robust", font="Segoe UI", font_size=11, color="#34D399", weight=BOLD).move_to(p2.get_bottom() + UP * 0.45)
        grp2 = VGroup(p2, t2, s2, ax2, dots2, curve_opt, b2)

        # Panel 3: Overfitting
        p3 = RoundedRectangle(corner_radius=0.18, width=3.6, height=4.2, stroke_color="#F59E0B", stroke_width=1.8, fill_color="#78350F", fill_opacity=0.75).move_to(RIGHT * 4.2 + DOWN * 0.55)
        t3 = Text("Overfitting", font_size=16, weight=BOLD, color="#FBBF24").move_to(p3.get_top() + DOWN * 0.35)
        s3 = Text("اوورفِٹِنٛگ (رٹہٕ مارُن)", font="Arial", font_size=10, color="#FDE68A").next_to(t3, DOWN, buff=0.08)
        ax3 = Axes(x_range=[-1.8, 1.8, 1], y_range=[-0.2, 2.4, 1], x_length=2.8, y_length=2.0, axis_config={{"color": "#64748B", "stroke_width": 1.2}}, tips=False).move_to(p3.get_center() + DOWN * 0.2)
        dots3 = VGroup(*[Dot(ax3.c2p(x, y), radius=0.05, color="#CBD5E1") for x, y in zip(pts_x, pts_y)])
        curve_over = ax3.plot(lambda x: 0.7*x**2 + 0.15 + 0.28*np.sin(6*x), color="#F59E0B", stroke_width=2.2)
        b3 = Text("High Variance (شور رٹُن)", font="Arial", font_size=11, color="#FBBF24", weight=BOLD).move_to(p3.get_bottom() + UP * 0.45)
        grp3 = VGroup(p3, t3, s3, ax3, dots3, curve_over, b3)

        self.play(FadeIn(grp1, shift=LEFT*0.2), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(grp2, shift=UP*0.2), run_time=1.2)
        self.wait(1.0)
        self.play(FadeIn(grp3, shift=RIGHT*0.2), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.2 + 1.0 + 1.2 + 1.0 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''
    (SCENES_DIR / "scene_04.py").write_text(sc4, encoding="utf-8")

    # -------------------------------------------------------------------------
    # SCENE 05: Real-World Applications & Summary (Zero Overlap)
    # -------------------------------------------------------------------------
    sc5 = f'''from manim import *

class Scene05(Scene):
    def construct(self):
        self.camera.background_color = "#080C16"
        total_time = {durations['05']:.2f}

        title = Text("Real-World Applications of Machine Learning", font_size=24, weight=BOLD, color=WHITE)
        title.to_edge(UP, buff=0.4)
        subtitle = Text("اصل دُنیاہَس مَنٛز استعمال تہٕ اہم خلاصہٕ", font="Arial", font_size=15, color="#38BDF8")
        subtitle.next_to(title, DOWN, buff=0.15)
        self.play(FadeIn(title), FadeIn(subtitle), run_time=1.0)

        # 4 Application Boxes
        # Top Left
        b1 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#0284C7", stroke_width=1.8, fill_color="#082F49", fill_opacity=0.88).move_to(LEFT * 3.2 + UP * 0.65)
        t1 = Text("Medical Imaging & Healthcare", font_size=13, weight=BOLD, color="#38BDF8").move_to(b1.get_top() + DOWN * 0.3)
        d1 = Text("صحت عامہ: ایکس رے تہٕ ایم آر آئی، بیماری تشخیص", font="Arial", font_size=10, color="#CBD5E1").next_to(t1, DOWN, buff=0.12)
        box1 = VGroup(b1, t1, d1)

        # Top Right
        b2 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#10B981", stroke_width=1.8, fill_color="#064E3B", fill_opacity=0.88).move_to(RIGHT * 3.2 + UP * 0.65)
        t2 = Text("Speech & Kashmiri Translation", font_size=13, weight=BOLD, color="#34D399").move_to(b2.get_top() + DOWN * 0.3)
        d2 = Text("کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ تہٕ آواز ہٕنٛز شناخت", font="Arial", font_size=10, color="#CBD5E1").next_to(t2, DOWN, buff=0.12)
        box2 = VGroup(b2, t2, d2)

        # Bottom Left
        b3 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#F59E0B", stroke_width=1.8, fill_color="#78350F", fill_opacity=0.88).move_to(LEFT * 3.2 + DOWN * 0.95)
        t3 = Text("Autonomous Systems & Robotics", font_size=13, weight=BOLD, color="#FBBF24").move_to(b3.get_top() + DOWN * 0.3)
        d3 = Text("خود مختار گاڑؠن ہٕنٛز ڈرائیونگ تہٕ خودکار روبوٹس", font="Arial", font_size=10, color="#CBD5E1").next_to(t3, DOWN, buff=0.12)
        box3 = VGroup(b3, t3, d3)

        # Bottom Right
        b4 = RoundedRectangle(corner_radius=0.14, width=5.4, height=1.35, stroke_color="#8B5CF6", stroke_width=1.8, fill_color="#4C1D95", fill_opacity=0.88).move_to(RIGHT * 3.2 + DOWN * 0.95)
        t4 = Text("Recommendation & Prediction", font_size=13, weight=BOLD, color="#A78BFA").move_to(b4.get_top() + DOWN * 0.3)
        d4 = Text("یوٹیوب، ای کامرس تجاویز تہٕ مالی پیشن گوئی", font="Arial", font_size=10, color="#CBD5E1").next_to(t4, DOWN, buff=0.12)
        box4 = VGroup(b4, t4, d4)

        self.play(FadeIn(box1, shift=RIGHT*0.2), FadeIn(box2, shift=LEFT*0.2), run_time=1.4)
        self.wait(1.0)
        self.play(FadeIn(box3, shift=RIGHT*0.2), FadeIn(box4, shift=LEFT*0.2), run_time=1.4)
        self.wait(2.0)

        # Concluding Banner sitting cleanly BELOW the boxes at y = -2.35
        thx_box = RoundedRectangle(corner_radius=0.15, width=11.2, height=0.85, stroke_color="#38BDF8", stroke_width=2.0, fill_color="#0F172A", fill_opacity=0.98).move_to(DOWN * 2.35)
        thx_txt1 = Text("Machine Learning: Shaping the Future of AI", font_size=13, weight=BOLD, color=WHITE).move_to(thx_box.get_center() + UP * 0.16)
        thx_txt2 = Text("شُکریہ! Thank You for Learning with Prompt2Render", font="Arial", font_size=11, color="#38BDF8").move_to(thx_box.get_center() + DOWN * 0.16)
        thx_grp = VGroup(thx_box, thx_txt1, thx_txt2)

        self.play(FadeIn(thx_grp, shift=UP*0.1), run_time=1.2)
        self.wait(2.0)

        elapsed = 1.0 + 1.4 + 1.0 + 1.4 + 2.0 + 1.2 + 2.0
        rem = max(1.0, total_time - elapsed)
        self.wait(rem)
'''
    (SCENES_DIR / "scene_05.py").write_text(sc5, encoding="utf-8")
    print(f"  Successfully regenerated all 5 Manim scenes with zero-overlap geometry!")

def render_scene(stem: str) -> Path:
    scene_class = f"Scene{stem}"
    py_file = SCENES_DIR / f"scene_{stem}.py"
    work = BUILD_DIR / "manim"
    work.mkdir(parents=True, exist_ok=True)

    print(f"\n>>> Rendering {scene_class} at 1080p Full HD (60 FPS)...")
    cmd = [
        sys.executable, "-m", "manim", "-qh", "--format", "mp4",
        "--fps", "30", "-r", "1920,1080",
        "--media_dir", str(work), str(py_file), scene_class
    ]
    t0 = time.time()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if res.returncode != 0:
        print(f"ERROR rendering {scene_class}:\n{res.stderr or res.stdout}")
        sys.exit(1)

    made = sorted(work.rglob(f"{scene_class}.mp4"), key=lambda p: p.stat().st_mtime_ns)
    if not made:
        sys.exit(f"No {scene_class}.mp4 found under {work}")

    print(f"  Rendered {scene_class} in {time.time() - t0:.1f}s -> {made[-1]}")
    return made[-1]

def normalise_high_quality(src: Path, dst: Path, seconds: float) -> None:
    """Pad/conform clip with high-bitrate libx264 (CRF 17, slow preset)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(seconds * 30))
    vf = (
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps=30,"
        f"tpad=stop_mode=clone:stop_duration={max(seconds, 0):.3f}"
    )
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", vf, "-frames:v", str(frames),
        "-c:v", "libx264", "-crf", "17", "-preset", "slow",
        "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
        "-pix_fmt", "yuv420p", "-an",
        str(dst)
    ]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    print(f"===========================================================")
    print(f" Prompt2Render: Machine Learning Video in Kashmiri (v2)")
    print(f" Studio Audio + Zero-Overlap Visuals + High-Bitrate 1080p")
    print(f"===========================================================")
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    (PROJ_DIR / "audio").mkdir(exist_ok=True)
    (PROJ_DIR / "scenes").mkdir(exist_ok=True)
    (PROJ_DIR / "sections").mkdir(exist_ok=True)
    (PROJ_DIR / "build").mkdir(exist_ok=True)
    (PROJ_DIR / "out").mkdir(exist_ok=True)

    # 1. Synthesize Studio Neural Audio
    print(f"\n[1/5] Synthesizing Studio Neural Voice Narration (Edge-TTS)...")
    durations = {}
    master_pcm_list = []
    sr = 48000
    cum_time = 0.0
    audio_map = {"sections": {}}

    for sec in SECTIONS_DATA:
        stem = sec["stem"]
        wav_path = PROJ_DIR / "audio" / f"{stem}.wav"
        print(f"  Section {stem}: {sec['title_en']}")
        pcm, sr = synthesize_section_audio_highdef(sec["sentences"], stem)
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
    print(f"Master audio saved to {master_wav}")

    # 2. Write Captions
    print(f"\n[2/5] Generating synchronized subtitles...")
    srt_content = generate_subtitles(SECTIONS_DATA, durations)
    srt_file = PROJ_DIR / "out" / "captions.srt"
    srt_file.write_text(srt_content, encoding="utf-8")
    print(f"Captions generated at {srt_file}")

    # 3. Generate Non-Overlapping Manim Scenes
    print(f"\n[3/5] Generating non-overlapping Manim scenes synchronized to exact audio...")
    write_scene_files(durations)

    # 4. Render and Normalise All Scenes
    print(f"\n[4/5] Batch rendering scenes at 1080p and high bitrate conform...")
    section_clips = []
    for sec in SECTIONS_DATA:
        stem = sec["stem"]
        dur = durations[stem]
        raw_clip = render_scene(stem)
        dst_clip = SECTIONS_DIR / f"{stem}.mp4"
        print(f"  High-quality encoding to {dur:.2f}s (CRF 17) -> {dst_clip.name}")
        normalise_high_quality(raw_clip, dst_clip, seconds=dur)
        section_clips.append(dst_clip)

    # 5. Concatenate and Master
    print(f"\n[5/5] Final Video & Audio Muxing...")
    concat_list = BUILD_DIR / "clips_concat.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in section_clips]
    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    video_only = BUILD_DIR / "video_only.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(video_only)
    ], check=True)

    master_lufs = BUILD_DIR / "master_lufs.wav"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(master_wav),
        "-af", "loudnorm=I=-14:LRA=7:TP=-1.5",
        "-ar", "48000", "-ac", "2", str(master_lufs)
    ], check=True)

    final_mp4 = OUT_DIR / "final.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_only),
        "-i", str(master_lufs),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "320k",
        "-movflags", "+faststart",
        str(final_mp4)
    ], check=True)

    # Update showcase copy
    showcase_mp4 = ROOT / "media" / "showcase" / "videos" / "Kashmiri_MachineLearning_preview.mp4"
    import shutil
    shutil.copy2(str(final_mp4), str(showcase_mp4))

    v_dur = cfg.duration(final_mp4)
    file_mb = final_mp4.stat().st_size / (1024 * 1024)
    print("\n==========================================================")
    print(f"  SUCCESS! High-Fidelity Kashmiri Video Built:")
    print(f"  File:     {final_mp4}")
    print(f"  Duration: {v_dur:.2f}s ({v_dur/60:.2f} minutes)")
    print(f"  Size:     {file_mb:.2f} MB")
    print(f"  Audio:    Neural Voice (48 kHz, -14 LUFS)")
    print(f"  Video:    1080p Full HD (CRF 17 High-Bitrate)")
    print("==========================================================")
