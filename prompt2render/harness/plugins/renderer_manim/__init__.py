"""Manim generation and rendering plugins for Prompt2Render.

This module provides two distinct roles:

1. GeneratorManimPlugin
   - LLM-driven alternative code generator.
   - Generates one Manim Scene per section.
   - Does NOT decide whether generated code is accepted.
   - Supports targeted repair through repair_router.

2. RendererManimPlugin
   - Renders generated Manim scenes.
   - The manual ``prompt2render manim`` escape hatch remains available.
   - Emits blocking findings when Manim compilation/rendering fails.

Acceptance is intentionally downstream:

    generation
        ↓
    code artifact
        ↓
    render
        ↓
    spatial / visual verification
        ↓
    accepted

A generated Python file therefore does not automatically mean that the
scene is accepted.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ...context import CodeArtifact, RenderArtifact, SceneContext
from ...plugin import Plugin
from ..verifier_execution import check_scene_artifact
from ....project import parse_script
from ....visuals import manim_scene


def hitl_status_sets(project_dir: Path | None) -> tuple[set[str], set[str]]:
    """Read ``hitl_feedback.json`` and split stems by status.

    Returns ``(rejected, locked)``. A "reject" entry forces a fresh
    regenerate+rerender. An "accept" entry is a hard LOCK: once the user is
    satisfied with a section, it must never be swept into an unrelated
    regeneration pass again — e.g. the align-mtime staleness heuristic
    below, which otherwise cannot tell "this scene's code is stale" apart
    from "some other scene's narration was re-synced, bumping every align
    file's mtime". Without an explicit lock, that kind of incidental
    trigger silently re-runs the (non-deterministic) LLM on a scene the
    user already approved, and it can come back worse.
    """

    rejected: set[str] = set()
    locked: set[str] = set()

    try:
        import json as _json

        path = project_dir / "hitl_feedback.json" if project_dir else None

        if path and path.exists():
            data = _json.loads(path.read_text(encoding="utf-8") or "{}")

            if isinstance(data, dict):
                for stem, entry in data.items():
                    if not isinstance(entry, dict):
                        continue
                    status = entry.get("status")
                    if status == "reject":
                        rejected.add(str(stem))
                    elif status == "accept":
                        locked.add(str(stem))
    except Exception:
        return set(), set()

    return rejected, locked


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIM_VERSION = "0.19.0"

MANIM_BUILD_DIR = "build/manim"

DEFAULT_MODEL = "gemini-3.7-flash"

DEFAULT_DURATION = 5.0

MAX_REPAIR_FEEDBACK = 6000

#: One initial attempt plus this many local regenerate-and-recheck attempts
#: before a scene's harness check failure is logged and generation moves on
#: to the next scene. See ``generator_code``'s identical constant/pattern.
MAX_HARNESS_CHECK_RETRIES = 1


# ---------------------------------------------------------------------------
# Deterministic Manim compatibility normalization
# ---------------------------------------------------------------------------

def _normalize_manim19(code: str) -> str:
    """Normalize a small set of known Manim 0.19 compatibility aliases.

    This is intentionally conservative.

    It must NOT become a generic code-repair mechanism. Actual semantic or
    compilation failures belong to the generator/repair/verifier pipeline.
    """

    if not isinstance(code, str):
        return ""

    # Strip BOM / zero-width that LLM or PowerShell may inject at start
    if code and code[0] == "\ufeff":
        code = code.lstrip("\ufeff")

    # Known Code keyword alias.
    code = re.sub(
        r"\binsert_line_numbers\s*=",
        "add_line_numbers=",
        code,
    )

    # Direction aliases sometimes emitted by LLMs.
    for old, new in (
        ("UP_LEFT", "UL"),
        ("UP_RIGHT", "UR"),
        ("DOWN_LEFT", "DL"),
        ("DOWN_RIGHT", "DR"),
    ):
        code = re.sub(
            rf"\b{old}\b",
            new,
            code,
        )

    # Known invalid LaTeX string escapes.
    code = re.sub(
        r"\\([&%_$#{}~^])",
        r"\\\\\1",
        code,
    )

    # Manim 0.19: Scene.wait(0) is a ValueError (duration must be >0).
    # The cue map may legitimately have gap 0.00 for back-to-back
    # sentences; LLMs sometimes emit self.wait(0.0) literally, which
    # crashes rendering. Strip those no-ops deterministically.
    # Keep waits >= 0.05s (manim's practical minimum is >0).
    code = re.sub(
        r"^\s*self\.wait\s*\(\s*0+(?:\.0+)?\s*\)\s*(?:\n|$)",
        "",
        code,
        flags=re.M,
    )
    code = re.sub(
        r"self\.wait\s*\(\s*0+(?:\.0+)?\s*\)",
        "self.wait(0.1)",
        code,
    )

    return code


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _safe_int(
    value: Any,
    default: int = 0,
    minimum: int = 0,
) -> int:
    """Safely parse a non-negative integer."""

    try:
        result = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, result)


def _ensure_llm_keys() -> None:
    """Provide legacy llm.keys() compatibility when required."""

    from .... import llm

    if hasattr(llm, "keys"):
        return

    def _keys() -> list[str]:
        keys: list[str] = []

        primary = os.environ.get(
            "GEMINI_API_KEY",
            "",
        ).strip()

        if primary:
            keys.append(primary)

        for name, value in sorted(
            os.environ.items()
        ):
            if (
                name.startswith("GEMINI_API_KEY_BACKUP")
                and value.strip()
            ):
                keys.append(value.strip())

        if not keys:
            raise RuntimeError(
                "[prompt2render] GEMINI_API_KEY is not configured."
            )

        return keys

    llm.keys = _keys


# ---------------------------------------------------------------------------
# Scene/script helpers
# ---------------------------------------------------------------------------

def _build_script(
    context: SceneContext,
):
    """Build the generator Script from the validated scene plan.

    The raw script determines title/narration/meta information.
    The harness scene plan determines scope and visual animation briefs.
    """

    script = parse_script(
        context.prompt
    )

    allowed_indices = {
        int(entry.index)
        for entry in context.scene_plan
    }

    plan_by_index = {
        int(entry.index): entry
        for entry in context.scene_plan
    }

    sections = []

    for section in script.sections:

        if int(section.index) not in allowed_indices:
            continue

        entry = plan_by_index.get(
            int(section.index)
        )

        if entry is None:
            continue

        # Harness-controlled animation brief is authoritative.
        section.anim = entry.anim

        sections.append(section)

    script.sections = sections

    return script


def _find_section(
    script,
    stem: str,
):
    """Find a script section safely."""

    return next(
        (
            section
            for section in script.sections
            if section.stem == stem
        ),
        None,
    )


def _scene_py_path(
    context: SceneContext,
    stem: str,
) -> Path:
    return (
        context.project_dir
        / MANIM_BUILD_DIR
        / f"scene_{stem}.py"
    )


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------

def _record_code_artifact(
    context: SceneContext,
    stem: str,
    path: Path | None,
    *,
    accepted: bool = False,
) -> None:
    """Synchronize code-artifact state.

    ``accepted`` defaults to False because generation alone does not establish
    semantic correctness.
    """

    exists = (
        path is not None
        and path.exists()
        and path.is_file()
    )

    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=path if exists else None,
        accepted=bool(
            accepted and exists
        ),
    )


def _record_failed_code_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=None,
        accepted=False,
    )


def _remove_generated_scene(
    context: SceneContext,
    stem: str,
) -> None:
    """Remove generated code and stale downstream artifacts."""

    py_file = _scene_py_path(
        context,
        stem,
    )

    py_file.unlink(
        missing_ok=True
    )

    context.code_artifacts.pop(
        stem,
        None,
    )

    context.render_artifacts.pop(
        stem,
        None,
    )


# ---------------------------------------------------------------------------
# Repair feedback
# ---------------------------------------------------------------------------

def _repair_feedback(
    context: SceneContext,
    stem: str,
) -> str:
    """Build bounded repair feedback for one scene."""

    repair_context = getattr(
        context,
        "repair_context",
        {},
    )

    if not isinstance(
        repair_context,
        dict,
    ):
        return ""

    messages = repair_context.get(
        stem,
        [],
    )

    if not isinstance(
        messages,
        list,
    ):
        return ""

    clean = [
        str(message).strip()
        for message in messages
        if str(message).strip()
    ]

    if not clean:
        return ""

    feedback = (
        "\n\nPRIOR REPAIR FEEDBACK:\n"
        + "\n".join(
            f"- {message}"
            for message in clean
        )
    )

    return feedback[-MAX_REPAIR_FEEDBACK:]


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

def _load_timing(
    context: SceneContext,
    stem: str,
) -> tuple[float, str, list[dict[str, float]]]:
    """Load sentence timing when available.

    Returns (total_duration, timing_table_text, sentences_list).
    The raw sentences list is kept so the prompt can compute exact
    per-sentence wait deltas (when they are necessary to keep cue
    alignment).  Callers that only need the table can ignore the third
    value.
    """

    try:
        from .... import align

        data = align.load(
            context.project_dir,
            stem,
        )

        sentences = data.get(
            "sentences",
            [],
        )

        if isinstance(sentences, list) and sentences:
            # Support both old (dur) and new (start/end) align formats.
            def _dur(s: dict) -> float:
                if "dur" in s and s.get("dur") is not None:
                    try:
                        return float(s["dur"])
                    except Exception:
                        pass
                try:
                    return float(s.get("end", 0)) - float(s.get("start", 0))
                except Exception:
                    return 0.0

            duration = sum(
                _dur(s) for s in sentences if isinstance(s, dict)
            )
            # fallback to audio_dur if sentences sum is broken (e.g. missing end)
            if duration <= 0.01:
                try:
                    duration = float(data.get("audio_dur", 0))
                except Exception:
                    pass

            timing_lines = []
            for s in sentences:
                if not isinstance(s, dict):
                    continue
                try:
                    st = float(s.get("start", 0))
                    en_raw = s.get("end")
                    if en_raw is None:
                        en_raw = st + float(s.get("dur", 0))
                    en = float(en_raw)
                except Exception:
                    continue
                txt = str(s.get("text", "")).strip()
                timing_lines.append(f"[{st:.2f}s - {en:.2f}s] {txt}")

            if duration > 0 and timing_lines:
                # Normalise sentences to a safe list of dicts with floats
                safe: list[dict[str, float]] = []
                for s in sentences:
                    if not isinstance(s, dict):
                        continue
                    try:
                        st = float(s.get("start", 0))
                        en_raw = s.get("end")
                        if en_raw is None:
                            en_raw = st + float(s.get("dur", 0))
                        en = float(en_raw)
                        dur = float(s.get("dur", en - st))
                        if dur <= 0:
                            dur = max(0.0, en - st)
                        safe.append({
                            "start": float(st),
                            "end": float(en),
                            "dur": float(dur),
                        })
                    except Exception:
                        continue
                return (
                    duration,
                    "\n".join(timing_lines),
                    safe,
                )

    except Exception:
        pass

    return (
        DEFAULT_DURATION,
        "[0.0s - 5.0s] "
        "(No timing data available)",
        [],
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class RendererManimPlugin(Plugin):
    """Render Manim scenes.

    This plugin also preserves the manual Manim escape hatch:

        prompt2render manim <slug> <pyfile> <scene> <index>

    Automatic rendering operates only on accepted/generated code artifacts.
    Rendering failure becomes a blocking finding for repair_router.
    """

    name = "renderer_manim"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
            # Without this, renderer_manim and verifier_execution are mere
            # sibling consumers of code_artifacts with no ordering between
            # them, so "verify before render" held only by accident of
            # registry list order. Depending on the field verifier_execution
            # actually publishes makes the topological sort put it first
            # unconditionally, so a scene can never reach the Manim CLI
            # before its generated code has passed (or been repaired past)
            # the pre-flight static check.
            "static_code_verified",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "render_artifacts",
            "check_results",
        ]

    def _record_render_failure(
        self,
        context: SceneContext,
        stem: str,
        error: Exception | str,
    ) -> None:
        from ...finding import (
            Category,
            Finding,
            Severity,
            next_finding_id,
        )

        message = str(error)

        finding = Finding(
            finding_id=next_finding_id(
                "manim"
            ),
            scene_id=stem,
            category=Category.RENDER,
            severity=Severity.BLOCKING,
            message=(
                "Manim compilation/render failed:\n"
                f"{message}"
            ),
        )

        result = finding.as_check_result()
        result["finding_type"] = "manim_crash"

        context.check_results.setdefault(
            self.name,
            [],
        ).append(result)

        context.render_artifacts[stem] = (
            RenderArtifact(
                stem=stem,
                outdir=context.project_dir,
                manifest=[],
            )
        )

    def _render_one(
        self,
        context: SceneContext,
        script,
        artifact: CodeArtifact,
        section,
    ) -> None:
        from .... import cfg

        stem = artifact.stem

        try:
            out = manim_scene(
                context.project_dir,
                script,
                artifact.path,
                f"Scene{stem}",
                section.index,
            )

            context.render_artifacts[stem] = (
                RenderArtifact(
                    stem=stem,
                    outdir=out.parent,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                )
            )

        except SystemExit as exc:
            # visuals.manim_scene historically calls sys.exit().
            error = str(exc)

            cfg.warn(
                f"Manim render failed for {stem}: "
                f"{error}"
            )

            self._record_render_failure(
                context,
                stem,
                error,
            )

        except Exception as exc:
            cfg.warn(
                f"Manim render failed for {stem}: "
                f"{exc}"
            )

            self._record_render_failure(
                context,
                stem,
                exc,
            )

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        # ---------------------------------------------------------------
        # Manual escape hatch
        # ---------------------------------------------------------------

        py_file = self.config.get(
            "py_file"
        )

        scene = self.config.get(
            "scene"
        )

        index = self.config.get(
            "index"
        )

        script = parse_script(
            context.prompt
        )

        if (
            py_file
            and scene
            and index is not None
        ):
            try:
                numeric_index = int(index)
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    f"Invalid Manim index: {index}"
                ) from exc

            out = manim_scene(
                context.project_dir,
                script,
                Path(py_file),
                str(scene),
                numeric_index,
            )

            stem = (
                f"{numeric_index:02d}"
            )

            context.render_artifacts[stem] = (
                RenderArtifact(
                    stem=stem,
                    outdir=out.parent,
                    manifest=[
                        {
                            "png": None,
                            "mp4": str(out),
                        }
                    ],
                )
            )

            return context

        # ---------------------------------------------------------------
        # Automatic rendering
        # ---------------------------------------------------------------

        if not context.code_artifacts:
            return context

        # Preserve successful renders unless this scene is explicitly
        # being repaired.  HITL rejects are treated as repairs so the
        # sections listed in hitl_feedback.json are always re-rendered to
        # a fresh clip before any assembly decision.
        repair_context = getattr(
            context,
            "repair_context",
            {},
        )
        hitl_rejects_r, locked_r = hitl_status_sets(context.project_dir)

        for stem, artifact in list(
            context.code_artifacts.items()
        ):

            if (
                not artifact.path
                or not artifact.path.exists()
            ):
                continue

            if (
                artifact.accepted is False
                and stem not in repair_context
            ):
                # Generated code exists but has not yet passed downstream
                # code/semantic acceptance. It may still be rendered for
                # verification depending on the surrounding pipeline, so
                # we intentionally do not reject it here.
                pass

            existing = context.render_artifacts.get(
                stem
            )

            # A locked (hitl "accept") stem with an existing render is done —
            # skip unconditionally, even if a stray repair_context/reject
            # entry would otherwise force a re-render. Its code never
            # changes once locked (see the generator's own lock check), so
            # the only thing a forced re-render could do here is burn time
            # reproducing the same clip.
            if existing and existing.manifest and stem in locked_r:
                continue

            if (
                existing
                and existing.manifest
                and stem not in repair_context
                and stem not in hitl_rejects_r
            ):
                continue

            section = _find_section(
                script,
                stem,
            )

            if section is None:
                continue

            self._render_one(
                context,
                script,
                artifact,
                section,
            )

        return context

    def _default_gate(self) -> bool:
        # Rendering is not an upstream quality gate.
        return False


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class GeneratorManimPlugin(Plugin):
    """Generate Manim code for each validated scene.

    This is an alternative backend to generator_code.

    It is deliberately LLM-driven, but the LLM is constrained by:
    - the validated scene plan,
    - the storyboard/visual contract,
    - exact narration timing,
    - Manim CE 0.19 compatibility rules,
    - and repair feedback.

    Generated code is NOT automatically accepted.
    """

    name = "generator_manim"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "narration",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "code_artifacts",
        ]

    def _get_llm_client(
        self,
    ):
        """Compatibility fallback for older llm implementations."""

        from .... import llm

        _ensure_llm_keys()

        keys = llm.keys()

        if not keys:
            raise RuntimeError(
                "No Gemini API key configured."
            )

        if hasattr(
            llm,
            "client",
        ):
            return (
                llm,
                llm.client(keys[0]),
                None,
            )

        try:
            if hasattr(
                llm,
                "model_chain",
            ):
                models = llm.model_chain(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                )

                model = models[0]

            else:
                model = os.environ.get(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                )

            if hasattr(
                llm,
                "complete",
            ):
                return (
                    llm,
                    None,
                    model,
                )

            from openai import OpenAI

            client = OpenAI(
                api_key=keys[0],
                base_url=(
                    "https://generativelanguage."
                    "googleapis.com/v1beta/openai/"
                ),
                timeout=300.0,
                max_retries=2,
            )

            return (
                llm,
                client,
                model,
            )

        except ImportError as exc:
            raise RuntimeError(
                "Neither the project LLM client nor "
                "the OpenAI compatibility client is available."
            ) from exc

    def _build_prompt(
        self,
        section,
        timing_table: str,
        duration: float,
        extra_feedback: str,
        sentences: list[dict[str, float]] | None = None,
    ) -> str:
        """Construct the deterministic Manim generation contract."""

        # Build exact per-sentence cue deltas so the LLM can emit precise
        # self.wait() values.  When necessary (i.e. when the narration has
        # >1 sentence) the animation for sentence N must start exactly at
        # sentences[N].start — the gap to the next cue is the source of
        # truth, not an estimated run_time.
        cue_block = ""
        if sentences and len(sentences) > 1:
            lines = []
            for idx, s in enumerate(sentences):
                st = float(s.get("start", 0))
                en = float(s.get("end", st + float(s.get("dur", 0))))
                dur = float(s.get("dur", en - st))
                nxt = float(sentences[idx + 1].get("start", en)) if idx + 1 < len(sentences) else duration
                gap = max(0.0, nxt - en)
                # Only emit a wait cue when the narration actually has a gap;
                # when sentences are back-to-back the gap is ~0 and no extra
                # wait is necessary. Emitting wait(0.0) crashes Manim
                # (ValueError: duration <=0), so suppress it.
                if idx + 1 < len(sentences):
                    if gap > 0.05:
                        lines.append(
                            f"  - After sentence {idx+1} ends at {en:.2f}s, wait {gap:.2f}s "
                            f"(until {nxt:.2f}s) before starting sentence {idx+2}'s animation."
                        )
                    else:
                        lines.append(
                            f"  - After sentence {idx+1} ends at {en:.2f}s, next sentence starts immediately at {nxt:.2f}s (gap ≈0, no wait needed)."
                        )
                # Highlight duration budget for this sentence's animation
                lines.append(
                    f"  - Sentence {idx+1} window: start {st:.2f}s, duration budget {dur:.2f}s "
                    f"(do not overrun {en:.2f}s)."
                )
            cue_block = "\n".join(lines)
        elif sentences and len(sentences) == 1:
            s = sentences[0]
            cue_block = (
                f"  - Single-sentence section: animation window is "
                f"{float(s.get('start',0)):.2f}s → {float(s.get('end', duration)):.2f}s "
                f"(budget {float(s.get('dur', duration)):.2f}s)."
            )

        prompt = f"""
Write a Manim Community Edition {MANIM_VERSION} script for this educational
video section.

TITLE:
{section.title}

VISUAL PLAN:
{section.anim}

NARRATION WITH EXACT TIMING:
{timing_table}

TOTAL DURATION:
{duration:.1f} seconds
"""
        if cue_block:
            prompt += f"""
EXACT CUE MAP (use these waits when they are necessary to keep sync):
{cue_block}
"""

        prompt += f"""
REQUIREMENTS:

1. Use Manim Community Edition v{MANIM_VERSION}.
   Use:
        from manim import *

   Do not use APIs introduced after v{MANIM_VERSION}.

2. Define exactly one class:
        Scene{section.stem}

   It must inherit from Scene.

3. EXACT SYNCHRONIZATION (CRITICAL — when they are necessary):
   You MUST use the exact start times from the NARRATION table and CUE MAP above.
   - Do NOT start an animation before its corresponding narration sentence begins.
    - Between sentences, use `self.wait(gap)` where gap is the exact value from the CUE MAP.
      When sentences are back-to-back (gap ≤0.05), do NOT insert any self.wait at all — Manim
      rejects wait(0) with ValueError. Let the next animation start immediately, but still
      ensure the previous animation's run_time did not overrun its window. NEVER emit
      self.wait(0) or self.wait(0.0).
    - Set each `self.play(..., run_time=...)` so the animation fits inside its sentence's
      duration budget.  Prefer `run_time = min(budget*0.85, natural_duration)` and then
      `self.wait(remaining)` to fill to the exact cue (remaining must be >0).
    - For example, if sentence 2 starts at 4.50s and sentence 1 ends at 4.20s, insert
      `self.wait(0.30)` after sentence 1's animation before starting sentence 2's. If the gap
      is 0.00, insert no wait.
   
   The total animation duration MUST equal:
        {duration:.1f} seconds

4. LAYOUT:
   - Title: UP * 3.5
   - Title font_size: 48
   - Primary visual: centered or slightly above center
   - Supporting text: below DOWN * 2.0
   - Do not overlap text and graphics.

5. TEXT:
   - Break long sentences into multiple lines.
   - Scale text when necessary.
   - Never allow text to leave the 16:9 frame.
   - Prefer concise labels over paragraphs.

6. MANIM 0.19 API SAFETY:
   - Do not pass font_size or direction to Axes.get_x_label/get_y_label. Create Text labels and position them with next_to.
   - Do not pass corner= to move_to. Use move_to(point) or align_to.
   - Do not pass theme= to Code. Use Code(code_string=..., language=...).
   - Do not pass row_height=, col_widths=, or include_background= to MobjectTable or Table. Scale the entire table using scale() or scale_to_fit_width() instead.
   - Do not pass include_background= to Text, MathTex, or Tex.
   - For Code line numbers use add_line_numbers=True. Never use insert_line_numbers.
   - Use UL/UR/DL/DR. Never use UP_LEFT/UP_RIGHT/DOWN_LEFT/DOWN_RIGHT.

7. VECTOR SAFETY & SHAPES:
   - move_to() requires a coordinate vector.
   - put_start_and_end_on() requires coordinate vectors.
   - Never pass a scalar where a 3D coordinate is required.
   - SurroundingRectangle, BackgroundRectangle, and always_redraw require a Mobject (like a Text or Circle), NOT a coordinate array. Never pass number_to_point(), get_center(), or c2p() directly to them.

9. Do not use:
   - undocumented keyword arguments
   - deprecated classes
   - unknown Manim APIs
   - .set_shadow(blur=...)
   - invented helper APIs

10. Preserve all numerical values and relationships from the visual plan.

11. Implement the storyboard progressively.
     Do not display unrelated major visual elements simultaneously.
     When a new sentence's visual builds on the previous, keep prior mobjects on screen
     and animate the delta — do not clear the scene between cues unless the brief
     explicitly demands it.

12. The visual plan is authoritative.
     Do not reinterpret or replace its core visual claim.

13. Output ONLY valid Python code.
    No Markdown fences.
    No explanation.
""".strip()

        if extra_feedback:
            prompt += (
                "\n\n"
                + extra_feedback
            )

        return prompt

    def _generate_code(
        self,
        prompt: str,
    ) -> str:
        """Generate code through the project's LLM abstraction."""

        from .... import llm

        _ensure_llm_keys()

        if hasattr(
            llm,
            "complete",
        ):
            code = llm.complete(
                prompt,
                max_tokens=5000,
                model_env="P2R_SCENE_MODEL",
                default_model=os.environ.get(
                    "P2R_SCENE_MODEL",
                    DEFAULT_MODEL,
                ),
                label="manim",
            )

            return str(code or "")

        _, client, model = (
            self._get_llm_client()
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        if not response.choices:
            return ""

        return str(
            response.choices[0].message.content
            or ""
        )

    def _clean_generated_code(
        self,
        code: str,
    ) -> str:
        """Remove fences and apply deterministic compatibility normalization."""

        code = (
            code
            or ""
        ).strip()

        # Strip Markdown code fences.
        match = re.match(
            r"^```(?:python)?\s*\n(.*?)\n```\s*$",
            code,
            re.S,
        )

        if match:
            code = match.group(1)

        return _normalize_manim19(
            code
        ).strip()

    def _generate_one(
        self,
        context: SceneContext,
        section,
    ) -> None:
        """Generate exactly one Manim scene."""

        from .... import cfg

        stem = section.stem

        outdir = (
            context.project_dir
            / MANIM_BUILD_DIR
        )

        outdir.mkdir(
            parents=True,
            exist_ok=True,
        )

        py_file = (
            outdir
            / f"scene_{stem}.py"
        )

        duration, timing_table, sentences = (
            _load_timing(
                context,
                stem,
            )
        )

        extra_feedback = (
            _repair_feedback(
                context,
                stem,
            )
        )

        prompt = self._build_prompt(
            section,
            timing_table,
            duration,
            extra_feedback,
            sentences,
        )

        try:
            code = self._generate_code(
                prompt
            )

            code = self._clean_generated_code(
                code
            )

            if not code:
                raise RuntimeError(
                    "LLM returned empty Manim code."
                )

            # Write only after successful generation and normalization.
            py_file.write_text(
                code,
                encoding="utf-8",
            )

            # IMPORTANT:
            # Generated != accepted.
            _record_code_artifact(
                context,
                stem,
                py_file,
                accepted=False,
            )

            cfg.say(
                f"section {stem}: "
                "Manim code generated"
            )

        except Exception as exc:
            cfg.warn(
                f"Manim generation failed for "
                f"{stem}: {exc}"
            )

            _record_failed_code_artifact(
                context,
                stem,
            )

    def _generate_and_check_one(
        self,
        context: SceneContext,
        section,
    ) -> None:
        """Generate one Manim scene, then send it to the harness immediately.

        ``_generate_one`` alone leaves the file completely unverified until
        the batch ``verifier_execution`` stage runs later in the pipeline —
        which meant a scene with a plain syntax error could sit unrewound
        long enough for ``renderer_manim`` to try (and crash on) it. This
        checks the file the instant it's written, retries once locally by
        feeding the harness's own diagnostics back as repair feedback, and
        otherwise logs the failure and moves on — the real
        ``verifier_execution`` pipeline stage remains the actual gate.
        """

        from .... import cfg

        stem = section.stem

        entry = next(
            (e for e in context.scene_plan if e.stem == stem),
            None,
        )

        attempt = 0

        while True:
            self._generate_one(context, section)

            artifact = context.code_artifacts.get(stem)
            if entry is None or artifact is None or artifact.path is None:
                # Generation itself already failed and logged a warning;
                # there is nothing on disk to send to the harness.
                return

            findings = check_scene_artifact(context, entry, gate=True)
            blocking = [
                f for f in findings
                if isinstance(f, dict) and str(f.get("status", "")).lower() == "fail"
            ]

            if not blocking:
                cfg.say(f"section {stem}: harness check passed")
                return

            if attempt >= MAX_HARNESS_CHECK_RETRIES:
                cfg.say(
                    f"section {stem}: harness check failed after "
                    f"{attempt + 1} attempt(s) — logging and continuing"
                )
                log = context.check_results.setdefault(
                    "generator_manim:preflight", []
                )
                log.extend(blocking)
                return

            attempt += 1
            first = str(
                blocking[0].get("detail") or blocking[0].get("message") or ""
            )[:110]
            cfg.say(
                f"section {stem}: harness check failed — {first} — retrying "
                f"({attempt}/{MAX_HARNESS_CHECK_RETRIES})"
            )

            diagnostics = [
                str(f.get("detail") or f.get("message") or "").strip()
                for f in blocking
                if isinstance(f, dict)
            ]
            context.repair_context.setdefault(stem, []).extend(
                d for d in diagnostics if d
            )

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        if not context.scene_plan:
            raise RuntimeError(
                "GeneratorManimPlugin received "
                "an empty scene plan."
            )

        _ensure_llm_keys()

        script = _build_script(
            context
        )

        if not script.sections:
            raise RuntimeError(
                "No script sections remain "
                "after scene-plan filtering."
            )

        outdir = (
            context.project_dir
            / MANIM_BUILD_DIR
        )

        outdir.mkdir(
            parents=True,
            exist_ok=True,
        )

        repair_context = getattr(
            context,
            "repair_context",
            {},
        )
        # HITL file is authoritative: if a stem is still listed as reject,
        # it must be regenerated even if repair_context is empty at the
        # start of a fresh harness invocation (the previous rewind fix was
        # not reliably re-rendering before assembly).  Read once per run.
        hitl_rejects: set[str] = set()
        try:
            import json as _json
            _hf = context.project_dir / "hitl_feedback.json" if context.project_dir else None
            if _hf and _hf.exists():
                _data = _json.loads(_hf.read_text(encoding="utf-8") or "{}")
                if isinstance(_data, dict):
                    for _k, _v in _data.items():
                        if isinstance(_v, dict) and _v.get("status") == "reject":
                            hitl_rejects.add(str(_k))
        except Exception:
            hitl_rejects = set()

        for section in script.sections:

            stem = section.stem

            py_file = (
                outdir
                / f"scene_{stem}.py"
            )

            is_repair = (
                stem in repair_context or stem in hitl_rejects
            )
            # If alignment was re-done (e.g. after voice re-synthesis,
            # narration 39s vs cached 5s code), the cached code is stale
            # even though hitl and repair_context are empty. Detect via
            # file mtimes: align JSON newer than code => must regenerate.
            if not is_repair and py_file.exists():
                try:
                    from .... import align as _align_mod
                    align_path = _align_mod.path_for(context.project_dir, stem)
                    if align_path.exists():
                        if align_path.stat().st_mtime > py_file.stat().st_mtime + 1.0:
                            is_repair = True
                except Exception:
                    pass

            # ----------------------------------------------------------
            # Cache handling
            # ----------------------------------------------------------

            if (
                py_file.exists()
                and not is_repair
            ):
                try:
                    cached_code = (
                        py_file.read_text(
                            encoding="utf-8"
                        )
                    )

                    normalized = (
                        _normalize_manim19(
                            cached_code
                        )
                    )

                    if normalized != cached_code:
                        py_file.write_text(
                            normalized,
                            encoding="utf-8",
                        )

                    # Cached code is generated, not automatically accepted.
                    _record_code_artifact(
                        context,
                        stem,
                        py_file,
                        accepted=False,
                    )

                    from .... import cfg

                    cfg.say(
                        f"section {stem}: "
                        "cached, skipping"
                    )

                    continue

                except Exception:
                    # A corrupt/unreadable cache should be regenerated.
                    py_file.unlink(
                        missing_ok=True
                    )

            self._generate_and_check_one(
                context,
                section,
            )

        return context

    def _default_gate(self) -> bool:
        # Generation itself is not a quality gate.
        return False

    # ------------------------------------------------------------------
    # repair_router hooks
    # ------------------------------------------------------------------

    def revert_scene(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Remove exactly one generated scene."""

        plan = {
            str(entry.stem)
            for entry in context.scene_plan
        }

        if stem not in plan:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        _remove_generated_scene(
            context,
            stem,
        )

    def regenerate_one(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Regenerate exactly one Manim scene.

        This does NOT call run() and does NOT regenerate unrelated scenes.
        """

        if not context.scene_plan:
            raise RuntimeError(
                "Cannot repair Manim scene: "
                "scene plan is empty."
            )

        entry = next(
            (
                item
                for item in context.scene_plan
                if str(item.stem) == str(stem)
            ),
            None,
        )

        if entry is None:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        _ensure_llm_keys()

        script = _build_script(
            context
        )

        section = _find_section(
            script,
            stem,
        )

        if section is None:
            raise ValueError(
                f"Scene '{stem}' is not "
                "present in the current script."
            )

        # Scene-plan visual contract remains authoritative.
        section.anim = entry.anim

        # Generate only this section.
        self._generate_and_check_one(
            context,
            section,
        )