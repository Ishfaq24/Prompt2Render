"""Harness planning stages for narration and animation briefs.

Pipeline:

    prompt
      ↓
    PlannerScriptPlugin
      ↓
    scene_plan + pedagogy_verified
      ↓
    PlannerVisualPlugin
      ↓
    deterministic animation contract
      ↓
    animation_plan

Design goals
------------
1. Never overwrite user-authored narration unless explicitly forced.
2. Preserve immutable provenance of the original script.
3. Make planning idempotent.
4. Give every visual brief the same deterministic contract.
5. Fail early when pedagogical verification has not passed.
6. Validate scene briefs before handing them to the coder.
7. Keep the contract versioned and auditable.
8. Avoid additional LLM calls merely to normalize visual requirements.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from ..context import SceneContext
from ..plugin import Plugin
from ... import draft


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARNESS_DIR = "build/harness"
PROVENANCE_DIR = "build/harness/provenance"

SCRIPT_ORIGINAL = "script.original.md"
SCRIPT_PLANNED = "script.planned.md"

VISUAL_CONTRACT_VERSION = "1.0"

VISUAL_CONTRACT = """
HARNESS ANIMATION CONTRACT v1.0

VISUAL SEMANTICS
- State the visual claim represented by this section.
- State the exact values, labels, symbols, or relationships shown.
- Every displayed value must agree with the narration and source script.
- Never visually imply a relationship that the narration does not establish.

LAYOUT
- Title zone: y = 7.6..8.6
- Primary visual zone: y = 4.0..7.0
- Secondary visual zone: y = 1.5..3.5
- Caption zone: y = 0.85
- Keep major visual objects spatially separated.
- Avoid overlapping labels, diagrams, equations, and annotations.

CONTINUITY
- Persistent objects must retain their coordinates across adjacent sections.
- Persistent objects must retain identity and meaning across transitions.
- A transition must preserve values unless the narration explicitly changes them.
- Do not silently reset, duplicate, or relocate persistent state.

PROGRESSIVE REVEAL
- Introduce one major conceptual change at a time.
- Prefer progressive construction over displaying all major elements simultaneously.
- New objects should appear only when pedagogically justified.
- Avoid unrelated visual changes during a single narration sentence.

RULE DEMONSTRATIONS
- Illegal states must be represented physically as illegal states.
- Never relabel a legal state as illegal.
- Clearly distinguish valid and invalid configurations.
- Preserve the actual invariant being demonstrated.

TECHNICAL VALIDITY
- Use only documented SceneKit/Manim primitives available to the coder.
- Use valid constructor signatures and input shapes.
- Do not invent APIs, methods, classes, or parameters.
- Prefer deterministic geometry over implicit layout.

CODER CONTRACT
- The coder must implement the visual brief exactly.
- The coder must not reinterpret numerical values.
- The coder must not replace a specified visual relationship with an unrelated abstraction.
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _harness_dir(project_dir: Path) -> Path:
    path = project_dir / HARNESS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _provenance_dir(project_dir: Path) -> Path:
    path = project_dir / PROVENANCE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write_json(path: Path, value: Any) -> None:
    """Write JSON atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def _ensure_original_script(context: SceneContext) -> Path:
    """Preserve the user's original script exactly once."""

    target = _provenance_dir(context.project_dir) / SCRIPT_ORIGINAL

    if not target.exists():
        shutil.copyfile(context.prompt, target)

    return target


def _snapshot_planned_script(context: SceneContext) -> Path:
    """Save the script that actually enters downstream planning."""

    target = _provenance_dir(context.project_dir) / SCRIPT_PLANNED

    shutil.copyfile(context.prompt, target)

    return target


def _sha256(path: Path) -> str:
    """Return SHA-256 digest of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _as_bool(value: Any, default: bool = False) -> bool:
    """Parse booleans safely.

    Unlike bool("false"), this correctly interprets textual false values.
    """

    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "y", "on"}:
            return True

        if normalized in {"false", "0", "no", "n", "off"}:
            return False

    return default


def _contract_block() -> str:
    """Return the canonical deterministic animation contract."""

    return f"\n\n{VISUAL_CONTRACT}"


def _append_contract(anim: str) -> str:
    """Idempotently attach the visual contract."""

    anim = (anim or "").rstrip()

    marker = f"HARNESS ANIMATION CONTRACT v{VISUAL_CONTRACT_VERSION}"

    if marker in anim:
        return anim

    return f"{anim}{_contract_block()}".strip()


def _validate_scene_plan(context: SceneContext) -> list[str]:
    """Validate scene-plan invariants before visual planning."""

    errors: list[str] = []

    if not context.scene_plan:
        errors.append("Scene plan is empty.")

        return errors

    seen_indices: set[int] = set()

    for entry in context.scene_plan:

        index = getattr(entry, "index", None)
        stem = getattr(entry, "stem", None)
        title = getattr(entry, "title", None)
        anim = getattr(entry, "anim", None)

        if index is None:
            errors.append("Scene has no index.")

        elif index in seen_indices:
            errors.append(
                f"Duplicate scene index detected: {index}."
            )

        else:
            seen_indices.add(index)

        if not stem:
            errors.append(
                f"Scene {index} has no stem."
            )

        if not title:
            errors.append(
                f"Scene {index} has no title."
            )

        if anim is None:
            errors.append(
                f"Scene {index} has no animation brief."
            )

    return errors


def _save_animation_plan_metadata(
    context: SceneContext,
    *,
    scene_count: int,
    script_hash: str,
) -> None:
    """Persist deterministic metadata for downstream auditing."""

    metadata = {
        "contract_version": VISUAL_CONTRACT_VERSION,
        "scene_count": scene_count,
        "script_sha256": script_hash,
        "contract_sha256": hashlib.sha256(
            VISUAL_CONTRACT.encode("utf-8")
        ).hexdigest(),
    }

    _atomic_write_json(
        _harness_dir(context.project_dir) / "animation_plan.json",
        metadata,
    )


# ---------------------------------------------------------------------------
# Script Planner
# ---------------------------------------------------------------------------

class PlannerScriptPlugin(Plugin):
    """Prepare the canonical narration/script artifact."""

    name = "planner_script"

    def declare_dependencies(self) -> list[str]:
        return ["prompt"]

    def declare_effects(self) -> list[str]:
        return ["script_artifact"]

    def run(self, context: SceneContext) -> SceneContext:
        _ensure_original_script(context)

        force = _as_bool(
            self.config.get("force", False)
        )

        before_hash = _sha256(context.prompt)

        # Existing draft workflow remains the authority for narration
        # generation/revision.
        draft.draft(
            context.project_dir,
            force=force,
        )

        after_hash = _sha256(context.prompt)

        _snapshot_planned_script(context)

        # Record exactly what happened.
        _atomic_write_json(
            _harness_dir(context.project_dir)
            / "script_planning.json",
            {
                "stage": self.name,
                "force": force,
                "changed": before_hash != after_hash,
                "before_sha256": before_hash,
                "after_sha256": after_hash,
            },
        )

        return context

    def _default_gate(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Visual Planner
# ---------------------------------------------------------------------------

class PlannerVisualPlugin(Plugin):
    """Attach the deterministic visual contract to every scene."""

    name = "planner_visual"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "pedagogy_verified",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "animation_plan",
        ]

    def run(self, context: SceneContext) -> SceneContext:
        # ---------------------------------------------------------------
        # Hard pedagogical gate
        # ---------------------------------------------------------------

        if not getattr(
            context,
            "pedagogy_verified",
            False,
        ):
            raise RuntimeError(
                "PlannerVisualPlugin cannot run before "
                "pedagogy verification passes."
            )

        # ---------------------------------------------------------------
        # Validate scene-plan invariants
        # ---------------------------------------------------------------

        errors = _validate_scene_plan(context)

        if errors:
            raise ValueError(
                "Invalid scene plan:\n"
                + "\n".join(
                    f"- {error}"
                    for error in errors
                )
            )

        # ---------------------------------------------------------------
        # Deterministic contract injection
        # ---------------------------------------------------------------

        for entry in context.scene_plan:
            entry.anim = _append_contract(entry.anim)

        # ---------------------------------------------------------------
        # Validate the resulting briefs
        # ---------------------------------------------------------------

        contract_marker = (
            f"HARNESS ANIMATION CONTRACT v"
            f"{VISUAL_CONTRACT_VERSION}"
        )

        missing_contract = [
            entry.index
            for entry in context.scene_plan
            if contract_marker not in (entry.anim or "")
        ]

        if missing_contract:
            raise RuntimeError(
                "Visual contract missing from scenes: "
                + ", ".join(
                    map(str, missing_contract)
                )
            )

        # ---------------------------------------------------------------
        # Persist deterministic metadata
        # ---------------------------------------------------------------

        _save_animation_plan_metadata(
            context,
            scene_count=len(context.scene_plan),
            script_hash=_sha256(context.prompt),
        )

        return context

    def _default_gate(self) -> bool:
        return True