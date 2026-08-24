"""Coder role for Prompt2Render.

This plugin is the boundary between planning and executable scene generation.

Responsibilities
----------------
1. Consume the verified scene plan and storyboard.
2. Delegate actual code generation to ``scenes.generate``, one section at a
   time, sending each generated scene straight to the harness's own
   ``verifier_execution`` check before moving on to the next section.
3. Preserve the existing generator's internal retry/key-rotation behaviour.
4. Never silently overwrite an existing scene.
5. Support deterministic per-scene rollback and regeneration.
6. Feed repair-router diagnostics back into targeted generation.
7. Record code-artifact provenance.
8. Treat file existence as necessary but NOT sufficient evidence of success.

The generator itself remains the authority for LLM-based code generation.
The harness controls orchestration, provenance, gating, and repair.
"""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ...context import CodeArtifact, SceneContext
from ...plugin import Plugin
from ..verifier_execution import check_scene_artifact
from ....project import parse_script
from ....scenes import default_jobs, generate
from ....stills import is_current, scene_path, stills_dir
from .... import cfg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REPAIR_FEEDBACK = 6000

#: One initial attempt plus this many local regenerate-and-recheck attempts
#: before a scene's harness check failure is logged and generation moves on
#: to the next scene. ``scenes.generate()`` already retries hard against its
#: own preflight validator; this is only a safety net for defects that only
#: the harness's own check (e.g. Manim-vs-SceneKit backend detection) would
#: catch.
MAX_HARNESS_CHECK_RETRIES = 1


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _safe_int(
    value: Any,
    default: int = 0,
    minimum: int = 0,
) -> int:
    """Safely parse a non-negative integer configuration value."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, parsed)


# ---------------------------------------------------------------------------
# LLM compatibility
# ---------------------------------------------------------------------------

def _ensure_llm_keys() -> None:
    """Provide legacy ``llm.keys`` compatibility when necessary.

    Prefer the real implementation when available. The fallback exists only
    for compatibility with older versions of the project.
    """

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
                name.startswith(
                    "GEMINI_API_KEY_BACKUP"
                )
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
# Filesystem helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str | None:
    """Return the SHA-256 digest of a file."""

    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _artifact_exists(
    context: SceneContext,
    stem: str,
) -> bool:
    path = scene_path(
        context.project_dir,
        stem,
    )

    return path.exists() and path.is_file()


def _record_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    """Synchronise the in-memory artifact record with disk."""

    path = scene_path(
        context.project_dir,
        stem,
    )

    exists = (
        path.exists()
        and path.is_file()
    )

    context.code_artifacts[stem] = CodeArtifact(
        stem=stem,
        path=path if exists else None,
        accepted=exists,
    )


# ---------------------------------------------------------------------------
# Scene-plan helpers
# ---------------------------------------------------------------------------

def _plan_by_index(
    context: SceneContext,
) -> dict[int, Any]:
    return {
        int(entry.index): entry
        for entry in context.scene_plan
    }


def _plan_by_stem(
    context: SceneContext,
) -> dict[str, Any]:
    return {
        str(entry.stem): entry
        for entry in context.scene_plan
    }


def _build_script(
    context: SceneContext,
):
    """Create the canonical Script consumed by the generator.

    The raw prompt is parsed, then filtered and enriched using the already
    validated scene plan. The scene plan therefore remains the authoritative
    scope for this stage.
    """

    script = parse_script(
        context.prompt
    )

    allowed_indices = {
        int(entry.index)
        for entry in context.scene_plan
    }

    plan = _plan_by_index(context)

    sections = []

    for section in script.sections:

        if int(section.index) not in allowed_indices:
            continue

        entry = plan.get(
            int(section.index)
        )

        if entry is None:
            continue

        # Inject the harness-controlled animation brief.
        section.anim = entry.anim

        sections.append(section)

    script.sections = sections

    return script


# ---------------------------------------------------------------------------
# Repair feedback
# ---------------------------------------------------------------------------

def _repair_feedback(
    context: SceneContext,
    stem: str,
) -> str:
    """Convert accumulated repair diagnostics into bounded feedback."""

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

    text = (
        "\n\nPRIOR REPAIR FEEDBACK:\n"
        + "\n".join(
            f"- {message}"
            for message in clean
        )
    )

    # Prevent pathological feedback growth.
    return text[-MAX_REPAIR_FEEDBACK:]


def _harness_feedback(
    findings: list[dict[str, Any]],
) -> str:
    """Convert harness check findings into LLM-facing repair feedback."""

    messages = [
        str(finding.get("detail") or finding.get("message") or "").strip()
        for finding in findings
        if isinstance(finding, dict)
    ]

    clean = [message for message in messages if message]

    if not clean:
        return ""

    text = (
        "\n\nYour previous answer was rejected by the harness's own "
        "syntax/quality check. Return the whole corrected module.\n\n"
        "HARNESS CHECK PROBLEMS:\n"
        + "\n".join(f"- {message}" for message in clean)
    )

    return text[-MAX_REPAIR_FEEDBACK:]


# ---------------------------------------------------------------------------
# Per-scene generation + immediate harness check
# ---------------------------------------------------------------------------

def _generate_and_check_one(
    context: SceneContext,
    script,
    index: int,
    stem: str,
    retries: int,
) -> None:
    """Generate one scene, then send it to the harness immediately.

    Regenerates the same scene up to ``MAX_HARNESS_CHECK_RETRIES`` extra
    times when the harness's own check (``verifier_execution``'s
    deterministic source check) reports a blocking failure. If it still
    fails after that, the failure is logged to
    ``context.check_results["generator_code:preflight"]`` and generation
    proceeds to the next scene — the end-of-batch ``verifier_execution``
    stage remains the authoritative gate, so this never hard-stops the run.
    """

    entry = next(
        (e for e in context.scene_plan if e.stem == stem),
        None,
    )

    if entry is None:
        raise KeyError(f"Unknown scene stem: {stem}")

    extra_feedback = _repair_feedback(context, stem)

    attempt = 0

    while True:
        generate(
            context.project_dir,
            script,
            index,
            retries=retries,
            extra_feedback=extra_feedback,
        )

        _record_artifact(context, stem)

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
                "generator_code:preflight", []
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
        extra_feedback = _repair_feedback(context, stem) + _harness_feedback(
            blocking
        )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _remove_scene_artifacts(
    context: SceneContext,
    stem: str,
) -> None:
    """Remove artifacts that would cause generate() to silently skip."""

    path = scene_path(
        context.project_dir,
        stem,
    )

    path.unlink(
        missing_ok=True
    )

    # Keep in-memory state consistent.
    context.code_artifacts.pop(
        stem,
        None,
    )

    context.render_artifacts.pop(
        stem,
        None,
    )


# ---------------------------------------------------------------------------
# Main plugin
# ---------------------------------------------------------------------------

class GeneratorCodePlugin(Plugin):
    """Generate executable scene code from the verified storyboard."""

    name = "generator_code"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "narration",
            "storyboard_verified",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "code_artifacts",
        ]

    def _assert_prerequisites(
        self,
        context: SceneContext,
    ) -> None:
        """Fail closed if upstream quality gates are missing."""

        if not getattr(
            context,
            "pedagogy_verified",
            False,
        ):
            raise RuntimeError(
                "GeneratorCodePlugin requires "
                "pedagogy_verified=True."
            )

        if not getattr(
            context,
            "storyboard_verified",
            False,
        ):
            raise RuntimeError(
                "GeneratorCodePlugin requires "
                "storyboard_verified=True."
            )

        if not context.scene_plan:
            raise RuntimeError(
                "GeneratorCodePlugin received an empty scene plan."
            )

    def _retries(self) -> int:
        return _safe_int(
            self.config.get(
                "retries",
                0,
            ),
            default=0,
        )

    def _jobs(self) -> int | None:
        value = self.config.get(
            "jobs"
        )

        if value in (
            None,
            "",
            0,
            "0",
        ):
            return None

        return _safe_int(
            value,
            default=1,
            minimum=1,
        )

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        self._assert_prerequisites(
            context
        )

        _ensure_llm_keys()

        script = _build_script(
            context
        )

        retries = self._retries()
        jobs = self._jobs()

        todo = []
        for section in script.sections:
            dst = scene_path(context.project_dir, section.stem)
            # dst.exists() alone isn't "done" — see scenes.generate_all()'s
            # own comment; is_current() requires the audit-backed manifest.
            if is_current(dst, stills_dir(context.project_dir, section.stem)):
                cfg.say(
                    f"section {section.stem}: scene already written, "
                    "skipping (delete it to regenerate)"
                )
                _record_artifact(context, section.stem)
                continue
            todo.append(section)

        if not todo:
            return context

        continuity = os.environ.get(
            "P2R_CONTINUITY", "1"
        ).strip().lower() not in {"0", "false", "off", "no"}

        n = jobs or default_jobs(len(todo))
        # Continuity means each section's prompt anchors on the previous
        # section's generated code, so concurrent generation would race —
        # keep it serial, exactly as generate_all() does today.
        if continuity:
            n = 1

        if n <= 1 or len(todo) == 1:
            for section in todo:
                _generate_and_check_one(
                    context,
                    script,
                    section.index,
                    section.stem,
                    retries,
                )
        else:
            cfg.say(f"storyboarding {len(todo)} sections, {n} at a time")
            with ThreadPoolExecutor(max_workers=n) as pool:
                futures = [
                    pool.submit(
                        _generate_and_check_one,
                        context,
                        script,
                        section.index,
                        section.stem,
                        retries,
                    )
                    for section in todo
                ]
                try:
                    for fut in as_completed(futures):
                        fut.result()
                except BaseException:
                    for f in futures:
                        f.cancel()
                    raise

        return context

    # ------------------------------------------------------------------
    # repair_router hooks
    # ------------------------------------------------------------------

    def revert_scene(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Remove exactly one generated scene so regeneration cannot no-op."""

        plan = _plan_by_stem(
            context
        )

        if stem not in plan:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        _remove_scene_artifacts(
            context,
            stem,
        )

    def regenerate_one(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Regenerate exactly one scene with accumulated repair feedback."""

        self._assert_prerequisites(
            context
        )

        _ensure_llm_keys()

        plan = _plan_by_stem(
            context
        )

        entry = plan.get(
            stem
        )

        if entry is None:
            raise KeyError(
                f"Unknown scene stem: {stem}"
            )

        script = _build_script(
            context
        )

        section = next(
            (
                section
                for section in script.sections
                if section.stem == stem
            ),
            None,
        )

        if section is None:
            raise ValueError(
                f"Scene '{stem}' is not present "
                "in the current script."
            )

        # The scene plan is authoritative.
        section.anim = entry.anim

        extra_feedback = _repair_feedback(
            context,
            stem,
        )

        retries = self._retries()

        generate(
            context.project_dir,
            script,
            section.index,
            retries=retries,
            extra_feedback=extra_feedback,
        )

        # --------------------------------------------------------------
        # Postcondition
        # --------------------------------------------------------------

        path = scene_path(
            context.project_dir,
            stem,
        )

        if not path.exists():
            raise RuntimeError(
                f"Scene generation failed: "
                f"{path} was not created."
            )

        _record_artifact(
            context,
            stem,
        )

        # Send the repaired scene straight to the harness, same as a
        # freshly generated one — the repair_router's caller (the runner)
        # re-runs the originating verifier afterward regardless, but this
        # gives an immediate, logged signal rather than waiting for that.
        findings = check_scene_artifact(context, entry, gate=True)
        if any(
            isinstance(f, dict) and str(f.get("status", "")).lower() == "fail"
            for f in findings
        ):
            log = context.check_results.setdefault(
                "generator_code:preflight", []
            )
            log.extend(findings)