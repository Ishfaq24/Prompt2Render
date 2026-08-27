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
    sys.exit(doctor.doctor(render_test=getattr(a, "render_test", False)))


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

def _report_self_check(ctx, journal) -> None:
    """Run the harness self-check (P1-3) and surface what it finds.

    Never a gate -- this never raises and never calls sys.exit. It prints
    BLOCKING findings (a real, on-disk inconsistency, not a content
    judgment) and journals a harness.selfcheck summary event either way,
    so "did the harness's own bookkeeping check out" is answered from
    build/harness/events.jsonl even when nobody read the console output.
    """

    try:
        from prompt2render.harness.selfcheck import run_self_check

        findings = run_self_check(ctx)
    except Exception as exc:
        cfg.warn(f"harness self-check itself raised {type(exc).__name__}: {exc}")
        findings = []

    blocking = [f for f in findings if f.get("severity") == "BLOCKING"]

    for finding in blocking:
        cfg.warn(f"harness self-check: {finding.get('detail')}")

    if journal is not None:
        project = ctx.project_dir.name if ctx.project_dir else ""
        journal.append(
            event_type="harness.selfcheck",
            project=project,
            scene_id="__all__",
            status="fail" if blocking else "ok",
            payload={
                "total_findings": len(findings),
                "blocking": len(blocking),
            },
        )


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

    # Tier 2 Phase 8-9 (F13 fix): generator_manim/renderer_manim_finish/
    # verifier_manim_final_qc are now normal REGISTRY entries, so selecting
    # Manim mode is pure config toggling resolved by build_plugins() itself
    # -- no post-hoc plugin-list splicing needed. Each Manim/stills pair
    # declares the same effect (code_artifacts / render_artifacts /
    # final_video), so the loader's existing effect-collision rejection is
    # what enforces "exactly one enabled at a time", the same mechanism
    # that already governed renderer_stills/renderer_manim before this fix.
    #
    # A stale config from an earlier experimental run must not inject Manim
    # into ordinary --harness builds. Only an explicit --manim opts in.
    if not getattr(a, "manim", False):
        cfg_dict.setdefault("generator_manim", {})["enabled"] = False
        cfg_dict.setdefault("renderer_manim", {})["enabled"] = False
        cfg_dict.setdefault("renderer_manim_finish", {})["enabled"] = False
        cfg_dict.setdefault("verifier_manim_final_qc", {})["enabled"] = False
        # Tier 3 Phase 11/12: only meaningful for Manim clips; nothing to
        # observe on the stills path.
        cfg_dict.setdefault("observer_visual", {})["enabled"] = False
        cfg_dict.setdefault("verifier_motion", {})["enabled"] = False
    else:
        cfg_dict.setdefault("generator_code", {})["enabled"] = False
        cfg_dict.setdefault("generator_manim", {})["enabled"] = True
        cfg_dict.setdefault("renderer_stills", {})["enabled"] = False
        cfg_dict.setdefault("renderer_manim", {})["enabled"] = True
        cfg_dict.setdefault("renderer_finish", {})["enabled"] = False
        cfg_dict.setdefault("renderer_manim_finish", {})["enabled"] = True
        cfg_dict.setdefault("verifier_final_qc", {})["enabled"] = False
        cfg_dict.setdefault("verifier_manim_final_qc", {})["enabled"] = True
        # Tier 3 Phase 11 (F3/F4): closes the loop for the Manim path --
        # RenderArtifact.audit was always None there before this, so
        # verifier_spatial always reported skip.
        cfg_dict.setdefault("observer_visual", {})["enabled"] = True
        # Tier 3 Phase 12: first real producer of the "motion" quality
        # dimension (quality_report.py).
        cfg_dict.setdefault("verifier_motion", {})["enabled"] = True
        # Manim produces one complete clip per section directly -- the
        # stills-only per-frame Ken-Burns plan/encode stages (F12: this used
        # to mean the whole production tail was disabled and --manim could
        # never reach a shippable final video) are simply not needed.
        cfg_dict.setdefault("generator_timeline", {})["enabled"] = False
        cfg_dict.setdefault("renderer_encode", {})["enabled"] = False
        # generator_publish/verifier_audio no longer force-disabled: both
        # only need out/final.mp4 to exist, which renderer_manim_finish now
        # produces within the harness itself (verifier_audio's old comment,
        # "assemble runs *after* the harness", no longer applies).
        cfg.say("harness: running in experimental --manim mode")

    # Tier 4: HITL extension -- three modes over the SAME hitl_feedback.json
    # contract (SS18, "must be extended, not replaced"). AUTONOMOUS is
    # today's unchanged behaviour (default): verifier_hitl_approval stays
    # off, a hard GateFailure just exits. HUMAN_APPROVAL turns on the new
    # publish-blocking approval gate. HUMAN_ON_FAILURE doesn't touch any
    # plugin at all -- see the GateFailure handler below, where it drafts a
    # review-needed file instead of just exiting.
    hitl_mode = str(getattr(a, "hitl_mode", None) or "autonomous").strip().lower()

    if hitl_mode not in ("autonomous", "human_on_failure", "human_approval"):
        cfg.warn(f"unknown --hitl-mode {hitl_mode!r}; falling back to autonomous")
        hitl_mode = "autonomous"

    cfg_dict.setdefault("verifier_hitl_approval", {})["enabled"] = (
        hitl_mode == "human_approval"
    )

    plugins = build_plugins(config=cfg_dict)

    log_path = d / "build" / "harness" / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = StructuredLogger(log_path)
    bus = EventBus()

    # Durable, append-only build event journal -- the replayable record of
    # what happened to each scene, distinct from log.jsonl (per-plugin
    # invocation) and repair_log.jsonl (per-repair-cycle decisions). See
    # harness/journal.py's module docstring for why this is a separate
    # file rather than a reformatting of either.
    from prompt2render.harness.journal import EventJournal

    journal = EventJournal(d / "build" / "harness" / "events.jsonl")

    # The repair controller is the single authority over the repair
    # lifecycle: detect -> snapshot -> repair -> re-verify every scene
    # verifier -> compare against the accepted scene -> accept or restore.
    # The router underneath it only routes and executes; it no longer
    # decides whether a repair worked.
    from prompt2render.harness.loader import build_repair_controller

    repair_controller = build_repair_controller(
        plugins,
        config=cfg_dict,
        logger=logger,
        log_path=d / "build" / "harness" / "repair_log.jsonl",
        journal=journal,
    )

    if repair_controller is not None:
        repair_controller.router.attach(bus=bus)

    # Clear any candidate trees left by an interrupted earlier run so a
    # stale sidecar can never be mistaken for this run's work.
    from prompt2render.harness import workspace as _workspace

    _workspace.cleanup_candidates(d)


    # Attach live progress UI if running in a TTY
    progress = None
    import sys
    if sys.stdout.isatty():
        from prompt2render.harness.progress import HarnessProgressUI
        progress = HarnessProgressUI(total_stages=len(plugins))
        progress.attach(bus)
        
    ctx = SceneContext(prompt=script_path, project_dir=d)
    runner = HarnessRunner(
        plugins,
        logger,
        bus,
        repair_controller=repair_controller,
        journal=journal,
    )

    cfg.say(f"running harness over {a.slug}: " + " -> ".join(p.name for p in plugins))
    try:
        ctx = runner.run(ctx)
    except GateFailure as e:
        if progress:
            progress.stop()
        # Tier 3 Phase 10: written on both outcomes -- check_results is only
        # known-complete once the runner has finished, and the report is
        # arguably most useful exactly when the run failed. write_quality_report
        # never raises, so this can't mask the real GateFailure below.
        from prompt2render.harness.quality_report import write_quality_report
        write_quality_report(ctx.check_results, ctx.project_dir)

        # P1-2: backfill build/harness/revisions.json for any scene that
        # reached a positive revision this run but has no repair-cycle
        # history yet (never repaired, or repaired in an earlier process
        # whose in-memory scene_versions did not survive). Never raises.
        from prompt2render.harness.revision_history import seed_from_context
        seed_from_context(ctx.project_dir, ctx)

        # P1-3: the harness's own consistency audit -- never a new gate,
        # only a printed/journaled fact. See selfcheck.py's module
        # docstring: this is what stands between "an LLM said it fixed
        # it" and an actual answer about what is on disk.
        _report_self_check(ctx, journal)

        # Tier 3 Phase 15: same reasoning -- the repair controller's
        # decision log is complete regardless of the final gate outcome,
        # and a hard-failed run's repair episodes are exactly the ones
        # worth remembering for next time. Never raises.
        #
        # Bug fix: this used to read ctx.repair_records, a list only the
        # OLD router-owned repair path ever populated -- RepairController
        # (the current repair owner) never wrote to it, so
        # experience_memory.jsonl was never actually produced by any real
        # run. from_decision_records reads the controller's own
        # authoritative decisions instead.
        from prompt2render.harness.experience import (
            append_experience,
            from_decision_records,
        )
        if repair_controller is not None:
            append_experience(
                ctx.project_dir,
                from_decision_records(repair_controller.decisions),
            )

        # Tier 4, HUMAN_ON_FAILURE mode: draft hitl_review_needed.json from
        # this exact failure's findings instead of leaving the human to
        # hand-author reject entries from scratch by reading logs (today's
        # only documented workflow, HITL_WORKFLOW.md). Never raises, and
        # never touches hitl_feedback.json itself -- see harness/hitl.py's
        # docstring for why a separate, inert draft file is the safe choice.
        if hitl_mode == "human_on_failure":
            from prompt2render.harness.hitl import write_review_draft

            draft_path = write_review_draft(ctx.project_dir, e.findings)

            if draft_path is not None:
                cfg.say(
                    f"HUMAN_ON_FAILURE: drafted {draft_path} -- review it, "
                    "then edit/rename it to hitl_feedback.json (see "
                    "HITL_WORKFLOW.md) and re-run."
                )

        sys.exit(f"[prompt2render] harness hard gate failed: {e}")
    finally:
        if progress:
            progress.stop()

    from prompt2render.harness.quality_report import write_quality_report
    write_quality_report(ctx.check_results, ctx.project_dir)

    # P1-2: see the matching comment in the GateFailure branch above.
    from prompt2render.harness.revision_history import seed_from_context
    seed_from_context(ctx.project_dir, ctx)

    # P1-3: see the matching comment in the GateFailure branch above.
    _report_self_check(ctx, journal)

    # Bug fix: write_self_correction_report(final_pass=True) was never
    # called anywhere -- the three existing call sites are all inside
    # runner.py's failure paths (gate failure, stage exception,
    # finalization failure). A successful run therefore left
    # out/self_correction_report.json either absent or holding a stale
    # report from the project's last *failed* attempt, silently claiming
    # final_pass=False for a build that just shipped out/final.mp4. Called
    # unguarded here, matching every existing call site inside
    # runner.py's own failure paths (none of them wrap it either).
    from prompt2render.harness.logging_ import write_self_correction_report
    write_self_correction_report(
        ctx,
        final_pass=True,
        repair_controller=repair_controller,
    )

    # Tier 3 Phase 15: durable, cross-run experience memory -- see
    # harness/experience.py's module docstring for the gap this closes
    # (repair_context is deleted on success; self_correction_report.json is
    # overwritten every run; nothing previously survived across builds).
    #
    # Bug fix: see the matching comment in the GateFailure branch above --
    # ctx.repair_records is never populated by the current repair
    # controller; from_decision_records(repair_controller.decisions) is.
    from prompt2render.harness.experience import (
        append_experience,
        from_decision_records,
    )
    if repair_controller is not None:
        append_experience(
            ctx.project_dir,
            from_decision_records(repair_controller.decisions),
        )

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
                        # Not hard-coded to "1080p30": Manim names that
                        # directory after the resolution/fps it actually
                        # rendered at, so a literal stops matching the moment
                        # P2R_MANIM_QUALITY or the fps moves.
                        from prompt2render.visuals import latest_manim_clip
                        cand3 = latest_manim_clip(d, stem)
                        if cand3 is not None:
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


def cmd_ablation(a):
    """Run the Stage 5 Phase A detection-only ablation matrix.

    F16 (docs/ARCHITECTURE_AUDIT.md SS12): tools/ablation_runner.py
    previously had no CLI wiring at all -- this is a thin wrapper over its
    own run_ablation(), the same function the standalone
    `python tools/ablation_runner.py` entry point now also calls.
    """
    from prompt2render.tools.ablation_runner import run_ablation

    run_ablation(
        a.slug,
        config_path=Path(a.config) if a.config else None,
        out_path=Path(a.out) if a.out else None,
    )


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

    dc = add("doctor", cmd_doctor,
             "check the environment before you spend an hour")
    dc.add_argument("--render-test", action="store_true", dest="render_test",
                    help="also render a real Manim smoke scene and verify it "
                         "is 1920x1080 at 30 fps (slower; needs manim)")

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

    ab = add("ablation", cmd_ablation,
             "Stage 5 Phase A: 4-condition detection-only ablation matrix "
             "(verifier_spatial x verifier_lifecycle on/off)")
    ab.add_argument("slug")
    ab.add_argument("--config", help="path to harness config.yaml")
    ab.add_argument("--out", help="output JSON path (default: "
                                   "<project>/build/harness/ablation_results.json)")

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
        sp.add_argument("--hitl-mode", dest="hitl_mode",
                        choices=["autonomous", "human_on_failure", "human_approval"],
                        default="autonomous",
                        help="Tier 4 HITL mode over the same hitl_feedback.json contract: "
                             "autonomous (default, today's behaviour), human_on_failure "
                             "(drafts hitl_review_needed.json on a hard gate failure instead "
                             "of just exiting), human_approval (blocks generator_publish "
                             "until every section has an explicit hitl_feedback.json accept)")

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