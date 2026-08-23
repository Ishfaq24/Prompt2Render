"""Coder role for Prompt2Render.

This plugin is the boundary between planning and executable scene generation.

Responsibilities
----------------
1. Consume the verified scene plan and storyboard.
2. Delegate actual code generation to ``scenes.generate_all`` / ``scenes.generate``.
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
from pathlib import Path
from typing import Any

from ...context import CodeArtifact, SceneContext
from ...plugin import Plugin
from ....project import parse_script
from ....scenes import generate_all
from ....stills import scene_path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REPAIR_FEEDBACK = 6000


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

        # Existing generate_all() remains the actual coder.
        generate_all(
            context.project_dir,
            script,
            retries=retries,
            jobs=jobs,
        )

        # Synchronise artifact state.
        for entry in context.scene_plan:
            _record_artifact(
                context,
                entry.stem,
            )

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

        from ....scenes import generate

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