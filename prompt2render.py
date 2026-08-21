#!/usr/bin/env python3
"""prompt2render — narrated, code-animated explainer videos, built to frame accuracy.

    python prompt2render.py new binary-search
    # write script.md in your own words (or `prompt2render draft binary-search`
    # for a first pass to rewrite), then:
    python prompt2render.py build binary-search

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

Run `python prompt2render.py doctor` first; it will tell you what is missing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt2render import cfg, project


def _load(slug: str):
    d = cfg.project_dir(slug)
    return d, project.parse_script(d / "script.md")


# ------------------------------------------------------------- scaffolding --

def cmd_new(a):
    if a.ai:
        from prompt2render import outline
        title = a.title or a.slug.replace("-", " ").title()
        secs = outline.generate(title, title, "undergraduate computer science",
                                minutes=a.minutes, sections=a.sections)
        d = project.new_project_from_sections(a.slug, title, secs, minutes=a.minutes)
    else:
        d = project.new_project(a.slug, a.title, minutes=a.minutes, sections=a.sections)
    print(f"\ncreated {d}\n\nNext: open {d/'script.md'} and write the narration.\n"
          "That script is the whole moat — it is the part no tool makes for you.\n")


def cmd_doctor(a):
    from prompt2render import doctor
    sys.exit(doctor.doctor())


def cmd_draft(a):
    from prompt2render import draft
    d = cfg.project_dir(a.slug)
    draft.draft(d, force=a.force)


def cmd_models(a):
    from prompt2render import asrmodel, voice
    if a.asr:
        asrmodel.fetch_asr(a.asr, force=a.force)
    if a.vad or a.asr:
        asrmodel.fetch_vad(force=a.force)
    if a.kokoro:
        voice.fetch_kokoro(force=a.force, int8=a.kokoro_int8)


def cmd_voices(a):
    from prompt2render import voice
    names = voice.voices()
    print(f"{len(names)} kokoro voices:\n")
    for i in range(0, len(names), 6):
        print("  " + "  ".join(n.ljust(12) for n in names[i:i + 6]))


def cmd_serve(a):
    import uvicorn
    uvicorn.run("prompt2render.web.app:app", host=a.host, port=a.port, reload=a.reload)


# ----------------------------------------------------------------- stages ---

def cmd_voice(a):
    from prompt2render import voice
    d, s = _load(a.slug)
    voice.build(d, s, voice.settings(a), only=a.only, force=a.force)


def cmd_align(a):
    from prompt2render import align
    d, s = _load(a.slug)
    align.align(d, s, only=a.only, force=a.force, use_asr=not a.no_asr,
                asr_jobs=a.asr_jobs)


def cmd_scenes(a):
    from prompt2render import scenes
    d, s = _load(a.slug)
    scenes.generate_all(d, s, index=a.section, retries=a.retries, jobs=a.jobs)


def _stills_jobs(d, script, section=None, force=False, check=False):
    """The sections that actually need rendering, as render_many() jobs."""
    from prompt2render import align, stills
    jobs = []
    for sec in script.sections:
        if section is not None and sec.index != section:
            continue
        scene = stills.scene_path(d, sec.stem)
        if not scene.exists():
            cfg.warn(f"section {sec.stem}: no scene module — run `prompt2render scenes`")
            continue
        outdir = stills.stills_dir(d, sec.stem)
        if not force and not check and stills.is_current(scene, outdir):
            # `prompt2render scenes` renders on acceptance now, so on a normal build
            # this is every section and the stage is a no-op.
            cfg.say(f"section {sec.stem}: stills current, skipping")
            continue
        n = len(align.load(d, sec.stem)["sentences"])
        jobs.append((sec.stem, scene, outdir, n - 1))
    return jobs


def cmd_stills(a):
    from prompt2render import stills
    d, s = _load(a.slug)
    jobs = _stills_jobs(d, s, section=a.section, force=a.force, check=a.check)
    got = stills.render_many(jobs, workers=a.jobs, check=a.check)
    if len(jobs) <= 1:
        for stem, n in got.items():
            cfg.say(f"section {stem}: {n} stills"
                    + (" (check only)" if a.check else ""))


def cmd_plan(a):
    from prompt2render import timeline
    d, s = _load(a.slug)
    timeline.build(d, s, motion=a.motion, lead_ms=a.lead_ms)


def cmd_encode(a):
    from prompt2render import encode
    d, _ = _load(a.slug)
    limit = None if a.all else a.limit
    jobs = a.jobs or cfg.env_int("P2R_ENCODE_JOBS", cfg.default_encode_jobs())
    left = encode.encode(d, limit=limit, preview=a.preview, jobs=jobs)
    sys.exit(0 if left == 0 else 7)          # 7 = more passes needed


def cmd_finish(a):
    from prompt2render import finish, publish
    d, s = _load(a.slug)
    finish.finish(d, s, burn=a.burn, style=a.style)
    print(f"\nwrote {publish.build_packet(d, s)}\n")


def cmd_check(a):
    from prompt2render import qc
    d, s = _load(a.slug)
    sys.exit(qc.check(d, s, strict=a.strict))


def cmd_build(a):
    """The whole chain. Every stage is cached, so re-running is cheap."""
    from prompt2render import align, encode, finish, publish, qc, scenes, stills, timeline, voice
    d, s = _load(a.slug)

    voice.build(d, s, voice.settings(a))
    align.align(d, s)
    scenes.generate_all(d, s, jobs=a.scene_jobs)
    # Usually a no-op: `prompt2render scenes` writes the stills for a section the moment
    # it accepts that section's module, so there is nothing left to draw.
    stills.render_many(_stills_jobs(d, s))
    timeline.build(d, s, motion=a.motion)
    jobs = a.jobs or cfg.env_int("P2R_ENCODE_JOBS", cfg.default_encode_jobs())
    if encode.encode(d, limit=None, jobs=jobs) != 0:
        sys.exit("[prompt2render] encode did not finish")
    finish.finish(d, s, burn=a.burn)
    publish.build_packet(d, s)
    sys.exit(qc.check(d, s, strict=a.strict))


# ---------------------------------------------------------- escape hatches --

def cmd_import(a):
    from prompt2render import visuals
    d, _ = _load(a.slug)
    visuals.import_sections(d, Path(a.src).expanduser().resolve())


def cmd_placeholders(a):
    from prompt2render import visuals
    d, s = _load(a.slug)
    for sec in s.sections:
        p = d / "sections" / f"{sec.stem}.mp4"
        # A truncated clip from an interrupted render is worse than no clip:
        # it exists, so it gets skipped, and then breaks concat much later.
        if not p.exists() or p.stat().st_size < 1024:
            cfg.say(f"placeholder for section {sec.stem}")
            visuals.stock_card(d, sec.index, sec.title)


def cmd_manim(a):
    from prompt2render import visuals
    d, s = _load(a.slug)
    visuals.manim_scene(d, s, Path(a.pyfile).expanduser().resolve(),
                        a.scene, a.index)


def cmd_assemble(a):
    from prompt2render import assemble as asm
    from prompt2render import publish
    d, s = _load(a.slug)
    asm.assemble(d, s, burn_captions=a.burn)
    publish.build_packet(d, s)


def cmd_publish(a):
    from prompt2render import publish, voice
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
        "[prompt2render] `animate` is retired.\n"
        "      The Code2Video path rendered at 480p15, could not run its own\n"
        "      layout critic on a Gemini key, and produced clips with no cue\n"
        "      structure — which is what forced the hold-last-frame sync hack.\n"
        "      Use `prompt2render scenes` instead. See docs/RETIRED.md.")


# -------------------------------------------------------------------- cli ---

def main() -> None:
    cfg.load_env()
    p = argparse.ArgumentParser(
        prog="prompt2render", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    n = add("new", cmd_new, "scaffold a new video project")
    n.add_argument("slug"); n.add_argument("--title")
    n.add_argument("--minutes", type=float,
                   help="target length; scales the number of body sections "
                        "(default 10 min = 6 sections, the old fixed template)")
    n.add_argument("--sections", type=int,
                   help="exact section count instead of deriving it from "
                        "--minutes")
    n.add_argument("--ai", action="store_true",
                   help="ask Gemini to propose section count/titles/ANIM "
                        "briefs for this specific topic, instead of the "
                        "fixed generic arc (needs GEMINI_API_KEY; narration "
                        "is still left as a placeholder either way)")

    dr = add("draft", cmd_draft, "ask Gemini to draft narration for script.md")
    dr.add_argument("slug")
    dr.add_argument("--force", action="store_true",
                    help="overwrite sections that already have real narration")

    add("doctor", cmd_doctor, "check the environment before you spend an hour")

    m = add("models", cmd_models, "download the models `voice`/`align` need")
    m.add_argument("--asr", default="base.en",
                   help="tiny.en | base.en | small.en")
    m.add_argument("--vad", action="store_true")
    m.add_argument("--kokoro", action="store_true",
                   help="the TTS voice weights (~350 MB, one time)")
    m.add_argument("--kokoro-int8", action="store_true", dest="kokoro_int8",
                   help="~92 MB instead of ~326 MB, small quality cost")
    m.add_argument("--force", action="store_true")

    add("voices", cmd_voices, "list the available kokoro voices")

    sv = add("serve", cmd_serve, "start the local web dashboard")
    sv.add_argument("--host", default="127.0.0.1",
                    help="127.0.0.1 is local-only (default) — 0.0.0.0 exposes "
                         "unauthenticated pipeline/Gemini triggers to your LAN")
    sv.add_argument("--port", type=int, default=8787)
    sv.add_argument("--reload", action="store_true")

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
    al.add_argument("--asr-jobs", type=int, default=None, dest="asr_jobs",
                    help="transcribe this many chunks of the programme at "
                         "once, split on section joins (default 1, or "
                         "$P2R_ASR_JOBS). The slowest local step in a build; "
                         "raising this trades a little cross-section context "
                         "for close to linear wall-clock")

    sc = add("scenes", cmd_scenes, "storyboard each section with the model")
    sc.add_argument("slug"); sc.add_argument("--section", type=int)
    sc.add_argument("--retries", type=int, default=3)
    sc.add_argument("--jobs", type=int, default=None,
                    help="storyboard this many sections concurrently "
                         "(default 3, or $P2R_SCENE_JOBS; lower it if the "
                         "free tier starts returning 429s)")

    st = add("stills", cmd_stills, "render the scene modules to PNG")
    st.add_argument("slug"); st.add_argument("--section", type=int)
    st.add_argument("--check", action="store_true", help="audit without writing")
    st.add_argument("--force", action="store_true",
                    help="re-render even where the stills are already current")
    st.add_argument("--jobs", type=int, default=None,
                    help="render this many sections concurrently "
                         "(default: one per core up to 4, or $P2R_STILLS_JOBS)")

    pl = add("plan", cmd_plan, "decide when every still appears")
    pl.add_argument("slug")
    pl.add_argument("--motion", choices=["none", "dissolve", "dissolve+reveal"])
    pl.add_argument("--lead-ms", type=int, dest="lead_ms")

    en = add("encode", cmd_encode, "render the clips (resumable)")
    en.add_argument("slug")
    en.add_argument("--limit", type=int, default=10)
    en.add_argument("--all", action="store_true")
    en.add_argument("--preview", action="store_true", help="fast nvenc pass")
    en.add_argument("--jobs", type=int, default=None,
                    help="encode this many clips concurrently (default 1, or "
                         "3 on NVENC; $P2R_ENCODE_JOBS overrides). Each clip "
                         "is its own ffmpeg process, so this can never change "
                         "the bitstream — time it and keep what is faster")

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
    bd.add_argument("--jobs", type=int, default=None,
                    help="parallel encode workers (default 1, or 3 on NVENC, "
                         "or $P2R_ENCODE_JOBS)")
    bd.add_argument("--scene-jobs", type=int, default=None, dest="scene_jobs",
                    help="parallel storyboard calls (default 3, "
                         "or $P2R_SCENE_JOBS)")

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
        sys.exit("\n[prompt2render] interrupted")


if __name__ == "__main__":
    main()
