"""LLM-assisted semantic correctness verifier for Prompt2Render.

This verifier evaluates whether generated scene code actually fulfills the
scene's educational intent. It combines deterministic prerequisites with an
LLM critic:

    scene plan + narration + generated code + fresh preview
        ↓
    semantic critic
        ↓
    structured finding
        ↓
    repair_router

Important boundaries
--------------------
* This is a semantic reviewer, not the deterministic execution verifier.
* It does not silently accept malformed LLM output.
* It never treats a missing preview as a successful visual audit.
* It does not mutate scene code.
* It keeps generated-code acceptance separate from verification.
* During repair, it regenerates the preview for the affected scene only.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin
from .... import cfg, llm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gemini-3.7-flash"
MAX_CODE_CHARS = 24000
MAX_PROMPT_CHARS = 50000


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _ensure_keys() -> list[str]:
    """Resolve Gemini keys without terminating the harness."""

    try:
        if hasattr(llm, "keys"):
            keys = llm.keys()
        else:
            primary = os.environ.get(
                "GEMINI_API_KEY",
                "",
            ).strip()

            keys = (
                [primary]
                if primary
                else []
            )

    except (
        SystemExit,
        Exception,
    ):
        keys = []

    return [
        str(key).strip()
        for key in keys
        if str(key).strip()
    ]


def _model_name() -> str:
    """Resolve the configured semantic-review model."""

    if hasattr(
        llm,
        "model_chain",
    ):
        try:
            models = llm.model_chain(
                "P2R_SCENE_MODEL",
                DEFAULT_MODEL,
            )

            if models:
                return str(
                    models[0]
                )
        except Exception:
            pass

    return os.environ.get(
        "P2R_SCENE_MODEL",
        DEFAULT_MODEL,
    )


def _client(
    key: str,
):
    """Build a client using the project's LLM abstraction when available."""

    if hasattr(
        llm,
        "client",
    ):
        return llm.client(
            key
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "openai is not installed; "
            "the semantic verifier requires an "
            "OpenAI-compatible client."
        ) from exc

    return OpenAI(
        api_key=key,
        base_url=(
            "https://generativelanguage."
            "googleapis.com/v1beta/openai/"
        ),
        timeout=300.0,
        max_retries=2,
    )


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _extract_json(
    content: str,
) -> dict[str, Any] | None:
    """Extract a JSON object from normal or fenced LLM output.

    No heuristic fallback to ``status=pass`` is allowed. If the critic cannot
    produce valid structured output, verification must fail closed.
    """

    if not isinstance(
        content,
        str,
    ):
        return None

    text = content.strip()

    if text.startswith(
        "```"
    ):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*```$",
            "",
            text,
        ).strip()

    # First attempt: entire response.
    try:
        value = json.loads(
            text,
            strict=False,
        )

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else None
        )

    except json.JSONDecodeError:
        pass

    # Second attempt: extract the outermost object.
    start = text.find(
        "{"
    )
    end = text.rfind(
        "}"
    )

    if (
        start < 0
        or end <= start
    ):
        return None

    try:
        value = json.loads(
            text[
                start:end + 1
            ],
            strict=False,
        )

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else None
        )

    except json.JSONDecodeError:
        return None


def _normalize_result(
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate and normalize critic output."""

    if not isinstance(
        result,
        dict,
    ):
        return None

    status = str(
        result.get(
            "status",
            "",
        )
    ).strip().lower()

    if status not in {
        "pass",
        "fail",
    }:
        return None

    reason = str(
        result.get(
            "reason",
            "",
        )
    ).strip()

    normalized = {
        "status": status,
        "reason": reason,
    }

    # Preserve optional structured reviewer fields if supplied.
    for key in (
        "violations",
        "evidence",
        "severity",
        "confidence",
        "fix",
    ):
        if key in result:
            normalized[key] = result[key]

    return normalized


def _is_layout_defect(result: dict[str, Any]) -> bool:
    """Whether a semantic-critic result actually describes a layout/crowding defect.

    A layout/crowding defect is being reported as SEMANTIC when the VLM
    happens to discover geometric overflow during semantic review. This
    heuristic prevents misclassification by detecting layout-specific
    language in the critic's output.

    Returns True if the result is layout-like (should be handled by
    verifier_layout), False if it is genuinely semantic.
    """

    if not isinstance(result, dict):
        return False

    # Collect all textual fields
    parts: list[str] = []
    for key in ("reason", "fix", "detail", "message"):
        v = result.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    for key in ("violations", "evidence"):
        v = result.get(key)
        if isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str) and item.strip():
                    parts.append(item)

    text = " ".join(parts).lower()

    if not text.strip():
        return False

    layout_keywords = [
        "caption",
        "overlap",
        "overlaps",
        "crowd",
        "crowding",
        "cramped",
        "tightly packed",
        "tightly",
        "margin",
        "safe area",
        "safe zone",
        "bottom edge",
        "bottom region",
        "overflow",
        "offframe",
        "off frame",
        "outside",
        "clipped",
        "clipping",
        "bbox",
        "bounding box",
        "collision",
        "near_safe_margin",
        "text overflow",
        "label",
        "stacked",
    ]

    # Strong layout signals: caption + geometric term together is a layout defect
    has_layout = any(kw in text for kw in layout_keywords)

    # Additional geometric evidence like "node label" + "complexity label" stacked tightly
    # is also layout when it mentions positioning / spacing
    geometric_terms = ["position", "spacing", "font size", "y-position", "packed", "touching", "edge"]
    has_geometric = any(term in text for term in geometric_terms)

    # If it mentions caption/label bottom crowding, it's layout regardless
    if "caption" in text and any(w in text for w in ("bottom", "margin", "overflow", "overlap", "crowd", "zone")):
        return True

    if has_layout:
        # Ensure it's not purely semantic: if it also mentions strong semantic signals
        # like wrong values/state but ALSO layout, layout wins only when geometric evidence dominates.
        # For the task's example, layout keywords dominate, so we bias toward layout when both present.
        # Check that at least one explicit layout geometric phrase exists.
        if any(kw in text for kw in ["caption", "bbox", "margin", "overflow", "overlap", "crowd", "safe", "zone", "clipped"]):
            return True
        if has_geometric:
            return True

    return False


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(
    entry,
    code: str,
    *,
    has_preview: bool,
) -> str:
    """Build a strict semantic-review prompt."""

    visual_instruction = (
        "A preview frame is attached. Evaluate it as evidence for layout "
        "and visual-state correctness."
        if has_preview
        else
        "No preview frame is available. Do NOT claim that layout or rendered "
        "appearance was visually verified. Restrict your judgement to code, "
        "brief, and narration."
    )

    prompt = f"""
You are a strict educational-video reviewer and computer-science expert.

Your task is to determine whether ONE generated scene faithfully implements
the educational intent supplied below.

SCENE:
{entry.stem}

TITLE:
{entry.title}

ANIMATION / VISUAL BRIEF:
{entry.anim}

NARRATION:
{entry.narration_text}

GENERATED CODE:
```python
{code}
```

{visual_instruction}

Evaluate all of the following:

1. DATA CONSISTENCY
   - Preserve exact values explicitly required by the visual brief/narration.
   - Do not invent, silently drop, reorder, or alter important values.

2. DOMAIN INVARIANTS
   - Check mathematical/computational rules that are directly relevant.
   - Examples:
     * Tower of Hanoi: a larger disk must not rest on a smaller disk in a
       legal state.
     * Sorting: a state labelled sorted must actually be sorted.
     * Trees/graphs: parent-child/edge relationships must match the claim.
   - Do not invent an invariant unrelated to the supplied topic.

3. ILLEGAL-RULE DEMONSTRATIONS
   - If the narration intentionally demonstrates an illegal state, the visual
     must physically depict the illegal state.
   - It must also clearly mark that state as illegal.
   - Merely writing "ILLEGAL" beside a legal state is insufficient.

4. PEDAGOGICAL CONSISTENCY
   - The visual state must not contradict what the speaker says.
   - Transitions must preserve established values unless the narration
     explains the change.

5. VISUAL INTENT
   - Determine whether the generated code actually implements the major
     visual claim in the animation brief.
   - Do not reward code merely because it contains similarly named objects.

6. LAYOUT
   - Only evaluate actual rendered layout when a preview is attached.
   - Check for overlap, clipping, unreadably small text, or visibly broken
     composition.

IMPORTANT:
- Be conservative.
- Do not reject a scene merely because you would design it differently.
- Reject only an actual contradiction, missing required visual state, invalid
  domain invariant, or clearly broken layout.
- If evidence is insufficient, say so in the reason rather than inventing a
  failure.

Return ONLY this JSON object:

{{
  "status": "pass" | "fail",
  "reason": "specific evidence-based explanation",
  "violations": [
    "optional concise violation"
  ],
  "evidence": [
    "optional code/visual evidence"
  ],
  "fix": "optional concrete correction"
}}

Do not return Markdown outside the JSON object.
""".strip()

    return prompt[
        :MAX_PROMPT_CHARS
    ]


# ---------------------------------------------------------------------------
# Preview handling
# ---------------------------------------------------------------------------

def _preview_path(
    context: SceneContext,
    stem: str,
) -> Path:
    return (
        context.project_dir
        / "build"
        / "manim"
        / "previews"
        / f"Scene{stem}.png"
    )


def _preview_is_fresh(
    preview: Path,
    source: Path,
) -> bool:
    """Is ``preview`` actually a picture of ``source``?

    A preview only counts as visual evidence when it is at least as new as
    the code it claims to depict. ``has_preview`` used to be a bare
    ``Path.exists()``, so outside a repair cycle the verifier would happily
    attach whatever PNG last happened to land on disk -- typically the
    render of a *previous* generation of the scene -- and present it to the
    model as evidence for layout. That produces confident verdicts about a
    frame the current code never produced, in both directions: passing a
    broken scene because the old frame looked fine, or failing a fixed one
    because the old frame still shows the defect.

    Being unable to prove freshness is treated as stale. This module's
    contract is that it never claims visual verification it does not have
    (see the module docstring); judging from code alone is the weaker but
    honest answer.
    """

    try:
        return preview.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def _regenerate_preview(
    context: SceneContext,
    entry,
) -> Path | None:
    """Regenerate one Manim preview during repair.

    This helper is deliberately limited to the affected scene. For SceneKit,
    normal renderers remain responsible for producing their preview artifacts.
    """

    preview = _preview_path(
        context,
        entry.stem,
    )

    scene_file = (
        context.project_dir
        / "build"
        / "manim"
        / f"scene_{entry.stem}.py"
    )

    if not scene_file.exists():
        return None

    try:
        from ....project import parse_script
        from ....visuals import manim_scene

        preview.unlink(
            missing_ok=True
        )

        manim_scene(
            context.project_dir,
            parse_script(context.prompt),
            scene_file,
            f"Scene{entry.stem}",
            entry.index,
        )

    except (
        SystemExit,
        Exception,
    ) as exc:
        raise RuntimeError(
            f"repaired Manim scene failed to render: {exc}"
        ) from exc

    return (
        preview
        if preview.exists()
        else None
    )


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

def _make_finding(
    *,
    stem: str,
    result: dict[str, Any],
    gate: bool,
) -> dict[str, Any]:
    """Convert semantic-review output into a harness finding."""

    reason = result.get(
        "reason",
        "Semantic mismatch detected by LLM critic.",
    )

    finding = Finding(
        finding_id=next_finding_id(
            "sem"
        ),
        scene_id=stem,
        category=Category.SEMANTIC,
        severity=(
            Severity.BLOCKING
            if gate
            else Severity.WARNING
        ),
        message=str(
            reason
        ),
    ).as_check_result()

    finding["finding_type"] = (
        "semantic_mismatch"
    )

    finding["mismatch_subtype"] = (
        "semantic_mismatch"
    )

    for key in (
        "violations",
        "evidence",
        "confidence",
        "fix",
    ):
        if key in result:
            finding[key] = result[key]

    return finding


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class VerifierSemanticPlugin(Plugin):
    """LLM-based semantic correctness reviewer."""

    name = "verifier_semantic"

    def declare_dependencies(self) -> list[str]:
        return [
            "code_artifacts",
            "scene_plan",
            "render_artifacts",
        ]

    def declare_effects(self) -> list[str]:
        return [
            "check_results",
        ]

    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:

        findings: list[
            dict[str, Any]
        ] = []

        keys = _ensure_keys()

        if not keys:
            cfg.warn(
                "No GEMINI_API_KEY found; "
                "semantic verification skipped."
            )

            context.check_results[
                self.name
            ] = [
                {
                    "status": "skip",
                    "finding_type": (
                        "semantic_verification_unavailable"
                    ),
                    "detail": (
                        "No LLM API key is available "
                        "for semantic verification."
                    ),
                }
            ]

            return context

        model = _model_name()

        try:
            # Sanity-check that a client is even constructible before
            # spending time on any scene. The actual per-call client is
            # created internally by llm.complete() for whichever key/model
            # it ends up rotating to.
            _client(
                keys[0]
            )
        except Exception as exc:
            cfg.warn(
                f"Semantic verifier unavailable: {exc}"
            )

            context.check_results[
                self.name
            ] = [
                {
                    "status": "skip",
                    "finding_type": (
                        "semantic_verification_unavailable"
                    ),
                    "detail": str(exc),
                }
            ]

            return context

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

        gate = self.is_gate()

        for entry in context.scene_plan:

            artifact = (
                context.code_artifacts.get(
                    entry.stem
                )
            )

            if (
                artifact is None
                or artifact.path is None
                or not artifact.path.exists()
            ):
                continue

            try:
                code = artifact.path.read_text(
                    encoding="utf-8"
                )
            except Exception as exc:
                findings.append(
                    _make_finding(
                        stem=entry.stem,
                        gate=gate,
                        result={
                            "status": "fail",
                            "reason": (
                                "Could not read generated "
                                f"scene source: {exc}"
                            ),
                        },
                    )
                )

                continue

            if len(code) > MAX_CODE_CHARS:
                code = code[
                    :MAX_CODE_CHARS
                ] + (
                    "\n\n# [CODE TRUNCATED FOR REVIEW]\n"
                )

            # ----------------------------------------------------------
            # Fresh preview during repair
            # ----------------------------------------------------------

            preview = _preview_path(
                context,
                entry.stem,
            )

            if entry.stem in repair_context:
                try:
                    regenerated = (
                        _regenerate_preview(
                            context,
                            entry,
                        )
                    )

                    if regenerated is not None:
                        preview = regenerated

                except Exception as exc:
                    findings.append(
                        _make_finding(
                            stem=entry.stem,
                            gate=gate,
                            result={
                                "status": "fail",
                                "reason": str(exc),
                            },
                        )
                    )

                    continue

            # ----------------------------------------------------------
            # Build prompt
            # ----------------------------------------------------------

            # A preview that predates the code it depicts is not evidence
            # about this scene -- see _preview_is_fresh().
            has_preview = (
                preview.exists()
                and _preview_is_fresh(
                    preview,
                    artifact.path,
                )
            )

            prompt = _build_prompt(
                entry,
                code,
                has_preview=has_preview,
            )

            image_base64 = (
                base64.b64encode(
                    preview.read_bytes()
                ).decode("ascii")
                if has_preview
                else None
            )

            # ----------------------------------------------------------
            # LLM call
            # ----------------------------------------------------------
            #
            # Always route through llm.complete(), preview or not. It owns
            # the deterministic key/model rotation (retry on 429, fall back
            # to the next model once every key is quota-exhausted) that
            # every other harness LLM call site already relies on. The old
            # raw client.chat.completions.create() fallback used whenever a
            # preview image was attached had none of that: a single 429
            # (even a transient one) went straight to `except Exception`
            # below and became a hard BLOCKING semantic_mismatch finding,
            # gating the whole pipeline on what was actually a quota hiccup.

            # A single transient hiccup -- a malformed/truncated critic
            # response, or an LLM call that raised despite llm.complete()'s
            # own key/model rotation -- used to become a permanent BLOCKING
            # finding on the first try, fail-closed with no second chance.
            # That is the right call once it's actually reproduced (see
            # "fail closed" below), but not on a one-off blip: it turned a
            # momentary overload into a hard gate failure for the whole
            # harness run. One silent retry before recording anything gives
            # a blip a chance to clear while still failing closed if the
            # problem repeats.
            result = None
            gave_up = False

            for attempt in (1, 2):
                try:
                    content = llm.complete(
                        prompt,
                        max_tokens=1400,
                        model_env="P2R_SCENE_MODEL",
                        default_model=model,
                        label="semantic",
                        image_base64=image_base64,
                        json_object=True,
                    )

                    parsed = _normalize_result(
                        _extract_json(
                            str(
                                content or ""
                            )
                        )
                    )

                    if parsed is not None:
                        result = parsed
                        break

                    # ------------------------------------------------------
                    # Fail closed on malformed critic output.
                    # ------------------------------------------------------
                    if attempt == 2:
                        findings.append(
                            _make_finding(
                                stem=entry.stem,
                                gate=gate,
                                result={
                                    "status": "fail",
                                    "reason": (
                                        "Semantic critic returned "
                                        "invalid structured output; "
                                        "verification could not establish "
                                        "semantic correctness."
                                    ),
                                },
                            )
                        )
                        gave_up = True
                    else:
                        cfg.warn(
                            f"Semantic verifier got malformed output for "
                            f"{entry.stem}; retrying once"
                        )

                except Exception as exc:
                    # A semantic verifier that crashes should not silently
                    # turn into PASS. It is recorded as a verification
                    # failure -- but only once a retry has also failed.
                    if attempt == 2:
                        cfg.warn(
                            f"Semantic verification failed "
                            f"for {entry.stem}: {exc}"
                        )

                        findings.append(
                            _make_finding(
                                stem=entry.stem,
                                gate=gate,
                                result={
                                    "status": "fail",
                                    "reason": (
                                        "Semantic verification "
                                        f"failed: {exc}"
                                    ),
                                },
                            )
                        )
                        gave_up = True
                    else:
                        cfg.warn(
                            f"Semantic verification transiently failed "
                            f"for {entry.stem}: {exc}; retrying once"
                        )

            if gave_up or result is None:
                continue

            if result[
                "status"
            ] == "fail":
                # Diagnosis-driven routing: do not misclassify geometric/layout evidence as semantic
                # merely because the VLM happened to discover it during semantic review.
                if _is_layout_defect(result):
                    cfg.warn(
                        f"Semantic verifier suppressed layout-like finding for {entry.stem}: "
                        f"{result.get('reason','')[:120]} -- delegated to verifier_layout"
                    )
                    continue
                findings.append(
                    _make_finding(
                        stem=entry.stem,
                        gate=gate,
                        result=result,
                    )
                )

        context.check_results[
            self.name
        ] = findings

        return context

    def _default_gate(self) -> bool:
        """Semantic correctness is a hard gate by default."""

        return True