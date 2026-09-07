"""Deterministic pre-render verifier for generated scene modules.

This verifier is intentionally independent of an LLM.

For SceneKit modules it:
    1. Parses/validates the generated source.
    2. Validates documented SceneKit input contracts.
    3. Records literal ``k.*`` calls to a JSON trace.
    4. Emits deterministic blocking findings.

For Manim modules it:
    1. Detects the Manim backend conservatively.
    2. Runs the deterministic Manim source validator.
    3. Does not attempt SceneKit tracing.

This verifier does not prove arbitrary subject-matter correctness.
Semantic correctness belongs to a structured topic/profile verifier or an
optional semantic reviewer.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...motion import find_storyboard_states
from ...plugin import Plugin
from ...timing import narration_span
from ....scenes import (
    trace_scene_source,
    validate_scene_source,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_manim_source(
    source: str,
) -> bool:
    """Detect Manim source using syntax-aware checks where possible."""

    if source and source[0] == "\ufeff":
        source = source.lstrip("\ufeff")
    # Fast string fallback: if source clearly imports manim and defines
    # a Scene class, treat as Manim even if ast.parse fails due to a
    # transient syntax error (e.g. missing colon). This ensures the
    # validator reports a proper Manim syntax error instead of falling
    # through to the SceneKit trace path which then obscures the cause
    # as "invalid syntax line 4" trace failure.
    lower = source.lower()
    has_manim_import = "from manim import" in lower or "import manim" in lower
    has_scene = "class scene" in lower
    try:
        tree = ast.parse(
            source
        )
    except SyntaxError:
        # If it looks like Manim, claim Manim so validate_manim_source
        # reports the syntax error directly.
        if has_manim_import and has_scene:
            return True
        return False

    imports_manim = False
    defines_scene = False

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Import,
        ):
            if any(
                alias.name == "manim"
                or alias.name.startswith("manim.")
                for alias in node.names
            ):
                imports_manim = True

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module == "manim" or (
                node.module
                and node.module.startswith("manim.")
            ):
                imports_manim = True

        elif isinstance(
            node,
            ast.ClassDef,
        ):
            if node.name.startswith(
                "Scene"
            ):
                defines_scene = True

    return (
        imports_manim
        and defines_scene
    )


def _trace_path(
    artifact_path: Path,
) -> Path:
    return artifact_path.with_suffix(
        ".trace.json"
    )


def _finding(
    *,
    scene_id: str,
    message: str,
    finding_type: str,
    gate: bool,
) -> dict[str, Any]:
    """Create a normalized verifier finding."""

    result = Finding(
        finding_id=next_finding_id(
            "exec"
        ),
        scene_id=scene_id,
        category=Category.SEMANTIC,
        severity=(
            Severity.BLOCKING
            if gate
            else Severity.WARNING
        ),
        message=message,
    ).as_check_result()

    result["finding_type"] = finding_type

    return result


def _classify_manim_error(message: str) -> str:
    """Typed routing key for one deterministic Manim preflight error.

    Distinct types matter downstream: the repair router and the evidence
    layer map ``undefined_identifier`` to a code-local repair and
    ``invalid_manim_api`` to a Manim-API repair, instead of treating every
    static error as one undifferentiated execution failure.
    """

    text = str(message or "")

    if "is not defined" in text:
        return "undefined_identifier"

    if "does not exist" in text:
        return "undefined_method"

    if "does not accept" in text:
        return "invalid_manim_api"

    return "execution_failure"


def _safe_narration_cue(
    context: SceneContext,
    stem: str,
) -> int | None:
    """Return the maximum narration cue when available."""

    narration = getattr(
        context,
        "narration",
        {},
    ).get(
        stem
    )

    if not narration:
        return None

    sentences = getattr(
        narration,
        "sentences",
        None,
    )

    if not sentences:
        return None

    return len(sentences) - 1


def _storyboard_motion_by_state(
    context: SceneContext,
    stem: str,
    index: int | None = None,
) -> dict[str, list] | None:
    """Return {state name: motion list} for one storyboard section.

    ``None`` means the section itself could not be found (stem, and index
    when given, both missed) — distinct from a section that was found but
    whose states simply declare no motion.
    """

    states = find_storyboard_states(context, stem, index=index)

    if states is None:
        return None

    return {
        state.get("name"): state.get("motion", [])
        for state in states
        if isinstance(state, dict)
    }


def _safe_narration_duration(
    context: SceneContext,
    stem: str,
) -> float:
    """The section's wall-clock narration span, including inter-sentence
    silence.

    Delegates to ``harness.timing.narration_span`` so this, ``_load_timing``
    and ``verifier_temporal._target_duration`` cannot drift apart again --
    they previously disagreed, this one using the true end while the other
    two summed speech durations and silently dropped every gap.
    """

    narration = getattr(context, "narration", {}).get(stem)

    if not narration:
        return 0.0

    sentences = getattr(narration, "sentences", None)

    if not sentences:
        return 0.0

    return narration_span(sentences)


def _validate_asset_invocations(
    source: str,
    project_dir: Path | None,
) -> list[str]:
    """Validate asset calls (k.draw_asset, SVGMobject, custom Mobjects) for existence and parameter schema."""
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    try:
        from ....assets.loader import load_catalog
        catalog = load_catalog()
    except Exception:
        catalog = {}

    build_assets_dir = (project_dir / "build" / "assets") if project_dir else None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Case 1: k.draw_asset / k.animate_asset(ax, asset_id_or_path, ...)
        is_k_asset_call = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "k"
            and node.func.attr in ("draw_asset", "animate_asset")
        )
        is_direct_asset_call = (
            isinstance(node.func, ast.Name)
            and node.func.id in ("draw_asset", "animate_asset")
        )
        if is_k_asset_call or is_direct_asset_call:
            asset_arg = None
            if len(node.args) >= 2:
                asset_arg = node.args[1]
            elif len(node.args) == 1:
                asset_arg = node.args[0]
            for kw in node.keywords:
                if kw.arg in ("asset", "asset_id", "name"):
                    asset_arg = kw.value

            asset_val = None
            if asset_arg is not None:
                try:
                    asset_val = ast.literal_eval(asset_arg)
                except Exception:
                    pass

            if isinstance(asset_val, str):
                asset_def = catalog.get(asset_val)
                if asset_def is not None:
                    schema = asset_def.parameter_schema
                    if schema and "properties" in schema:
                        allowed_props = set(schema["properties"].keys())
                        required_props = set(schema.get("required", []))

                        provided_kwargs = {kw.arg for kw in node.keywords if kw.arg is not None}
                        pos_names = ["ax", "asset", "x", "y", "start_time", "duration", "scale", "width", "height", "color", "tint_color"]
                        for i, arg in enumerate(node.args):
                            if i < len(pos_names) and pos_names[i] not in ("ax", "asset"):
                                provided_kwargs.add(pos_names[i])

                        for req in required_props:
                            if req not in provided_kwargs:
                                errors.append(f"Missing required parameter '{req}' for asset '{asset_val}' (line {node.lineno})")

                        for kw in node.keywords:
                            if kw.arg and kw.arg not in allowed_props and kw.arg not in ("ax", "asset", "zorder", "alpha", "loop", "width", "height"):
                                errors.append(f"Unknown parameter '{kw.arg}' for asset '{asset_val}' (line {node.lineno})")
                else:
                    if build_assets_dir:
                        candidate = build_assets_dir / Path(asset_val).name
                        if not candidate.is_file() and not (project_dir and (project_dir / asset_val).is_file()):
                            errors.append(f"Asset file '{asset_val}' does not exist on disk (line {node.lineno})")

        # Case 2: SVGMobject("assets/...") or P2RSVGMobject("assets/...")
        is_svg_mobject = (
            isinstance(node.func, ast.Name) and node.func.id in ("SVGMobject", "P2RSVGMobject")
        ) or (
            isinstance(node.func, ast.Attribute) and node.func.attr in ("SVGMobject", "P2RSVGMobject")
        )
        if is_svg_mobject and node.args:
            path_arg = node.args[0]
            try:
                path_val = ast.literal_eval(path_arg)
                if isinstance(path_val, str) and (path_val.endswith(".svg") or "assets" in path_val):
                    if build_assets_dir:
                        cand1 = build_assets_dir / Path(path_val).name
                        cand2 = (project_dir / path_val) if project_dir else None
                        if not cand1.is_file() and not (cand2 and cand2.is_file()):
                            errors.append(f"SVGMobject asset file '{path_val}' not found in build/assets (line {node.lineno})")
            except Exception:
                pass

        # Case 3: Instantiation of Parametric Mobject from catalog
        mobject_class_name = None
        if isinstance(node.func, ast.Name):
            mobject_class_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            mobject_class_name = node.func.attr

        if mobject_class_name:
            for asset_def in catalog.values():
                if asset_def.class_name == mobject_class_name:
                    schema = asset_def.parameter_schema
                    if schema and "properties" in schema:
                        allowed_props = set(schema["properties"].keys())
                        for kw in node.keywords:
                            if kw.arg and kw.arg not in allowed_props and kw.arg not in ("color", "z_index", "stroke_color", "fill_color"):
                                errors.append(f"Unknown parameter '{kw.arg}' for Mobject '{mobject_class_name}' (line {node.lineno})")
                    break

    return errors


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

def check_scene_artifact(
    context: SceneContext,
    entry: Any,
    *,
    gate: bool,
) -> list[dict[str, Any]]:
    """Run the deterministic pre-render execution/source check on one scene.

    This is the same logic ``VerifierExecutionPlugin.run()`` applies to every
    entry in ``context.scene_plan``, extracted so ``generator_code`` can send
    a scene straight to the harness the instant its file is written, rather
    than waiting for the batch verifier stage to run over every scene at once.
    """

    findings: list[dict[str, Any]] = []

    artifact = context.code_artifacts.get(entry.stem)

    # ----------------------------------------------------------
    # Missing generated artifact
    # ----------------------------------------------------------

    if (
        artifact is None
        or artifact.path is None
        or not artifact.path.exists()
    ):
        findings.append(
            _finding(
                scene_id=entry.stem,
                message=(
                    "PRE-FLIGHT EXECUTION CHECK: "
                    "generated scene artifact is missing."
                ),
                finding_type="execution_failure",
                gate=gate,
            )
        )

        return findings

    artifact_path = artifact.path

    # ----------------------------------------------------------
    # Read source
    # ----------------------------------------------------------

    try:
        source = artifact_path.read_text(
            encoding="utf-8"
        )
        # Strip BOM / zero-width that PowerShell or LLM may inject
        # (U+FEFF) which makes ast.parse raise SyntaxError and
        # forces a false SceneKit path that then fails trace.
        if source and source[0] == "\ufeff":
            source = source.lstrip("\ufeff").lstrip()
            # persist clean file so next run doesn't re-hit
            try:
                artifact_path.write_text(source, encoding="utf-8")
            except Exception:
                pass
    except Exception as exc:
        findings.append(
            _finding(
                scene_id=entry.stem,
                message=(
                    "PRE-FLIGHT EXECUTION CHECK: "
                    f"could not read generated source: {exc}"
                ),
                finding_type="execution_failure",
                gate=gate,
            )
        )

        return findings

    if not source.strip():
        findings.append(
            _finding(
                scene_id=entry.stem,
                message=(
                    "PRE-FLIGHT EXECUTION CHECK: "
                    "generated source file is empty."
                ),
                finding_type="execution_failure",
                gate=gate,
            )
        )

        return findings

    # ----------------------------------------------------------
    # Backend detection
    # ----------------------------------------------------------

    is_manim = _is_manim_source(
        source
    )

    # ----------------------------------------------------------
    # Manim validation
    # ----------------------------------------------------------

    if is_manim:

        try:
            from ....scenes import (
                validate_manim_source,
            )

            errors = list(
                validate_manim_source(
                    source
                )
                or []
            )

        except Exception as exc:
            errors = [
                (
                    "Manim source validator failed: "
                    f"{exc}"
                )
            ]

        asset_errors = _validate_asset_invocations(source, context.project_dir)
        errors.extend(asset_errors)

        for message in errors:
            findings.append(
                _finding(
                    scene_id=entry.stem,
                    message=(
                        "PRE-FLIGHT EXECUTION CHECK: "
                        f"{message}"
                    ),
                    finding_type=_classify_manim_error(message),
                    gate=gate,
                )
            )

        # Manim source is intentionally not sent through the
        # SceneKit primitive tracer.
        return findings

    # ----------------------------------------------------------
    # SceneKit validation
    # ----------------------------------------------------------

    max_cue = _safe_narration_cue(
        context,
        entry.stem,
    )

    try:
        errors = list(
            validate_scene_source(
                source,
                max_cue=max_cue,
            )
            or []
        )
        asset_errors = _validate_asset_invocations(source, context.project_dir)
        errors.extend(asset_errors)
    except Exception as exc:
        errors = [
            (
                "SceneKit source validator failed: "
                f"{exc}"
            )
        ]

    for message in errors:
        findings.append(
            _finding(
                scene_id=entry.stem,
                message=(
                    "PRE-FLIGHT EXECUTION CHECK: "
                    f"{message}"
                ),
                finding_type=(
                    "execution_failure"
                ),
                gate=gate,
            )
        )

    # ----------------------------------------------------------
    # Deterministic SceneKit trace
    # ----------------------------------------------------------

    try:
        trace = trace_scene_source(
            source
        )

        if not isinstance(
            trace,
            dict,
        ):
            raise TypeError(
                "trace_scene_source() "
                "did not return a dictionary."
            )

        trace["stem"] = (
            entry.stem
        )
        trace["source"] = str(
            artifact_path
        )
        trace["valid"] = not bool(
            errors
        )
        trace["backend"] = (
            "scenekit"
        )

        trace_path = _trace_path(
            artifact_path
        )

        trace_path.write_text(
            json.dumps(
                trace,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:
        findings.append(
            _finding(
                scene_id=entry.stem,
                message=(
                    "PRE-FLIGHT EXECUTION CHECK: "
                    "could not write deterministic "
                    f"SceneKit trace: {exc}"
                ),
                finding_type=(
                    "execution_trace_failure"
                ),
                gate=gate,
            )
        )

    return findings


class VerifierExecutionPlugin(Plugin):
    """Deterministic pre-render execution/source verifier."""

    name = "verifier_execution"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
            "static_code_verified",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        findings: list[dict[str, Any]] = []

        gate = self.is_gate()

        for entry in context.scene_plan:
            findings.extend(
                check_scene_artifact(
                    context,
                    entry,
                    gate=gate,
                )
            )

        # --------------------------------------------------------------
        # Publish result
        # --------------------------------------------------------------

        context.check_results[
            self.name
        ] = findings

        # Explicitly expose the aggregate result. This is informational;
        # acceptance remains the responsibility of downstream verification.
        context.static_code_verified = not any(
            finding.get("status") == "fail"
            for finding in findings
        )

        return context

    def _default_gate(self) -> bool:
        """Static source validation is a hard pre-render gate."""

        return True