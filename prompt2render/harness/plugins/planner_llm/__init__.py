"""Video-level LLM storyboard planner.

This stage performs ONE LLM planning request per video rather than one
request per scene.

Responsibilities
----------------
1. Convert the pedagogically validated scene plan into a structured storyboard.
2. Preserve exact claims and numerical values from the source material.
3. Generate progressive visual states for every section.
4. Enforce deterministic structural invariants after the LLM response.
5. Persist an auditable storyboard artifact and provenance.
6. Support targeted section repair without permanently mutating the source
   animation brief.
7. Keep the storyboard separate from the original animation brief.

Pipeline

    scene_plan
        +
    pedagogy_verified
        ↓
    PlannerLlmPlugin
        ↓
    storyboard_plan
        ↓
    StoryboardVerifier
        ↓
    Scene Coder
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...plugin import Plugin
from .... import cfg, llm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARNESS_DIR = "build/harness"
PROVENANCE_DIR = "build/harness/provenance"

STORYBOARD_FILE = "storyboard.json"
STORYBOARD_PROMPT_FILE = "storyboard.prompt.txt"

STORYBOARD_VERSION = "2.0"

MIN_STATES = 2
MAX_STATES = 6

DEFAULT_MODEL = "gemini-3.5-flash-lite"


# ---------------------------------------------------------------------------
# Deterministic helpers
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
    """Atomically persist JSON."""

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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response.

    Handles:
    - plain JSON
    - fenced JSON
    - JSON surrounded by accidental prose
    """

    if not isinstance(text, str):
        return None

    text = text.strip()

    if not text:
        return None

    # Remove markdown fences.
    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    # Fast path.
    try:
        value = json.loads(text)

        return value if isinstance(value, dict) else None

    except json.JSONDecodeError:
        pass

    # Recovery path.
    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        return None

    try:
        value = json.loads(
            text[start:end + 1]
        )

        return value if isinstance(value, dict) else None

    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback(entry: Any) -> dict[str, Any]:
    """Generate a deterministic storyboard for one section."""

    narration = (
        getattr(entry, "narration_text", "")
        or ""
    ).strip()

    first_sentence = (
        narration.split(".", 1)[0].strip()
        if narration
        else ""
    )

    claim = first_sentence or (
        getattr(entry, "title", None)
        or "Explain the concept."
    )

    return {
        "index": entry.index,
        "title": entry.title,
        "claim": claim,
        "states": [
            {
                "name": "introduce",
                "cue": 0,
                "visual": entry.anim or "Introduce the concept.",
                "values": [],
                "transition": "progressive reveal",
            },
            {
                "name": "explain",
                "cue": 0,
                "visual": entry.anim or "Explain the concept.",
                "values": [],
                "transition": "preserve established state",
            },
        ],
        "source": "deterministic-fallback",
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _normalise_state(
    state: Any,
    entry: Any,
) -> dict[str, Any]:
    """Normalise a single storyboard state."""

    if not isinstance(state, dict):
        state = {}

    values = state.get("values", [])

    if not isinstance(values, list):
        values = []

    return {
        "name": str(
            state.get("name")
            or "state"
        ),

        "cue": _normalise_cue(
            state.get("cue", 0)
        ),

        "visual": str(
            state.get("visual")
            or entry.anim
            or ""
        ),

        "values": values,

        "transition": str(
            state.get("transition")
            or "progressive reveal"
        ),
    }


def _normalise_cue(value: Any) -> int:
    """Convert a cue to a safe non-negative integer."""

    try:
        return max(0, int(value))
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _normalise_section(
    item: Any,
    entry: Any,
    source: str,
) -> dict[str, Any]:
    """Normalise one LLM storyboard section."""

    if not isinstance(item, dict):
        item = {}

    raw_states = item.get("states", [])

    if not isinstance(raw_states, list):
        raw_states = []

    states = [
        _normalise_state(
            state,
            entry,
        )
        for state in raw_states
    ]

    # Enforce minimum state count.
    if len(states) < MIN_STATES:
        fallback = _fallback(entry)["states"]

        for state in fallback:
            if len(states) >= MIN_STATES:
                break

            states.append(state)

    # Enforce maximum state count.
    states = states[:MAX_STATES]

    return {
        "index": entry.index,
        "stem": entry.stem,
        "title": str(
            item.get("title")
            or entry.title
        ),
        "claim": str(
            item.get("claim")
            or entry.title
        ),
        "states": states,
        "source": source,
    }


def _validate_sections(
    entries: list[Any],
    sections: list[dict[str, Any]],
) -> list[str]:
    """Validate storyboard coverage and structural invariants."""

    errors: list[str] = []

    expected = [
        int(entry.index)
        for entry in entries
    ]

    actual = [
        int(section.get("index"))
        for section in sections
        if section.get("index") is not None
    ]

    # Every source section must appear exactly once.
    if sorted(actual) != sorted(expected):
        errors.append(
            "Storyboard section coverage mismatch: "
            f"expected={expected}, actual={actual}"
        )

    if len(actual) != len(set(actual)):
        errors.append(
            "Storyboard contains duplicate section indices."
        )

    for section in sections:
        index = section.get("index")

        states = section.get("states")

        if not isinstance(states, list):
            errors.append(
                f"Section {index}: states is not a list."
            )
            continue

        if not (
            MIN_STATES
            <= len(states)
            <= MAX_STATES
        ):
            errors.append(
                f"Section {index}: invalid state count "
                f"{len(states)}."
            )

        for state_no, state in enumerate(states):
            if not isinstance(state, dict):
                errors.append(
                    f"Section {index}, state {state_no}: "
                    "invalid state."
                )
                continue

            if not state.get("visual"):
                errors.append(
                    f"Section {index}, state {state_no}: "
                    "missing visual."
                )

            if not isinstance(
                state.get("values"),
                list,
            ):
                errors.append(
                    f"Section {index}, state {state_no}: "
                    "values must be a list."
                )

    return errors


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(
    payload: list[dict[str, Any]],
    repair_feedback: dict[str, list[str]] | None = None,
) -> str:
    """Construct the single video-level storyboard request."""

    repair_feedback = repair_feedback or {}

    repair_text = ""

    if repair_feedback:
        repair_text = (
            "\n\nTARGETED REPAIR FEEDBACK:\n"
            + json.dumps(
                repair_feedback,
                ensure_ascii=False,
                indent=2,
            )
        )

    return f"""
You are the storyboard director for an educational video.

Your task is to create ONE coherent storyboard for the COMPLETE video.

This is not a script-writing task.

Do not rewrite the narration.
Do not invent facts.
Do not invent numerical values.
Do not change mathematical relationships.
Do not introduce claims unsupported by the supplied material.

For EVERY section:

1. Preserve the section's teaching claim.
2. Create {MIN_STATES}-{MAX_STATES} progressive visual states.
3. Each state must correspond to a meaningful pedagogical step.
4. `cue` is the zero-based narration sentence index where the state
   should appear or change.
5. `visual` must describe exactly what should be visible.
6. `values` must contain only values explicitly present or directly
   derivable from the source.
7. `transition` describes how the previous state becomes the current state.
8. Maintain continuity of persistent objects.
9. Do not reset state between sections unless the narration requires it.
10. Follow the existing animation brief as a hard constraint.
11. Avoid visual decoration that does not teach something.
12. Prefer progressive construction over simultaneous presentation.

IMPORTANT:

The animation brief is authoritative for implementation constraints.

The storyboard adds explicit state semantics.

Return ONLY valid JSON.

Schema:

{{
  "sections": [
    {{
      "index": 1,
      "title": "...",
      "claim": "...",
      "states": [
        {{
          "name": "...",
          "cue": 0,
          "visual": "...",
          "values": [],
          "transition": "..."
        }}
      ]
    }}
  ]
}}

SECTIONS:

{json.dumps(
    payload,
    ensure_ascii=False,
    indent=2,
)}
{repair_text}
""".strip()


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class PlannerLlmPlugin(Plugin):
    """Generate a single coherent storyboard for the entire video."""

    name = "planner_llm"

    def declare_dependencies(self) -> list[str]:
        return [
            "scene_plan",
            "pedagogy_verified",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "storyboard_plan",
        ]

    def _repair_feedback(
        self,
        context: SceneContext,
    ) -> dict[str, list[str]]:
        """Extract repair feedback without mutating the scene plan."""

        feedback = getattr(
            context,
            "repair_context",
            {},
        )

        if not isinstance(feedback, dict):
            return {}

        return {
            str(stem): [
                str(message)
                for message in messages
            ]
            for stem, messages in feedback.items()
            if isinstance(messages, list)
        }

    def _build_payload(
        self,
        context: SceneContext,
    ) -> list[dict[str, Any]]:
        """Convert scene plans into the LLM input contract."""

        return [
            {
                "index": entry.index,
                "stem": entry.stem,
                "title": entry.title,
                "animation_brief": entry.anim,
                "narration": entry.narration_text,
            }
            for entry in context.scene_plan
        ]

    def _call_llm(
        self,
        prompt: str,
    ) -> dict[str, Any] | None:
        """Perform exactly one video-level LLM request."""

        if not llm.keys():
            return None

        model = os.environ.get(
            "P2R_STORYBOARD_MODEL",
            os.environ.get(
                "P2R_SCENE_MODEL",
                DEFAULT_MODEL,
            ),
        )

        response = llm.complete(
            prompt,
            max_tokens=6000,
            model_env="P2R_STORYBOARD_MODEL",
            default_model=model,
            label="storyboard",
        )

        return _extract_json(response)

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        # ---------------------------------------------------------------
        # Hard pedagogical gate
        # ---------------------------------------------------------------

        if not getattr(
            context,
            "pedagogy_verified",
            False,
        ):
            raise RuntimeError(
                "PlannerLlmPlugin requires "
                "pedagogy_verified=True."
            )

        entries = list(
            context.scene_plan
        )

        if not entries:
            raise ValueError(
                "Cannot generate storyboard: "
                "scene plan is empty."
            )

        payload = self._build_payload(
            context
        )

        repair_feedback = self._repair_feedback(
            context
        )

        prompt = _build_prompt(
            payload,
            repair_feedback,
        )

        # ---------------------------------------------------------------
        # Persist exact prompt for reproducibility
        # ---------------------------------------------------------------

        prompt_path = (
            _provenance_dir(context.project_dir)
            / STORYBOARD_PROMPT_FILE
        )

        prompt_path.write_text(
            prompt,
            encoding="utf-8",
        )

        storyboard_response = None
        llm_used = False

        try:
            storyboard_response = self._call_llm(
                prompt
            )

            if storyboard_response:
                llm_used = True

        except Exception as exc:
            cfg.warn(
                "Storyboard LLM unavailable; "
                f"using deterministic fallback: {exc}"
            )

        # ---------------------------------------------------------------
        # Index returned sections
        # ---------------------------------------------------------------

        returned_by_index: dict[int, dict[str, Any]] = {}

        if storyboard_response:
            raw_sections = storyboard_response.get(
                "sections",
                [],
            )

            if isinstance(raw_sections, list):
                for item in raw_sections:
                    if not isinstance(item, dict):
                        continue

                    try:
                        index = int(
                            item["index"]
                        )
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                    ):
                        continue

                    # First valid section wins.
                    if index not in returned_by_index:
                        returned_by_index[index] = item

        # ---------------------------------------------------------------
        # Normalise EVERY source section
        # ---------------------------------------------------------------

        normalized: list[dict[str, Any]] = []

        for entry in entries:

            raw = returned_by_index.get(
                int(entry.index)
            )

            if raw is None:
                normalized.append(
                    _fallback(entry)
                )
                continue

            normalized.append(
                _normalise_section(
                    raw,
                    entry,
                    "llm",
                )
            )

        # ---------------------------------------------------------------
        # Ensure deterministic ordering
        # ---------------------------------------------------------------

        normalized.sort(
            key=lambda section: int(
                section["index"]
            )
        )

        # ---------------------------------------------------------------
        # Validate
        # ---------------------------------------------------------------

        validation_errors = _validate_sections(
            entries,
            normalized,
        )

        # If the LLM produced a structurally invalid storyboard,
        # downgrade only invalid sections to deterministic fallback.
        if validation_errors:

            cfg.warn(
                "Storyboard structural validation "
                f"reported {len(validation_errors)} issue(s)."
            )

            repaired_sections = []

            for entry in entries:

                section = next(
                    (
                        item
                        for item in normalized
                        if item["index"] == entry.index
                    ),
                    None,
                )

                if section is None:
                    section = _fallback(entry)

                if not (
                    MIN_STATES
                    <= len(section.get("states", []))
                    <= MAX_STATES
                ):
                    section = _fallback(entry)

                repaired_sections.append(
                    section
                )

            normalized = repaired_sections

        # ---------------------------------------------------------------
        # Final storyboard artifact
        # ---------------------------------------------------------------

        source_counts = {
            "llm": sum(
                section["source"] == "llm"
                for section in normalized
            ),
            "deterministic-fallback": sum(
                section["source"]
                == "deterministic-fallback"
                for section in normalized
            ),
        }

        storyboard = {
            "version": STORYBOARD_VERSION,
            "source": (
                "llm"
                if llm_used
                else "deterministic-fallback"
            ),
            "llm_used": llm_used,
            "section_count": len(normalized),
            "source_counts": source_counts,
            "sections": normalized,
            "prompt_sha256": _sha256_text(
                prompt
            ),
        }

        context.storyboard_plan = storyboard

        # ---------------------------------------------------------------
        # Persist artifact
        # ---------------------------------------------------------------

        _atomic_write_json(
            _harness_dir(context.project_dir)
            / STORYBOARD_FILE,
            storyboard,
        )

        # ---------------------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT append the complete storyboard into entry.anim.
        #
        # Keep the source animation brief clean. The coder should receive
        # storyboard_plan as a separate structured input.
        # ---------------------------------------------------------------

        for entry in entries:
            entry.planned = True

        return context

    def _default_gate(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Repair router
    # ------------------------------------------------------------------

    def revert_scene(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Mark exactly one storyboard section for repair."""

        storyboard = getattr(
            context,
            "storyboard_plan",
            None,
        )

        if not isinstance(storyboard, dict):
            return

        for section in storyboard.get(
            "sections",
            [],
        ):
            if str(
                section.get("stem", "")
            ) == str(stem):

                section["_needs_repair"] = True
                break

    def regenerate_one(
        self,
        context: SceneContext,
        stem: str,
    ) -> None:
        """Regenerate one storyboard section.

        This intentionally does NOT call run().

        The normal planner is video-level. Repair is section-level and
        therefore uses a targeted request containing only the affected
        section plus the existing neighbouring context.
        """

        storyboard = getattr(
            context,
            "storyboard_plan",
            None,
        )

        if not isinstance(
            storyboard,
            dict,
        ):
            self.run(context)
            return

        target = None

        for section in storyboard.get(
            "sections",
            [],
        ):
            if str(
                section.get("stem", "")
            ) == str(stem):
                target = section
                break

        if target is None:
            return

        feedback = self._repair_feedback(
            context
        )

        messages = feedback.get(
            str(stem),
            [],
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
            return

        # ---------------------------------------------------------------
        # Targeted repair prompt
        # ---------------------------------------------------------------

        prompt = f"""
You are repairing ONE storyboard section in an educational video.

Do not modify unrelated sections.

Preserve:
- the teaching claim,
- all stated numerical values,
- the animation contract,
- the narration meaning.

Fix only the reported problem.

Return ONLY JSON.

{{
  "index": {entry.index},
  "title": {json.dumps(entry.title)},
  "claim": "...",
  "states": [
    {{
      "name": "...",
      "cue": 0,
      "visual": "...",
      "values": [],
      "transition": "..."
    }}
  ]
}}

CURRENT SECTION:
{json.dumps(target, ensure_ascii=False, indent=2)}

ANIMATION BRIEF:
{entry.anim}

REPAIR FEEDBACK:
{json.dumps(messages, ensure_ascii=False, indent=2)}
""".strip()

        try:
            repaired = self._call_llm(
                prompt
            )

        except Exception as exc:
            cfg.warn(
                f"Storyboard repair failed for {stem}: {exc}"
            )
            return

        if not repaired:
            return

        repaired = _normalise_section(
            repaired,
            entry,
            "llm-repair",
        )

        # ---------------------------------------------------------------
        # Replace exactly one section
        # ---------------------------------------------------------------

        for index, section in enumerate(
            storyboard.get("sections", [])
        ):
            if str(
                section.get("stem", "")
            ) == str(stem):

                storyboard["sections"][index] = (
                    repaired
                )

                break

        storyboard["repair"] = {
            "stem": stem,
            "feedback": messages,
        }

        _atomic_write_json(
            _harness_dir(context.project_dir)
            / STORYBOARD_FILE,
            storyboard,
        )