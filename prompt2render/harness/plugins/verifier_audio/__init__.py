"""Whole-video audio/caption-drift verifier.

This plugin wraps ``qc.caption_drift`` and deliberately operates on the
finished, muxed ``out/final.mp4`` rather than individual scene artifacts.

It is therefore a post-finish quality check:

    renderer_finish
        ↓
    out/final.mp4
        ↓
    independent ASR
        ↓
    qc.caption_drift()
        ↓
    PASS / WARN / FAIL

Important design constraints
----------------------------
* It does not attempt per-scene repair.
* It does not manufacture an audio verdict when the final video is missing.
* Missing final-video or ASR prerequisites are reported as ``skip``.
* The underlying ``qc.caption_drift`` implementation remains authoritative.
* Any real caption-drift failure is exposed using the harness finding taxonomy
  so future routing can distinguish audio problems from code/visual problems.
* The verifier itself is a soft/post-finish gate; ``repair_router`` cannot
  directly regenerate a scene from this whole-video result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...plugin import Plugin
from .... import asrmodel, qc
from ....project import parse_script


class VerifierAudioPlugin(Plugin):
    """Run the independent whole-video caption-drift verification."""

    name = "verifier_audio"

    def declare_dependencies(self) -> list[str]:
        return [
            "final_video",
            "narration",
            "render_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _final_video(
        context: SceneContext,
    ) -> Path:
        return (
            context.project_dir
            / "out"
            / "final.mp4"
        )

    @staticmethod
    def _skip(
        context: SceneContext,
        detail: str,
        finding_type: str,
    ) -> SceneContext:
        """Record an explicit prerequisite skip."""

        context.check_results[
            VerifierAudioPlugin.name
        ] = [
            {
                "status": "skip",
                "finding_type": finding_type,
                "detail": detail,
                "scope": "video",
                "repairable_per_scene": False,
            }
        ]

        return context

    @staticmethod
    def _normalize_result(
        result: Any,
    ) -> dict[str, Any]:
        """Normalize qc.caption_drift output without changing its semantics."""

        if isinstance(
            result,
            dict,
        ):
            normalized = dict(result)
        else:
            normalized = {
                "status": "fail",
                "detail": str(result),
            }

        status = str(
            normalized.get(
                "status",
                "fail",
            )
        ).lower()

        if status not in {
            "pass",
            "warn",
            "fail",
            "skip",
        }:
            status = "fail"

        normalized["status"] = status
        normalized.setdefault(
            "finding_type",
            "audio_visual_mismatch",
        )
        normalized.setdefault(
            "scope",
            "video",
        )
        normalized.setdefault(
            "repairable_per_scene",
            False,
        )

        # Preserve the audio-specific mismatch information when qc supplies
        # it. Otherwise classify a non-pass caption-drift result as an
        # unclear audio/visual mismatch. This gives routing_policy enough
        # information without inventing a more specific diagnosis.
        if (
            status in {"warn", "fail"}
            and normalized.get(
                "finding_type"
            ) == "audio_visual_mismatch"
        ):
            normalized.setdefault(
                "mismatch_subtype",
                "unclear",
            )

        return normalized

    # ------------------------------------------------------------------
    # Main verifier
    # ------------------------------------------------------------------

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:
        final = self._final_video(
            context
        )

        # qc.caption_drift() requires the finished muxed video. This is a
        # prerequisite skip, not a quality failure.
        if not final.exists():
            return self._skip(
                context,
                (
                    "no out/final.mp4 after "
                    "renderer_finish"
                ),
                "missing_final_video",
            )

        if not final.is_file():
            return self._skip(
                context,
                (
                    "out/final.mp4 exists but is "
                    "not a regular file"
                ),
                "invalid_final_video",
            )

        # ASR availability is another prerequisite. Do not convert an
        # unavailable verification dependency into a false quality failure.
        try:
            model = asrmodel.available()
        except Exception as exc:
            return self._skip(
                context,
                f"ASR availability check failed: {exc}",
                "asr_unavailable",
            )

        if model is None:
            return self._skip(
                context,
                (
                    "no ASR model — cannot verify "
                    "caption drift independently"
                ),
                "asr_unavailable",
            )

        # Parse the authoritative source script exactly once for this
        # verification. qc.caption_drift remains responsible for the actual
        # cached transcription/drift analysis.
        try:
            script = parse_script(
                context.prompt
            )

            result = qc.caption_drift(
                context.project_dir,
                script,
                final,
                model,
            )

        except SystemExit as exc:
            # Some legacy prompt2render utilities use SystemExit for missing
            # runtime prerequisites. Treat this as a verifier failure only
            # when the final video and ASR model were already established.
            result = {
                "status": "fail",
                "finding_type": "audio_verification_failure",
                "detail": str(exc),
                "scope": "video",
                "repairable_per_scene": False,
            }

        except Exception as exc:
            result = {
                "status": "fail",
                "finding_type": "audio_verification_failure",
                "detail": (
                    "caption-drift verification failed: "
                    f"{exc}"
                ),
                "scope": "video",
                "repairable_per_scene": False,
            }

        normalized = self._normalize_result(
            result
        )

        context.check_results[
            self.name
        ] = [
            normalized
        ]

        return context

    def _default_gate(self) -> bool:
        """This is a post-finish whole-video verifier, not a pipeline gate."""

        return False