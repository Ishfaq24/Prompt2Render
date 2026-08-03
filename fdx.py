#!/usr/bin/env python3
"""fdx — narrated, code-animated explainer videos, built to frame accuracy.

    python fdx.py new binary-search
    # write script.md in your own words, then:
    python fdx.py build binary-search

`build` runs the whole chain. The stages exist separately because each one is
worth inspecting, and because the expensive ones are cached:

    voice    synthesise sentence by sentence, master the programme once
    align    force-align the rendered audio; word-level timings
    scenes   ask the model to storyboard each section against scenekit
    stills   execute those modules, with the layout audit as a gate
    plan     decide when every still appears, to the frame
    encode   one clip per still, with the dissolve at its head
    finish   concat, mux, chapter, caption
    check    the gates that say whether it is shippable

Run `python fdx.py doctor` first; it will tell you what is missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fdx import cfg, project


def _load(slug: str):
    d = cfg.project_dir(slug)
    return d, project.parse_script(d / "script.md")


# ------------------------------------------------------------- scaffolding --

def cmd_new(a):
    d = project.new_project(a.slug, a.title)
    print(f"\ncreated {d}\n\nNext: open {d/'script.md'} and write the narration.\n"
          "That script is the whole moat — it is the part no tool makes for you.\n")


def cmd_doctor(a):
    from fdx import doctor
    sys.exit(doctor.doctor())


def cmd_models(a):
    from fdx import asrmodel
    if a.asr:
        asrmodel.fetch_asr(a.asr, force=a.force)
    if a.vad or a.asr:
        asrmodel.fetch_vad(force=a.force)


def cmd_voices(a):
    from fdx import voice
    names = voice.voices()
    print(f"{len(names)} kokoro voices:\n")
    for i in range(0, len(names), 6):
        print("  " + "  ".join(n.ljust(12) for n in names[i:i + 6]))


# ----------------------------------------------------------------- stages ---

def cmd_voice(a):
    from fdx import voice
    d, s = _load(a.slug)
    voice.build(d, s, voice.settings(a), only=a.only, force=a.force)


def cmd_align(a):
    from fdx import align
    d, s = _load(a.slug)
    align.align(d, s, only=a.only, force=a.force, use_asr=not a.no_asr)


def cmd_scenes(a):
    from fdx import scenes
    d, s = _load(a.slug)
    scenes.generate_all(d, s, index=a.section, retries=a.retries)


def cmd_stills(a):
    from fdx import align, stills
    d, s = _load(a.slug)
    for sec in s.sections:
        if a.section is not None and sec.index != a.section:
            continue
        scene = stills.scene_path(d, sec.stem)
        if not scene.exists():
            cfg.warn(f"section {sec.stem}: no scene module — run `fdx scenes`")
            continue
        n = len(align.load(d, sec.stem)["sentences"])
        man = stills.render(scene, stills.stills_dir(d, sec.stem),
                            max_cue=n - 1, check=a.check)
        cfg.say(f"section {sec.stem}: {len(man)} stills"
                + (" (check only)" if a.check else ""))


def cmd_plan(a):
    from fdx import timeline
    d, s = _load(a.slug)
    timeline.build(d, s, motion=a.motion, lead_ms=a.lead_ms)


def cmd_encode(a):
    from fdx import encode
    d, _ = _load(a.slug)
    limit = None if a.all else a.limit
    left = encode.encode(d, limit=limit, preview=a.preview)
    sys.exit(0 if left == 0 else 7)          # 7 = more passes needed


def cmd_finish(a):
    from fdx import finish, publish
    d, s = _load(a.slug)
    finish.finish(d, s, burn=a.burn, style=a.style)
    print(f"\nwrote {publish.build_packet(d, s)}\n")


def cmd_check(a):
    from fdx import qc
    d, s = _load(a.slug)
    sys.exit(qc.check(d, s, strict=a.strict))


def cmd_build(a):
    """The whole chain. Every stage is cached, so re-running is cheap."""
    from fdx import align, encode, finish, publish, qc, scenes, stills, timeline, voice
    d, s = _load(a.slug)

    voice.build(d, s, voice.settings(a))
    align.align(d, s)
    scenes.generate_all(d, s)
    for sec in s.sections:
        n = len(align.load(d, sec.stem)["sentences"])
        stills.render(stills.scene_path(d, sec.stem),
                      stills.stills_dir(d, sec.stem), max_cue=n - 1)
    timeline.build(d, s, motion=a.motion)
    if encode.encode(d, limit=None) != 0:
        sys.exit("[fdx] encode did not finish")
    finish.finish(d, s, burn=a.burn)
    publish.build_packet(d, s)
    sys.exit(qc.check(d, s, strict=a.strict))


# ---------------------------------------------------------- escape hatches --

def cmd_import(a):
    from fdx import visuals
    d, _ = _load(a.slug)
    visuals.import_sections(d, Path(a.src).expanduser().resolve())


def cmd_placeholders(a):
    from fdx import visuals
    d, s = _load(a.slug)
    for sec in s.sections:
        p = d / "sections" / f"{sec.stem}.mp4"
        # A truncated clip from an interrupted render is worse than no clip:
        # it exists, so it gets skipped, and then breaks concat much later.
        if not p.exists() or p.stat().st_size < 1024:
            cfg.say(f"placeholder for section {sec.stem}")
            visuals.stock_card(d, sec.index, sec.title)


def cmd_manim(a):
    from fdx import visuals
    d, s = _load(a.slug)
    visuals.manim_scene(d, s, Path(a.pyfile).expanduser().resolve(),
                        a.scene, a.index)


def cmd_assemble(a):
    from fdx import assemble as asm
    from fdx import publish
    d, s = _load(a.slug)
    asm.assemble(d, s, burn_captions=a.burn)
    publish.build_packet(d, s)


def cmd_publish(a):
    from fdx import publish, voice
    d, s = _load(a.slug)
    try:
        amap = voice.audio_map(d)
        for sec in s.sections:
            o = amap["sections"][sec.stem]
            sec.start, sec.dur = o["start"], o["dur"]
    except SystemExit:
        cfg.warn("no audio map — chapter times will be zero")
    print(f"\nwrote {publish.build_packet(d, s)}\n")


def cmd_animate(a):
    sys.exit(
        "[fdx] `animate` is retired.\n"
        "      The Code2Video path rendered at 480p15, could not run its own\n"
        "      layout critic on a Gemini key, and produced clips with no cue\n"
        "      structure — which is what forced the hold-last-frame sync hack.\n"
        "      Use `fdx scenes` instead. See docs/RETIRED.md.")


# -------------------------------------------------------------------- cli ---

def main() -> None:
    cfg.load_env()
    p = argparse.ArgumentParser(
        prog="fdx", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    n = add("new", cmd_new, "scaffold a new video project")
    n.add_argument("slug"); n.add_argument("--title")

    add("doctor", cmd_doctor, "check the environment before you spend an hour")

    m = add("models", cmd_models, "download the ASR models used by `align`")
    m.add_argument("--asr", default="base.en",
                   help="tiny.en | base.en | small.en")
    m.add_argument("--vad", action="store_true")
    m.add_argument("--force", action="store_true")

    add("voices", cmd_voices, "list the available kokoro voices")

    # --- stages -------------------------------------------------------------
    v = add("voice", cmd_voice, "synthesise and master the narration")
    v.add_argument("slug")
    v.add_argument("--backend", choices=["kokoro", "edge", "own"])
    v.add_argument("--voice"); v.add_argument("--speed", type=float)
    v.add_argument("--lufs", type=float)
    v.add_argument("--audio-profile", choices=["tts", "voice"], dest="audio_profile")
    v.add_argument("--pause-sentence", type=int, dest="pause_sentence")
    v.add_argument("--pause-paragraph", type=int, dest="pause_paragraph")
    v.add_argument("--only", help="section stem, e.g. 03")
    v.add_argument("--force", action="store_true")

    al = add("align", cmd_align, "force-align the narration to word level")
    al.add_argument("slug"); al.add_argument("--only")
    al.add_argument("--force", action="store_true")
    al.add_argument("--no-asr", action="store_true", dest="no_asr",
                    help="skip whisper; use the exact synthesis timings only")

    sc = add("scenes", cmd_scenes, "storyboard each section with the model")
    sc.add_argument("slug"); sc.add_argument("--section", type=int)
    sc.add_argument("--retries", type=int, default=3)

    st = add("stills", cmd_stills, "render the scene modules to PNG")
    st.add_argument("slug"); st.add_argument("--section", type=int)
    st.add_argument("--check", action="store_true", help="audit without writing")

    pl = add("plan", cmd_plan, "decide when every still appears")
    pl.add_argument("slug")
    pl.add_argument("--motion", choices=["none", "dissolve", "dissolve+reveal"])
    pl.add_argument("--lead-ms", type=int, dest="lead_ms")

    en = add("encode", cmd_encode, "render the clips (resumable)")
    en.add_argument("slug")
    en.add_argument("--limit", type=int, default=10)
    en.add_argument("--all", action="store_true")
    en.add_argument("--preview", action="store_true", help="fast nvenc pass")

    fi = add("finish", cmd_finish, "concat, mux, caption, chapter")
    fi.add_argument("slug"); fi.add_argument("--burn", action="store_true")
    fi.add_argument("--style", choices=["srt", "ass"], default="srt")

    ck = add("check", cmd_check, "run the quality gates")
    ck.add_argument("slug"); ck.add_argument("--strict", action="store_true")

    bd = add("build", cmd_build, "voice -> align -> scenes -> ... -> check")
    bd.add_argument("slug")
    bd.add_argument("--motion", choices=["none", "dissolve", "dissolve+reveal"])
    bd.add_argument("--speed", type=float); bd.add_argument("--voice")
    bd.add_argument("--lufs", type=float)
    bd.add_argument("--burn", action="store_true")
    bd.add_argument("--strict", action="store_true")

    # --- escape hatches -----------------------------------------------------
    im = add("import", cmd_import, "import section clips from a folder")
    im.add_argument("slug"); im.add_argument("src")

    ph = add("placeholders", cmd_placeholders, "title cards for missing sections")
    ph.add_argument("slug")

    mn = add("manim", cmd_manim, "render one hand-authored Manim scene")
    mn.add_argument("slug"); mn.add_argument("pyfile"); mn.add_argument("scene")
    mn.add_argument("index", type=int)

    ab = add("assemble", cmd_assemble, "legacy sync path, for imported clips")
    ab.add_argument("slug"); ab.add_argument("--burn", action="store_true")

    pb = add("publish", cmd_publish, "write the upload packet")
    pb.add_argument("slug")

    an = add("animate", cmd_animate, "(retired — use `scenes`)")
    an.add_argument("slug", nargs="?")

    a = p.parse_args()
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit("\n[fdx] interrupted")


if __name__ == "__main__":
    main()
