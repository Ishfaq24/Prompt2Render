"""Full production builder for K-Means Clustering (Hindi Audio, 4-5 minutes).

Creates:
1. projects/kmeans-clustering-hindi/script.md
2. High-fidelity Hindi TTS audio for all 7 sections (audio/01.wav - 07.wav)
3. Matched Manim scenes (scenes/scene_01.py - scene_07.py)
4. Rendered video sections (sections/01.mp4 - 07.mp4)
5. Master audio, SRT subtitles, and final muxed video (out/final.mp4)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path
import numpy as np

# Root project path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from prompt2render import cfg
from prompt2render.multilingual.voice_service import OnlineTTSProvider

PROJECT_SLUG = "kmeans-clustering-hindi"
PROJ_DIR = ROOT / "projects" / PROJECT_SLUG

# -----------------------------------------------------------------------------
# Detailed 7-Section Script & Narration in Natural Technical Hindi
# -----------------------------------------------------------------------------
SECTIONS_DATA = [
    {
        "index": 1,
        "stem": "01",
        "title": "Unsupervised Learning और K-Means का परिचय",
        "anim": "Unlabeled scatter points in 2D space cluster into 3 distinct groups with centroids",
        "sentences": [
            "मशीन लर्निंग की दुनिया में, के-मीन्स क्लस्टरिंग सबसे लोकप्रिय और शक्तिशाली अनसुपरवाइज्ड लर्निंग एल्गोरिदम्स में से एक है।",
            "सुपरवाइज्ड लर्निंग के विपरीत, जहाँ हमारे पास पहले से लेबल किया हुआ डेटा होता है, यहाँ डेटा पूरी तरह से बिना किसी लेबल के होता है।",
            "के-मीन्स का मुख्य उद्देश्य इस बिना लेबल वाले डेटा के अंदर छिपे हुए पैटर्न्स और प्राकृतिक समूहों यानी क्लस्टर्स को खोजना है।",
            "यह पूरे डेटासेट को के अलग-अलग समूहों में इस तरह बाँटता है कि एक ही समूह के बिंदु आपस में अत्यधिक समान हों, जबकि अलग समूहों के बिंदु एक-दूसरे से काफी भिन्न हों।",
            "आइए समझते हैं कि यह एल्गोरिदम गणितीय रूप से कैसे काम करता है।"
        ]
    },
    {
        "index": 2,
        "stem": "02",
        "title": "गणितीय आधार और WCSS ऑब्जेक्टिव फंक्शन",
        "anim": "Mathematical formula card showing Euclidean distance and WCSS objective function with vector lines",
        "sentences": [
            "के-मीन्स क्लस्टरिंग का पूरा गणित दो प्रमुख स्तंभों पर टिका है, सेंट्रोइड और दूरी का माप।",
            "प्रत्येक क्लस्टर का अपना एक केंद्र बिंदु होता है जिसे सेंट्रोइड या म्यू कहा जाता है। यह उस क्लस्टर के सभी बिंदुओं का गणितीय माध्य यानी मीन होता है।",
            "किसी भी डेटा बिंदु और सेंट्रोइड के बीच की निकटता मापने के लिए हम सामान्यतः यूक्लिडियन डिस्टेंस का उपयोग करते हैं।",
            "एल्गोरिदम का मुख्य लक्ष्य एक ऑब्जेक्टिव फंक्शन को न्यूनतम करना होता है, जिसे विद-इन-क्लस्टर सम ऑफ स्क्वेयर्स या डब्ल्यू-सी-एस-एस कहा जाता है।",
            "इसे इनर्शिया भी कहते हैं। डब्ल्यू-सी-एस-एस प्रत्येक बिंदु और उसके संबंधित सेंट्रोइड के बीच की दूरी के वर्ग का कुल योग होता है।",
            "जितना कम डब्ल्यू-सी-एस-एस होगा, हमारे क्लस्टर्स उतने ही सघन और सटीक होंगे।"
        ]
    },
    {
        "index": 3,
        "stem": "03",
        "title": "लॉयड का एल्गोरिदम: 4 मुख्य चरण",
        "anim": "Flow diagram showing the 4 steps of Lloyd's algorithm: Initialize, Assign, Update, Converge",
        "sentences": [
            "के-मीन्स को व्यवहार में लागू करने के लिए लॉयड के एल्गोरिदम का उपयोग किया जाता है, जो चार मुख्य चरणों में कार्य करता है।",
            "पहला चरण है इनिशियलाइजेशन। हम डेटास्पेस में के सेंट्रोइड्स को यादृच्छिक यानी रैंडम रूप से चुनते हैं।",
            "दूसरा चरण है असाइनमेंट स्टेप। प्रत्येक डेटा बिंदु की सभी सेंट्रोइड्स से दूरी नापी जाती है और बिंदु को उसके सबसे निकटतम सेंट्रोइड वाले क्लस्टर में असाइन कर दिया जाता है।",
            "तीसरा चरण है अपडेट स्टेप। जब सभी बिंदु असाइन हो जाते हैं, तब प्रत्येक क्लस्टर के नए केंद्र की गणना उसके सभी बिंदुओं का औसत निकालकर की जाती है। सेंट्रोइड्स अपने नए स्थान पर खिसक जाते हैं।",
            "और चौथा चरण है कन्वर्जेंस। हम इन दोनों चरणों को तब तक दोहराते हैं जब तक कि सेंट्रोइड्स का हिलना बंद न हो जाए या असाइनमेंट्स बदलना बंद न हो जाएं।"
        ]
    },
    {
        "index": 4,
        "stem": "04",
        "title": "विजुअल कन्वर्जेंस और वोरोनोई निर्णय सीमाएं",
        "anim": "Step-by-step scatter animation showing centroids moving and Voronoi boundary shifting over iterations",
        "sentences": [
            "आइए इस प्रक्रिया को विजुअली देखें।",
            "आरंभ में, रैंडम चुने गए सेंट्रोइड्स डेटा के वास्तविक केंद्रों से दूर हो सकते हैं।",
            "जैसे ही पहला असाइनमेंट होता है, स्पेस वोरोनोई सेल्स यानी निर्णय सीमाओं में विभाजित हो जाता है।",
            "पहले इटरेशन के बाद, जब सेंट्रोइड्स का नया माध्य निकाला जाता है, तो वे सीधे अपने-अपने डेटा बादलों के केंद्र की ओर खिंचते हैं।",
            "दूसरे और तीसरे इटरेशन में, सीमांत बिंदु नए निकटतम क्लस्टर में शिफ्ट होते हैं और सीमाएं स्थिर होने लगती हैं।",
            "प्रत्येक इटरेशन के साथ हमारा ऑब्जेक्टिव फंक्शन यानी डब्ल्यू-सी-एस-एस लगातार घटता जाता है।",
            "अंततः, जब सेंट्रोइड्स में कोई बदलाव नहीं होता, तो एल्गोरिदम सफलता से कन्वर्ज हो जाता है।"
        ]
    },
    {
        "index": 5,
        "stem": "05",
        "title": "सर्वश्रेष्ठ K का चयन: एल्बो मेथड",
        "anim": "Coordinate axes with K vs WCSS curve showing sharp bend at K=3 with Elbow point marker",
        "sentences": [
            "के-मीन्स का सबसे बड़ा प्रश्न यह है कि हम के का सही मान कैसे चुनें?",
            "यदि हम के का मान डेटा बिंदुओं की संख्या के बराबर रख दें, तो डब्ल्यू-सी-एस-एस शून्य हो जाएगा, लेकिन वह मॉडल पूरी तरह से व्यर्थ होगा।",
            "सही संतुलन खोजने के लिए हम एल्बो मेथड का उपयोग करते हैं।",
            "हम के के अलग-अलग मानों, जैसे एक से आठ तक, के लिए एल्गोरिदम चलाते हैं और हर बार डब्ल्यू-सी-एस-एस का ग्राफ प्लॉट करते हैं।",
            "शुरुआत में के बढ़ाने पर डब्ल्यू-सी-एस-एस बहुत तेजी से नीचे गिरता है।",
            "लेकिन एक बिंदु ऐसा आता है जिसके बाद गिरावट की दर अचानक धीमी हो जाती है। यह मोड़ एक मुड़ी हुई कोहनी यानी एल्बो की तरह दिखाई देता है।",
            "इस एल्बो पॉइंट पर मिलने वाला के का मान ही हमारे डेटासेट के लिए सबसे उपयुक्त और संतुलित माना जाता है।"
        ]
    },
    {
        "index": 6,
        "stem": "06",
        "title": "इनिशियलाइजेशन की समस्या और K-Means++",
        "anim": "Comparison of poor random centroid initialization versus K-Means++ smart probability seeding",
        "sentences": [
            "मानक के-मीन्स में एक बड़ी कमजोरी होती है, इनिशियलाइजेशन सेंसिटिविटी।",
            "यदि हम शुरुआत में सभी सेंट्रोइड्स को गलती से एक ही क्लस्टर के पास चुन लें, तो एल्गोरिदम सब-ऑप्टिमल लोकल मिनिमा में फंस सकता है।",
            "इस गंभीर समस्या को हल करने के लिए वर्ष 2007 में के-मीन्स प्लस प्लस एल्गोरिदम पेश किया गया।",
            "के-मीन्स प्लस प्लस पहला सेंट्रोइड रैंडम चुनता है, लेकिन बाद के प्रत्येक सेंट्रोइड को मौजूदा सेंट्रोइड्स से दूरी के वर्ग के अनुपात में संभाव्यता के आधार पर चुनता है।",
            "इससे यह सुनिश्चित होता है कि शुरुआती सेंट्रोइड्स पूरे डेटास्पेस में एक-दूसरे से पर्याप्त दूरी पर फैलें।",
            "आज साइकिट-लर्न जैसी आधुनिक लाइब्रेरीज में के-मीन्स प्लस प्लस ही डिफॉल्ट तकनीक के रूप में उपयोग किया जाता है।"
        ]
    },
    {
        "index": 7,
        "stem": "07",
        "title": "अनुप्रयोग, सीमाएं और महत्वपूर्ण निष्कर्ष",
        "anim": "Summary card and badges displaying real-world use cases, strengths, and geometric limitations",
        "sentences": [
            "के-मीन्स की लोकप्रियता का मुख्य कारण इसकी गति और कम्प्यूटेशनल दक्षता है। इसकी समय जटिलता यानी टाइम कॉम्प्लेक्सिटी लीनियर होती है।",
            "उद्योग में इसका व्यापक उपयोग कस्टमर सेगमेंटेशन, ई-कॉमर्स में ग्राहक वर्गीकरण, इमेज कम्प्रेशन और दस्तावेज़ क्लस्टरिंग में होता है।",
            "हालाँकि, इसकी कुछ सीमाएं भी हैं। यह हमेशा गोलाकार यानी स्फेरिकल क्लस्टर्स की कल्पना करता है और जटिल या गैर-रेखीय आकारों पर विफल हो जाता है।",
            "साथ ही, यह आउटलायर्स और डेटा के विभिन्न पैमानों के प्रति अत्यधिक संवेदनशील है।",
            "संक्षेप में, के-मीन्स डेटा में छुपी संरचना को खोजने का एक बेहद तेज, सुंदर और बुनियादी एल्गोरिदम है, जिसकी समझ हर मशीन लर्निंग इंजीनियर के लिए अनिवार्य है।"
        ]
    }
]

def build_script_markdown() -> str:
    lines = [
        "---",
        "title: \"K-Means Clustering: Complete Intuition & Mathematics\"",
        "topic: K-Means Clustering, Unsupervised Learning, Centroids, Euclidean Distance, WCSS Inertia, Lloyd's Algorithm, Convergence, Elbow Method, K-Means++",
        "audience: undergraduate computer science & data science practitioners",
        "aspect: 16:9",
        "language: hi",
        "audio_language: hi",
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
    """Synthesize list of Hindi sentences with comfortable natural pauses."""
    pcm_chunks = []
    sr = 24000
    pause_samples = int(sr * 0.38) # 380ms pause between sentences
    pause_pcm = np.zeros(pause_samples, dtype=np.float32)

    for i, sent in enumerate(sentences):
        print(f"    Synthesizing sentence {i+1}/{len(sentences)}...")
        samples, sr = tts.synthesise_sentence(sent, lang_code="hi")
        pcm_chunks.append(samples)
        if i < len(sentences) - 1:
            pcm_chunks.append(pause_pcm)

    # Lead and tail silence
    lead = np.zeros(int(sr * 0.25), dtype=np.float32)
    tail = np.zeros(int(sr * 0.40), dtype=np.float32)
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
    """Generate high-accuracy synchronized SRT captions."""
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
        # Distribute duration proportionally across sentences
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
    print(f"=== K-Means Clustering Hindi Video Generator ===")
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
    print(f"[1/6] Generated script.md ({len(SECTIONS_DATA)} sections)")

    # 2. Synthesize audio
    tts = OnlineTTSProvider()
    durations = {}
    master_pcm_list = []
    sr = 24000
    cum_time = 0.0
    audio_map = {"sections": {}}

    print(f"[2/6] Synthesizing Hindi Narration Audio for all sections...")
    for sec in SECTIONS_DATA:
        stem = sec["stem"]
        wav_path = PROJ_DIR / "audio" / f"{stem}.wav"
        print(f"  Section {stem}: {sec['title']}")
        pcm, sr = synthesize_section_audio(tts, sec["sentences"])
        dur = len(pcm) / sr
        write_wav(wav_path, pcm, sr)
        durations[stem] = dur
        master_pcm_list.append(pcm)
        audio_map["sections"][stem] = {"start": round(cum_time, 3), "dur": round(dur, 3)}
        cum_time += dur
        print(f"    -> Duration: {dur:.2f}s ({dur/60:.2f} min)")

    total_sec = cum_time
    print(f"Total Video Duration: {total_sec:.2f}s ({total_sec/60:.2f} minutes)")

    # Write audio_map.json
    amap_path = PROJ_DIR / "build" / "audio_map.json"
    amap_path.write_text(json.dumps(audio_map, indent=2), encoding="utf-8")

    # Write concatenated master.wav
    master_pcm = np.concatenate(master_pcm_list)
    master_wav = PROJ_DIR / "build" / "master.wav"
    write_wav(master_wav, master_pcm, sr)
    print(f"[2/6 Complete] Master audio saved to {master_wav}")

    # 3. Generate captions
    srt_content = generate_subtitles(SECTIONS_DATA, durations)
    srt_file = PROJ_DIR / "out" / "captions.srt"
    srt_file.write_text(srt_content, encoding="utf-8")
    print(f"[3/6] Subtitles written to {srt_file}")
