#!/usr/bin/env python3
"""prompt2render — narrated, code-animated explainer videos, built to frame accuracy.

    python prompt2render.py new binary-search
    # write script.md in your own words (or `prompt2render draft binary-search`
    # for a first pass to rewrite), then:
    python prompt2render.py build binary-search

    # or, unattended, topic to checked video in one call (see `auto --help`
    # for the trade-off: no human reads the narration before it ships):
    python prompt2render.py auto binary-search

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
        seed = a.title or a.slug.replace("-", " ").title()
        out = outline.generate(seed, seed, "undergraduate computer science",
                               minutes=a.minutes, sections=a.sections,
                               fixed_title=bool(a.title))
        title = a.title or out["title"]
        d = project.new_project_from_sections(a.slug, title, out["sections"],
                                              minutes=a.minutes, topic=out["topic"])
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
    if a.vad:
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


def _run_pipeline(d, s, a) -> int:
    """voice -> align -> scenes -> stills -> plan -> encode -> finish -> publish -> check.

    Shared by `build` (script.md already written) and `auto` (script.md was
    just outlined/drafted by AI). Returns the QC exit code rather than
    calling sys.exit() itself, so callers can decide what to do with it.
    """
    from prompt2render import align, encode, finish, publish, qc, scenes, stills, timeline, voice
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
    return qc.check(d, s, strict=a.strict)


def cmd_build(a):
    """The whole chain. Every stage is cached, so re-running is cheap."""
    if getattr(a, "manim", False) and not getattr(a, "harness", False):
        sys.exit(
            "[prompt2render] --manim requires the harness path; "
            "use `build SLUG --harness --manim`"
        )
    if getattr(a, "harness", False):
        # Route through the harness instead of the raw pipeline
        cmd_harness(a)
    else:
        d, s = _load(a.slug)
        sys.exit(_run_pipeline(d, s, a))

def cmd_harness(a):
    """Run the harness pipeline explicitly."""
    from prompt2render.harness.context import SceneContext
    from prompt2render.harness.events import EventBus
    from prompt2render.harness.loader import build_plugins, build_repair_router
    from prompt2render.harness.logging_ import StructuredLogger
    from prompt2render.harness.runner import GateFailure, HarnessRunner
    
    d, s = _load(a.slug)
    script_path = d / "script.md"
    
    # The harness now wraps voice and align natively via GeneratorVoicePlugin
    # and GeneratorAlignPlugin.
    config_path = Path(a.config) if getattr(a, "config", None) else None
    
    from prompt2render.harness.loader import load_config
    cfg_dict = load_config(config_path)
    
    # Forward CLI arguments into the plugin config so the harness wrappers
    # can respect them just like the raw pipeline did.
    if "planner_script" not in cfg_dict:
        cfg_dict["planner_script"] = {}
    cfg_dict["planner_script"]["force"] = getattr(a, "redraft", False)

    if "generator_voice" not in cfg_dict:
        cfg_dict["generator_voice"] = {}
    cfg_dict["generator_voice"]["kokoro_voice"] = getattr(a, "voice", None) or "am_eric"
    cfg_dict["generator_voice"]["kokoro_speed"] = getattr(a, "speed", None) or 1.0
    cfg_dict["generator_voice"]["lufs"] = getattr(a, "lufs", None) or cfg.LUFS
    
    if "renderer_encode" not in cfg_dict:
        cfg_dict["renderer_encode"] = {}
    cfg_dict["renderer_encode"]["jobs"] = getattr(a, "jobs", None)
    
    if "renderer_finish" not in cfg_dict:
        cfg_dict["renderer_finish"] = {}
    cfg_dict["renderer_finish"]["burn"] = getattr(a, "burn", False)

    # A stale config from an earlier experimental run must not inject Manim
    # into ordinary --harness builds. Only an explicit --manim opts in.
    if not getattr(a, "manim", False):
        cfg_dict.setdefault("renderer_manim", {})["enabled"] = False
    else:
        # Manim produces opaque section clips, not still manifests.
        # Disable the still renderer before build_plugins() resolves the DAG;
        # otherwise both renderer_stills and renderer_manim claim the shared
        # render_artifacts field and the loader correctly rejects the graph.
        cfg_dict.setdefault("renderer_stills", {})["enabled"] = False
        cfg_dict.setdefault("renderer_manim", {})["enabled"] = True
        cfg_dict.setdefault("generator_timeline", {})["enabled"] = False
        cfg_dict.setdefault("renderer_encode", {})["enabled"] = False
        cfg_dict.setdefault("renderer_finish", {})["enabled"] = False
        cfg_dict.setdefault("generator_publish", {})["enabled"] = False
        # We also disable verifier_audio because it expects out/final.mp4 which won't exist yet
        # (assemble runs *after* the harness).
        cfg_dict.setdefault("verifier_audio", {})["enabled"] = False
        cfg_dict.setdefault("verifier_final_qc", {})["enabled"] = False
    
    plugins = build_plugins(config=cfg_dict)
    
    # Hot-swap plugins if --manim is requested
    if getattr(a, "manim", False):
        from prompt2render.harness.plugins.renderer_manim import GeneratorManimPlugin, RendererManimPlugin
        # Replace generator_code with generator_manim. Pass its config.yaml
        # block through (e.g. use_motion_compiler) -- a bare GeneratorManimPlugin()
        # would silently ignore any config for it.
        plugins = [
            GeneratorManimPlugin(cfg_dict.get("generator_manim", {})) if p.name == "generator_code" else p
            for p in plugins
        ]
        # Keep an already-enabled renderer_manim, or replace renderer_stills
        # when an older configuration supplied only the still renderer.
        new_plugins = []
        manim_renderer_seen = False
        for p in plugins:
            if p.name == "renderer_stills":
                if not manim_renderer_seen:
                    new_plugins.append(
                        RendererManimPlugin({"enabled": True, "gate_override": True})
                    )
                    manim_renderer_seen = True
            elif p.name == "renderer_manim":
                new_plugins.append(p)
                manim_renderer_seen = True
            else:
                new_plugins.append(p)

        if not manim_renderer_seen:
            new_plugins.append(
                RendererManimPlugin({"enabled": True, "gate_override": True})
            )
                
        # Ensure verifier_temporal is enabled in Manim mode and runs after the renderer
        if not any(p.name == "verifier_temporal" for p in new_plugins):
            from prompt2render.harness.plugins.verifier_temporal import VerifierTemporalPlugin
            # Insert right after renderer_manim
            idx = next((i for i, p in enumerate(new_plugins) if p.name == "renderer_manim"), len(new_plugins))
            new_plugins.insert(idx + 1, VerifierTemporalPlugin({"enabled": True, "gate_override": True}))
        # Manim produces section-level MP4 clips, not scenekit still manifests.
        # Never allow still-based timeline/encode/finish plugins into this graph,
        # even if a stale config file enabled them.
        incompatible = {
            "generator_timeline", "renderer_encode", "renderer_finish",
            "verifier_audio", "verifier_final_qc", "generator_publish",
        }
        plugins = [p for p in new_plugins if p.name not in incompatible]
        cfg.say("harness: running in experimental --manim mode")
    repair_router = build_repair_router(config=cfg_dict)
    
    log_path = d / "build" / "harness" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = StructuredLogger(log_path)
    bus = EventBus()
    
    if repair_router is not None:
        repair_router.attach(
            bus=bus,
            plugins_by_name={p.name: p for p in plugins},
            log_path=d / "build" / "harness" / "repair_log.jsonl",
        )
        
    # Attach live progress UI if running in a TTY
    progress = None
    import sys
    if sys.stdout.isatty():
        from prompt2render.harness.progress import HarnessProgressUI
        progress = HarnessProgressUI(total_stages=len(plugins))
        progress.attach(bus)
        
    ctx = SceneContext(prompt=script_path, project_dir=d)
    runner = HarnessRunner(plugins, logger, bus)
    
    cfg.say(f"running harness over {a.slug}: " + " -> ".join(p.name for p in plugins))
    try:
        ctx = runner.run(ctx)
    except GateFailure as e:
        if progress:
            progress.stop()
        sys.exit(f"[prompt2render] harness hard gate failed: {e}")
    finally:
        if progress:
            progress.stop()
        
    # The default harness now runs timeline -> encode -> finish -> final QC ->
    # publish natively. Do not run qc.check a second time; it would repeat the
    # expensive independent caption-drift transcription. The final-QC plugin
    # has already recorded the authoritative result in the harness log.
    if getattr(a, "manim", False):
        # --- Hard assembly gate: no stale assembly after HITL regeneration ---
        # Blocking conditions (any one aborts assembly):
        #  1. Any BLOCKING fail in any check_results (including non-gate plugins
        #     that emitted BLOCKING for the repaired stems).
        #  2. Non-empty repair_context — a regenerated stem has not yet been
        #     re-rendered and re-verified through execution + temporal + semantic.
        #  3. Stale or missing clip for any repaired/HITL stem (render artifact
        #     absent or older than its code artifact).
        #  4. Missing PASS from execution/temporal/semantic for a repaired stem
        #     (a verifier that only emitted "skip" is not proof of correctness).
        import json as _json
        blocking: list[str] = []
        for plugin_name, findings in ctx.check_results.items():
            for f in (findings or []):
                if not isinstance(f, dict):
                    continue
                if str(f.get("status", "")).lower() == "fail" and str(f.get("severity", "")) == "BLOCKING":
                    stem = f.get("stem") or f.get("scene_id") or "?"
                    blocking.append(f"{plugin_name}:{stem}:{f.get('finding_type','?')}:{f.get('detail') or f.get('message','')[:120]}")
        if blocking:
            sys.exit("[prompt2render] aborting assembly: unresolved BLOCKING findings:\n  " + "\n  ".join(blocking))

        # HITL rejects still on disk are authoritative even if the in-memory
        # repair_context was deduplicated this pass.  While any reject
        # remains, assembly must not run — the user explicitly asked for
        # regeneration of those sections (same hitl.json → generate again).
        hitl_rejects: set[str] = set()
        hitl_file = d / "hitl_feedback.json"
        if hitl_file.exists():
            try:
                data = _json.loads(hitl_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict) and v.get("status") == "reject":
                            hitl_rejects.add(str(k))
            except Exception:
                pass
        if hitl_rejects:
            # Do NOT allow assembly while HITL still lists rejects, even if
            # clips look fresh and verifiers pass — the fresh render is the
            # *result* of the reject, but the reject itself must be cleared
            # by the user to signal acceptance.  This prevents the stale-
            # assembly bug where 01/07 were regenerated but immediately
            # assembled without a blocking gate.
            sys.exit(
                "[prompt2render] aborting assembly: HITL rejects remain for "
                f"{sorted(hitl_rejects)} in {hitl_file}. "
                "Regenerated sections have fresh clips but assembly is blocked "
                "until you remove those entries from hitl_feedback.json or set "
                'them to {"status":"accept"}.'
            )

        pending_stems: set[str] = set(ctx.repair_context.keys()) | hitl_rejects

        # Stems that were repaired but whose render artifact is stale/missing
        # must block assembly — otherwise sections/01.mp4 would still be the
        # old clip padded to the narration length.
        stale: list[str] = []
        missing_pass: list[str] = []
        for stem in sorted(pending_stems):
            art = ctx.code_artifacts.get(stem)
            rend = ctx.render_artifacts.get(stem)
            # A pending stem must have a fresh render artifact with a non-empty manifest
            if not rend or not getattr(rend, "manifest", None):
                stale.append(f"{stem}: missing render artifact (regenerated code has not been re-rendered)")
                continue
            # Prefer clip manifest entry, fall back to sections/XX.mp4 mtime
            try:
                code_mtime = art.path.stat().st_mtime if art and art.path and art.path.exists() else 0
            except Exception:
                code_mtime = 0
            clip_path = None
            try:
                # renderer_manim stores sections/XX.mp4 in manifest[0].mp4
                if rend.manifest and isinstance(rend.manifest[0], dict):
                    cand = rend.manifest[0].get("mp4")
                    if cand:
                        from pathlib import Path as _P
                        cand_p = _P(cand)
                        if cand_p.exists():
                            clip_path = cand_p
                if clip_path is None:
                    # Fallback to on-disk section clip
                    cand2 = d / "sections" / f"{stem}.mp4"
                    if cand2.exists():
                        clip_path = cand2
                    else:
                        cand3 = d / "build" / "manim" / "videos" / f"scene_{stem}" / "1080p30" / f"Scene{stem}.mp4"
                        if cand3.exists():
                            clip_path = cand3
            except Exception:
                clip_path = None
            if clip_path is None or not clip_path.exists():
                stale.append(f"{stem}: clip file missing on disk")
                continue
            try:
                clip_mtime = clip_path.stat().st_mtime
            except Exception:
                clip_mtime = 0
            # Allow 1s clock granularity; fresh clip must be >= code mtime
            if code_mtime and clip_mtime + 0.5 < code_mtime:
                stale.append(f"{stem}: stale clip (clip {clip_mtime:.0f} < code {code_mtime:.0f} at {clip_path})")
                continue
            if clip_path.stat().st_size < 1024:
                stale.append(f"{stem}: clip truncated (<1k) at {clip_path}")
                continue

            # Execution / temporal / semantic must have an explicit PASS for this stem,
            # not merely an absent failure (skip is not a pass).
            for verifier in ("verifier_execution", "verifier_temporal", "verifier_semantic"):
                results = ctx.check_results.get(verifier, [])
                stem_results = [r for r in results if isinstance(r, dict) and str(r.get("stem") or r.get("scene_id") or "") == str(stem)]
                has_pass = any(str(r.get("status", "")).lower() == "pass" for r in stem_results)
                has_blocking_fail = any(str(r.get("status", "")).lower() == "fail" and str(r.get("severity","")) == "BLOCKING" for r in stem_results)
                if has_blocking_fail:
                    missing_pass.append(f"{stem}: {verifier} still BLOCKING")
                elif not has_pass:
                    # Temporal verifier emits "skip" when clip missing — that is not verification.
                    # For a repaired stem we require a real pass.
                    missing_pass.append(f"{stem}: {verifier} has no PASS (results={stem_results[:1]})")
        if stale or missing_pass:
            msgs = []
            if stale:
                msgs.append("stale/missing clips: " + "; ".join(stale))
            if missing_pass:
                msgs.append("unverified repaired stems: " + "; ".join(missing_pass))
            if pending_stems:
                msgs.append(f"pending repair_context/hitl stems: {sorted(pending_stems)}")
            sys.exit("[prompt2render] aborting assembly: regenerated sections have not completed fresh render + execution/temporal/semantic gates:\n  " + "\n  ".join(msgs))

        # Also block if *any* repair_context remains for non-HITL stems
        if ctx.repair_context:
            sys.exit(f"[prompt2render] aborting assembly: non-empty repair_context remains: {sorted(ctx.repair_context.keys())}")

        from prompt2render import assemble
        cfg.say("harness: assembling Manim section clips...")
        assemble.assemble(d, s, burn_captions=getattr(a, "burn", False))
        final = d / "out" / "final.mp4"
        if not final.exists() or final.stat().st_size < 1024:
            sys.exit("[prompt2render] Manim assembly did not produce a valid out/final.mp4")
        cfg.say(f"harness: Manim final video ready at {final}")
        # Manim has no still/timeline plan, so the Scenekit final-QC plugin is
        # intentionally not run here. The section-clip assembly is complete;
        # run `prompt2render check` only for a Scenekit build.
        sys.exit(0)

    final_results = ctx.check_results.get("verifier_final_qc")
    if final_results:
        sys.exit(0 if all(r.get("status") in {"pass", "warn", "skip"} for r in final_results) else 1)
    sys.exit(0)


def cmd_auto(a):
    """script.md -> script.md, if it doesn't exist yet -> final.mp4, unattended.

    `new --ai` + `draft` + `build`, chained: a topic and a slug in, a checked
    final.mp4 out, with no manual pause to read the narration first. That is
    a real trade against this project's default stance (see `draft.py`,
    `outline.py`, README) that narration should get a human read before it is
    voiced -- opted into here because the caller asked for exactly that.
    """
    if getattr(a, "manim", False) and not getattr(a, "harness", False):
        sys.exit(
            "[prompt2render] --manim requires the harness path; "
            "use `auto SLUG --harness --manim`"
        )
    from prompt2render import draft, outline
    d = cfg.PROJECTS / a.slug
    if d.exists():
        cfg.say(f"project {d} already exists — using its current script.md")
    else:
        seed = a.title or a.slug.replace("-", " ").title()
        out = outline.generate(seed, seed, "undergraduate computer science",
                               minutes=a.minutes, sections=a.sections,
                               fixed_title=bool(a.title))
        title = a.title or out["title"]
        d = project.new_project_from_sections(a.slug, title, out["sections"],
                                              minutes=a.minutes, topic=out["topic"])
        cfg.say(f"scaffolded {d} with an AI-suggested outline")
    draft.draft(d, force=a.redraft)
    cfg.warn("narration above was AI-drafted and is about to be voiced and "
             "shipped with no human read -- that's what `auto` means. If "
             "this goes out close to as-is, set the synthetic-content "
             "disclosure in YouTube Studio (see out/upload.md's checklist).")
    if getattr(a, "harness", False):
        cmd_harness(a)
    else:
        d, s = _load(a.slug)
        sys.exit(_run_pipeline(d, s, a))


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
    
    hr = add("harness", cmd_harness, "run the full harness pipeline (evaluation & repair)")
    hr.add_argument("slug")
    hr.add_argument("--config", help="path to harness config.yaml")

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
    sc.add_argument("--retries", type=int, default=0,
                    help="positive N caps total attempts at N+1; default 0 continues "
                         "until validation passes; set $P2R_MAX_SCENE_ATTEMPTS>0 for a cap")
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

    def add_pipeline_args(sp):
        """--motion/--speed/.../--scene-jobs: the flags `_run_pipeline` reads,
        shared between `build` (script.md already written) and `auto`."""
        sp.add_argument("--motion", choices=["none", "dissolve", "dissolve+reveal"])
        sp.add_argument("--speed", type=float); sp.add_argument("--voice")
        sp.add_argument("--lufs", type=float)
        sp.add_argument("--burn", action="store_true")
        sp.add_argument("--strict", action="store_true")
        sp.add_argument("--jobs", type=int, default=None,
                        help="parallel encode workers (default 1, or 3 on "
                             "NVENC, or $P2R_ENCODE_JOBS)")
        sp.add_argument("--scene-jobs", type=int, default=None, dest="scene_jobs",
                        help="parallel storyboard calls (default 3, "
                             "or $P2R_SCENE_JOBS)")
        sp.add_argument("--harness", action="store_true", 
                        help="route the build through the new harness layer (evaluation & repair)")
        sp.add_argument("--manim", action="store_true",
                        help="experimental: use Manim to generate scenes instead of scenekit")

    bd = add("build", cmd_build, "voice -> align -> scenes -> ... -> check")
    bd.add_argument("slug")
    bd.add_argument("--config", help="path to harness config.yaml")
    add_pipeline_args(bd)

    au = add("auto", cmd_auto,
            "new --ai -> draft -> build, unattended: topic in, checked video out")
    au.add_argument("slug")
    au.add_argument("--title")
    au.add_argument("--minutes", type=float,
                    help="target length for a fresh project (default 10 "
                         "min = 6 sections); ignored if the project already "
                         "exists")
    au.add_argument("--sections", type=int,
                    help="exact section count for a fresh project instead "
                         "of deriving it from --minutes")
    au.add_argument("--redraft", action="store_true",
                    help="redraft every section's narration even if it's "
                         "already written, not just the placeholders")
    add_pipeline_args(au)

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
    except SystemExit:
        raise
    except Exception as exc:
        sys.exit(f"[prompt2render] {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()