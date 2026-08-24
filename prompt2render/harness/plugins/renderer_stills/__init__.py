"""Still-frame renderer for the Prompt2Render SceneKit pipeline.

This plugin wraps ``stills.render_many`` and remains the actual live still
renderer.

Responsibilities
----------------
1. Render stills for accepted scene-code artifacts.
2. Reuse current stills when the scene source has not changed.
3. Support forced regeneration.
4. Preserve per-scene render artifacts and audit information.
5. Emit blocking render findings when still generation fails.
6. Render only affected scenes during repair cycles.
7. Keep generation/acceptance separate from rendering.

The normal pipeline is:

    CodeArtifact
        ↓
    RendererStillsPlugin
        ↓
    RenderArtifact
        ↓
    Spatial / Visual verification
        ↓
    final acceptance
"""

from __future__ import annotations

from typing import Any

from ...context import RenderArtifact, SceneContext
from ...plugin import Plugin
from .... import align, stills


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _as_bool(
    value: Any,
    default: bool = False,
) -> bool:
    """Safely parse boolean configuration.

    Avoids the common Python pitfall:

        bool("false") == True
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "n",
            "off",
        }:
            return False

    return default


def _safe_jobs(value: Any) -> int | None:
    """Normalize worker count."""

    if value in (
        None,
        "",
        0,
        "0",
    ):
        return None

    try:
        workers = int(value)
    except (TypeError, ValueError):
        return None

    return max(1, workers)


# ---------------------------------------------------------------------------
# Finding helper
# ---------------------------------------------------------------------------

def _record_render_failure(
    context: SceneContext,
    stem: str,
    error: Exception | str,
) -> None:
    """Record a blocking still-render failure for repair_router."""

    from ...finding import (
        Category,
        Finding,
        Severity,
        next_finding_id,
    )

    finding = Finding(
        finding_id=next_finding_id(
            "stills"
        ),
        scene_id=stem,
        category=Category.RENDER,
        severity=Severity.BLOCKING,
        message=(
            "Still rendering failed:\n"
            f"{error}"
        ),
    )

    result = finding.as_check_result()
    result["finding_type"] = "stills_render_failure"

    context.check_results.setdefault(
        "renderer_stills",
        [],
    ).append(result)


# ---------------------------------------------------------------------------
# Render-artifact helpers
# ---------------------------------------------------------------------------

def _manifest(
    context: SceneContext,
    stem: str,
    outdir,
) -> list:
    """Safely retrieve the current still manifest."""

    manifest_path = outdir / "manifest.json"

    if not manifest_path.exists():
        return []

    try:
        return stills.manifest(
            context.project_dir,
            stem,
        )
    except Exception:
        return []


def _audit(
    outdir,
):
    """Safely retrieve the still audit record."""

    try:
        return stills.audit_record(
            outdir
        )
    except Exception:
        return None


def _record_render_artifact(
    context: SceneContext,
    stem: str,
) -> None:
    """Synchronize RenderArtifact with the filesystem."""

    outdir = stills.stills_dir(
        context.project_dir,
        stem,
    )

    context.render_artifacts[stem] = (
        RenderArtifact(
            stem=stem,
            outdir=outdir,
            manifest=_manifest(
                context,
                stem,
                outdir,
            ),
            audit=_audit(outdir),
        )
    )


# ---------------------------------------------------------------------------
# Alignment helper
# ---------------------------------------------------------------------------

def _sentence_count(
    context: SceneContext,
    stem: str,
) -> int:
    """Return narration sentence count for a scene.

    Still generation needs the sentence count because the live still renderer
    expects the final sentence index rather than a count.
    """

    try:
        data = align.load(
            context.project_dir,
            stem,
        )

        sentences = data.get(
            "sentences",
            [],
        )

        if not isinstance(
            sentences,
            list,
        ):
            raise ValueError(
                "Alignment sentences is not a list."
            )

        return len(sentences)

    except Exception as exc:
        raise RuntimeError(
            f"Unable to load narration alignment "
            f"for scene {stem}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class RendererStillsPlugin(Plugin):
    """Render sentence-aligned still frames for generated SceneKit scenes."""

    name = "renderer_stills"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "render_artifacts",
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        force = _as_bool(
            self.config.get(
                "force",
                False,
            )
        )

        workers = _safe_jobs(
            self.config.get(
                "jobs"
            )
        )

        repair_context = getattr(
            context,
            "repair_context",
            {},
        )

        if not isinstance(
            repair_context,
            dict,
        ):
            repair_context = {}

        jobs: list[
            tuple
        ] = []

        stems: list[str] = []

        # ---------------------------------------------------------------
        # Determine which scenes need rendering.
        # ---------------------------------------------------------------

        for stem, artifact in list(
            context.code_artifacts.items()
        ):

            if not artifact.accepted:
                continue

            if artifact.path is None:
                continue

            if not artifact.path.exists():
                continue

            stems.append(stem)

            outdir = stills.stills_dir(
                context.project_dir,
                stem,
            )

            # A scene explicitly under repair must be regenerated even if
            # an old manifest still exists.
            is_repair = (
                stem in repair_context
            )

            if (
                not force
                and not is_repair
                and stills.is_current(
                    artifact.path,
                    outdir,
                )
            ):
                # Existing stills are current. Reconstruct the in-memory
                # RenderArtifact without doing expensive rendering.
                _record_render_artifact(
                    context,
                    stem,
                )
                continue

            try:
                sentence_count = _sentence_count(
                    context,
                    stem,
                )

                if sentence_count <= 0:
                    raise RuntimeError(
                        "Narration alignment contains "
                        "no sentences."
                    )

                # stills.render_many expects the final sentence index.
                last_sentence_index = (
                    sentence_count - 1
                )

                jobs.append(
                    (
                        stem,
                        artifact.path,
                        outdir,
                        last_sentence_index,
                    )
                )

            except Exception as exc:
                _record_render_failure(
                    context,
                    stem,
                    exc,
                )

                context.render_artifacts[
                    stem
                ] = RenderArtifact(
                    stem=stem,
                    outdir=outdir,
                    manifest=[],
                    audit=None,
                )

        # ---------------------------------------------------------------
        # Render all required scenes.
        # ---------------------------------------------------------------

        if jobs:

            try:
                stills.render_many(
                    jobs,
                    workers=workers,
                )

            except Exception as exc:
                # A batch-level failure may leave some scenes successfully
                # rendered and others incomplete. Inspect each scene below
                # rather than marking the whole batch uniformly.
                from .... import cfg

                cfg.warn(
                    "Still rendering batch failed: "
                    f"{exc}"
                )

                for stem, _, _, _ in jobs:
                    _record_render_failure(
                        context,
                        stem,
                        exc,
                    )

        # ---------------------------------------------------------------
        # Reconstruct RenderArtifacts from actual filesystem state.
        # ---------------------------------------------------------------

        for stem in stems:

            outdir = stills.stills_dir(
                context.project_dir,
                stem,
            )

            manifest_path = (
                outdir / "manifest.json"
            )

            manifest_exists = (
                manifest_path.exists()
            )

            manifest = (
                _manifest(
                    context,
                    stem,
                    outdir,
                )
                if manifest_exists
                else []
            )

            audit = _audit(
                outdir
            )

            # If this scene was requested for rendering but no manifest
            # appeared, it is a real rendering failure.
            was_requested = any(
                job[0] == stem
                for job in jobs
            )

            if (
                was_requested
                and not manifest_exists
            ):
                _record_render_failure(
                    context,
                    stem,
                    (
                        "Still renderer completed "
                        "without producing manifest.json."
                    ),
                )

            context.render_artifacts[
                stem
            ] = RenderArtifact(
                stem=stem,
                outdir=outdir,
                manifest=manifest,
                audit=audit,
            )

        return context

    def _default_gate(self) -> bool:
        """Rendering is not itself an upstream quality gate."""

        return False

    # ------------------------------------------------------------------
    # repair_router hooks
    # ------------------------------------------------------------------

    def revert_scene(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Invalidate one scene's still-render state.

        The actual scene source remains intact; only downstream still
        artifacts are invalidated. The next render cycle will regenerate them.
        """

        context.render_artifacts.pop(
            stem,
            None,
        )

    def regenerate_one(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Regenerate stills for exactly one scene."""

        artifact = context.code_artifacts.get(
            stem
        )

        if artifact is None:
            raise KeyError(
                f"No code artifact exists for scene '{stem}'."
            )

        if artifact.path is None:
            raise RuntimeError(
                f"Scene '{stem}' has no generated source file."
            )

        if not artifact.path.exists():
            raise RuntimeError(
                f"Scene source does not exist: "
                f"{artifact.path}"
            )

        outdir = stills.stills_dir(
            context.project_dir,
            stem,
        )

        try:
            sentence_count = _sentence_count(
                context,
                stem,
            )

            if sentence_count <= 0:
                raise RuntimeError(
                    "Narration alignment contains "
                    "no sentences."
                )

            job = (
                stem,
                artifact.path,
                outdir,
                sentence_count - 1,
            )

            stills.render_many(
                [job],
                workers=1,
            )

        except Exception as exc:
            _record_render_failure(
                context,
                stem,
                exc,
            )

            context.render_artifacts[
                stem
            ] = RenderArtifact(
                stem=stem,
                outdir=outdir,
                manifest=[],
                audit=None,
            )

            raise

        # ---------------------------------------------------------------
        # Postcondition
        # ---------------------------------------------------------------

        manifest_path = (
            outdir / "manifest.json"
        )

        if not manifest_path.exists():
            error = RuntimeError(
                f"Still regeneration for scene "
                f"'{stem}' completed without "
                "manifest.json."
            )

            _record_render_failure(
                context,
                stem,
                error,
            )

            context.render_artifacts[
                stem
            ] = RenderArtifact(
                stem=stem,
                outdir=outdir,
                manifest=[],
                audit=None,
            )

            raise error

        _record_render_artifact(
            context,
            stem,
        )