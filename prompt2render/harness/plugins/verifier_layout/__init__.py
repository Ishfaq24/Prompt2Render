"""Deterministic layout verifier for Prompt2Render.

This plugin is the authoritative geometric/layout gate. It surfaces
findings already recorded on ``RenderArtifact.audit`` but reclassifies
them as LAYOUT with precise sub-types, so that a caption that crowds the
bottom margin is never misattributed to semantics.

Hierarchy:
    STRUCTURAL -> render/missing assets
    LAYOUT     -> out_of_bounds, overlap, crowding, caption_collision etc
    SEMANTIC   -> wrong_object/wrong_value mismatches
    PEDAGOGICAL, TEMPORAL ...

The verifier complements (does not replace) ``verifier_spatial``: that
plugin remains advisory and reports SPATIAL for historical consumers,
while this plugin is the hard gate for layout (BLOCKING for
out_of_bounds / severe_overlap / caption_collision, WARNING for
near_safe_margin).

Severity mapping:
    fail + offframe/caption_collision/overlap/text_overflow/crowding
        -> BLOCKING  (unless explicitly near margin)
    warn + near_safe_margin / crowded
        -> WARNING

Deterministic checks already ran in scenekit.audit (or
observer_visual for Manim). This verifier does not recompute geometry;
it interprets the recorded warnings with layout-aware severity and
routing.

For Manim scenes, audit is produced by observer_visual similarly but
with frame sampling; the same textual kinds flow through.
"""

from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .... import cfg, llm
from ...context import SceneContext
from ...finding import (
    Category,
    Finding,
    LayoutSubtype,
    Severity,
    next_finding_id,
)
from ...plugin import Plugin

_RECORDED = re.compile(
    r"^(?P<level>WARN|FAIL)\s+\[(?P<kind>[^\]]+)\]\s+(?P<message>.*)$",
    re.DOTALL,
)

LAYOUT_BLOCKING_KINDS = frozenset(
    {"offframe", "title_collision", "overlap", "crowding", "text_overflow", "caption_collision", "blank"}
)

LAYOUT_WARNING_KINDS = frozenset(
    {"crowded", "near_safe_margin", "tiny"}
)

KIND_TO_SUBTYPE = {
    "offframe": LayoutSubtype.OUT_OF_BOUNDS.value,
    "caption_collision": LayoutSubtype.CAPTION_COLLISION.value,
    "title_collision": LayoutSubtype.TITLE_COLLISION.value,
    "overlap": LayoutSubtype.OVERLAP.value,
    "crowding": LayoutSubtype.CROWDING.value,
    "near_safe_margin": LayoutSubtype.NEAR_SAFE_MARGIN.value,
    "text_overflow": LayoutSubtype.TEXT_OVERFLOW.value,
    "blank": LayoutSubtype.OUT_OF_BOUNDS.value,
    "tiny": LayoutSubtype.TEXT_OVERFLOW.value,
    "crowded": LayoutSubtype.CROWDING.value,
    "unsafe_margin": LayoutSubtype.UNSAFE_MARGIN.value,
}


def _kind_to_subtype(kind: str) -> str:
    return KIND_TO_SUBTYPE.get(str(kind).strip(), str(kind).strip() or "unknown")


def _parse_recorded(recorded: Any) -> tuple[str, str, str]:
    text = str(recorded).strip()
    m = _RECORDED.match(text)
    if m:
        return m.group("level"), m.group("kind").strip(), m.group("message").strip()
    return "WARN", "unknown", text or "SceneKit layout audit reported an unspecified issue."


def _finding_for(
    stem: str,
    recorded: Any,
    *,
    gate: bool,
) -> dict[str, Any]:
    level, kind, message = _parse_recorded(recorded)
    subtype = _kind_to_subtype(kind)

    if level == "FAIL" and kind in LAYOUT_BLOCKING_KINDS:
        severity = Severity.BLOCKING
    elif level == "FAIL" and kind in LAYOUT_WARNING_KINDS:
        severity = Severity.WARNING
    elif level == "FAIL" and gate:
        severity = Severity.BLOCKING
    elif level == "FAIL":
        severity = Severity.BLOCKING
    else:
        severity = Severity.WARNING

    # Near margin should never be BLOCKING even if audit says FAIL (defensive)
    if kind == "near_safe_margin":
        severity = Severity.WARNING

    finding = Finding(
        finding_id=next_finding_id("layout"),
        scene_id=stem,
        category=Category.LAYOUT,
        severity=severity,
        message=message,
    )
    result = finding.as_check_result()
    result["finding_type"] = "layout_violation" if severity == Severity.BLOCKING else "layout_warning"
    # Keep both keys for compatibility; mismatch_subtype is the typed subtype
    result["mismatch_subtype"] = subtype
    result["layout_subtype"] = subtype
    result["audit_level"] = level
    result["recorded_kind"] = kind
    result["recorded_problem"] = str(recorded).strip()
    # Extract bbox/safe_zone etc if present in message for repair targeting
    # Preserve original message detail for routing
    return result


def _audit_warnings(record: dict[str, Any]) -> list[Any]:
    warnings = record.get("warnings", [])
    if warnings is None:
        return []
    if isinstance(warnings, (list, tuple)):
        return list(warnings)
    return [warnings]


DEFAULT_LAYOUT_MODEL = "gemini-3.7-flash"
MAX_CODE_CHARS = 24000

# See verifier_semantic's DEFAULT_VERIFIER_WORKERS for the rationale: each
# scene's VLM layout review is an independent round trip, previously run
# strictly sequentially across every scene in the programme.
DEFAULT_VERIFIER_WORKERS = 4


def _ensure_keys() -> list[str]:
    try:
        if hasattr(llm, "keys"):
            keys = llm.keys()
        else:
            primary = os.environ.get("GEMINI_API_KEY", "").strip()
            keys = [primary] if primary else []
    except (SystemExit, Exception):
        keys = []
    return [str(k).strip() for k in keys if str(k).strip()]


def _model_name() -> str:
    if hasattr(llm, "model_chain"):
        try:
            models = llm.model_chain("P2R_SCENE_MODEL", DEFAULT_LAYOUT_MODEL)
            if models:
                return str(models[0])
        except Exception:
            pass
    return os.environ.get("P2R_SCENE_MODEL", DEFAULT_LAYOUT_MODEL)


def _preview_path(context: SceneContext, stem: str) -> Path:
    try:
        from ...preview import preview_path_for

        return preview_path_for(context, stem)
    except Exception:
        return context.project_dir / "build" / "manim" / "previews" / f"Scene{stem}.png"


def _preview_is_fresh(preview: Path, source: Path) -> bool:
    try:
        return preview.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def _check_preview_exists(preview: Path) -> tuple[bool, str]:
    """Robust preview existence/size check per preview helper contract."""
    if not preview.exists():
        return False, f"required preview artifact missing at {preview}"
    try:
        size = preview.stat().st_size
        from ...preview import PREVIEW_MIN_BYTES

        if size < PREVIEW_MIN_BYTES:
            return False, f"preview file too small ({size} bytes) at {preview}"
    except OSError as exc:
        return False, f"preview not readable at {preview}: {exc}"
    return True, ""


def _salvage_partial_json_object(text: str) -> dict[str, Any] | None:
    """Recover structured fail/pass results from truncated LLM JSON.

    Some model responses are almost-valid JSON but end mid-string, usually in the
    final ``fix`` field. Those payloads still contain enough information to
    classify the scene as a real layout fail rather than a spurious
    ``VERIFICATION_UNAVAILABLE`` result.
    """
    if not isinstance(text, str):
        return None
    lowered = text.lower()
    if '"status"' not in lowered:
        return None

    def _decode(value: str) -> str:
        try:
            return bytes(value, "utf-8").decode("unicode_escape")
        except Exception:
            return value

    obj: dict[str, Any] = {}
    for key in ("status", "reason", "fix"):
        match = re.search(rf'"{key}"\s*:\s*"((?:\\.|[^"\\])*)', text, flags=re.DOTALL)
        if match:
            obj[key] = _decode(match.group(1)).rstrip("\n")
    for key in ("violations", "evidence"):
        match = re.search(rf'"{key}"\s*:\s*\[(.*?)(?:\]\s*(?:,|\}})|\]\s*$)', text, flags=re.DOTALL)
        if match:
            items: list[str] = []
            for item in re.findall(r'"((?:\\.|[^"\\])*)"', match.group(1), flags=re.DOTALL):
                items.append(_decode(item))
            if items:
                obj[key] = items

    status = str(obj.get("status", "")).strip().lower()
    reason = str(obj.get("reason", "")).strip()
    if status not in {"pass", "fail"} or not reason:
        return None
    normalized = {"status": status, "reason": reason}
    for key in ("violations", "evidence", "fix"):
        if key in obj:
            normalized[key] = obj[key]
    return normalized


def _extract_json(content: str) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        v = json.loads(text, strict=False)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        pass
    else:
        try:
            v = json.loads(text[start:end+1], strict=False)
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            pass
    return _salvage_partial_json_object(text)


def _normalize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    status = str(result.get("status", "")).strip().lower()
    if status not in {"pass", "fail"}:
        return None
    reason = str(result.get("reason", "")).strip()
    normalized = {"status": status, "reason": reason}
    for k in ("violations", "evidence", "severity", "confidence", "fix"):
        if k in result:
            normalized[k] = result[k]
    return normalized


def _build_layout_prompt(entry, code: str, *, has_preview: bool) -> str:
    visual_instruction = (
        "A preview frame is attached. Evaluate it for layout only: "
        "overlap, clipping, caption crowding, text overflow, safe-margin violations."
        if has_preview
        else
        "No preview frame is available. Restrict judgement to code and layout zones."
    )
    return f"""
You are a strict layout reviewer for educational videos.

SCENE: {entry.stem}
TITLE: {entry.title}
ANIM BRIEF: {entry.anim}
NARRATION: {entry.narration_text}
CODE:
```python
{code}
```
{visual_instruction}

Evaluate ONLY layout:
- Caption inside caption zone (y 0.4-1.3)
- No overlap between caption and labels
- No text outside safe area (x 0.4-15.6, y 0.4-8.6)
- No crowding in bottom region
- Multiline caption fits allocated height

Return ONLY JSON:
{{
  "status": "pass" | "fail",
  "reason": "evidence-based explanation",
  "violations": ["concise violation"],
  "evidence": ["code/visual evidence"],
  "fix": "concrete correction (move caption, increase gap, reduce font)"
}}
""".strip()[:50000]


def _layout_subtype_from_result(result: dict[str, Any]) -> str:
    text = " ".join([
        str(result.get("reason", "")),
        " ".join(str(v) for v in result.get("violations", []) if isinstance(v, str)),
        str(result.get("fix", "")),
    ]).lower()
    if "caption" in text and ("overlap" in text or "collision" in text):
        return LayoutSubtype.CAPTION_COLLISION.value
    if "caption" in text and ("zone" in text or "outside" in text):
        return LayoutSubtype.CAPTION_COLLISION.value
    if "overflow" in text or "multiline" in text:
        return LayoutSubtype.TEXT_OVERFLOW.value
    if "crowd" in text:
        return LayoutSubtype.CROWDING.value
    if "overlap" in text:
        return LayoutSubtype.OVERLAP.value
    if "offframe" in text or "off frame" in text or "outside" in text:
        return LayoutSubtype.OUT_OF_BOUNDS.value
    if "margin" in text:
        return LayoutSubtype.NEAR_SAFE_MARGIN.value
    return LayoutSubtype.CROWDING.value


def _make_vlm_layout_finding(*, stem: str, result: dict[str, Any], gate: bool) -> dict[str, Any]:
    reason = result.get("reason", "Layout violation detected by VLM.")
    subtype = _layout_subtype_from_result(result)
    severity = Severity.BLOCKING if gate else Severity.WARNING
    # near margin should be warning even via VLM
    if subtype == LayoutSubtype.NEAR_SAFE_MARGIN.value:
        severity = Severity.WARNING
    finding = Finding(
        finding_id=next_finding_id("layout"),
        scene_id=stem,
        category=Category.LAYOUT,
        severity=severity,
        message=str(reason),
    ).as_check_result()
    finding["finding_type"] = "layout_violation"
    finding["mismatch_subtype"] = subtype
    finding["layout_subtype"] = subtype
    for k in ("violations", "evidence", "fix"):
        if k in result:
            finding[k] = result[k]
    return finding


class VerifierLayoutPlugin(Plugin):
    """Deterministic + VLM layout verifier."""

    name = "verifier_layout"

    def declare_dependencies(self) -> list[str]:
        return ["render_artifacts", "code_artifacts", "scene_plan"]

    def declare_effects(self) -> list[str]:
        return ["check_results"]

    def run(self, context: SceneContext) -> SceneContext:
        findings: list[dict[str, Any]] = []
        gate = self.is_gate()
        stems_with_blocking: set[str] = set()

        # Phase 1: deterministic audit from render artifacts
        for stem, artifact in context.render_artifacts.items():
            record = getattr(artifact, "audit", None)
            if record is None:
                from ...finding import verification_unavailable

                findings.append(
                    verification_unavailable(
                        verifier=self.name,
                        stem=stem,
                        reason="required preview artifact missing -- no layout audit recorded for this scene",
                        category=Category.LAYOUT,
                    )
                )
                stems_with_blocking.add(stem)
                continue
            if not isinstance(record, dict):
                findings.append({
                    "status": "fail",
                    "stem": stem,
                    "finding_type": "layout_audit_invalid",
                    "category": Category.LAYOUT.value,
                    "detail": "RenderArtifact.audit is not a dictionary.",
                    "verifier": self.name,
                    "verifier_state": "VERIFICATION_UNAVAILABLE",
                })
                stems_with_blocking.add(stem)
                continue

            status_raw = str(record.get("status") or "").strip().lower()
            warnings = _audit_warnings(record)
            if status_raw == "fail" and not warnings:
                warnings = [record.get("detail", "Layout audit reported FAIL.")]
            stem_had_warnings = bool(warnings)
            blocking_here = 0

            if warnings:
                for warning in warnings:
                    text = str(warning)
                    level, kind, msg = _parse_recorded(text)
                    # Filter: only layout kinds; skip non-layout audit kinds that are not layout (but most are layout)
                    layout_kinds = {"tiny", "caption_collision", "unsafe_margin", "text_overflow", "title_collision", "near_safe_margin", "overlap", "blank", "offframe", "crowding", "crowded"}
                    if kind not in layout_kinds and kind != "unknown":
                        continue
                    if kind == "unknown":
                        low = text.lower()
                        if not any(kw in low for kw in ("caption", "overlap", "offframe", "crowd", "margin", "overflow", "zone", "bbox", "safe")):
                            continue
                    finding = _finding_for(stem, warning, gate=gate)
                    findings.append(finding)
                    if finding.get("severity") == Severity.BLOCKING.value or finding.get("status") == "fail":
                        blocking_here += 1
                if blocking_here > 0:
                    stems_with_blocking.add(stem)
                # If warnings existed but none were blocking, we still don't emit extra pass
                if stem_had_warnings and blocking_here == 0:
                    # warnings were all warnings -> continue without adding pass
                    continue
                if stem_had_warnings and blocking_here > 0:
                    continue
                # If warnings existed and were blocking, we already added
            # No warnings path
            if status_raw == "warn" and not stem_had_warnings:
                findings.append({
                    "status": "warn",
                    "stem": stem,
                    "finding_type": "layout_audit_warning",
                    "category": Category.LAYOUT.value,
                    "detail": "Layout audit returned WARN without structured warning list.",
                })
                continue
            if status_raw == "fail" and not stem_had_warnings:
                findings.append({
                    "status": "fail",
                    "stem": stem,
                    "finding_type": "layout_violation",
                    "category": Category.LAYOUT.value,
                    "detail": "Layout audit reported FAIL.",
                })
                stems_with_blocking.add(stem)
                continue
            if stem_had_warnings:
                continue
            # Clean
            still_count = record.get("stills", 0)
            unit = record.get("unit", "stills")
            findings.append({
                "status": "pass",
                "stem": stem,
                "finding_type": "layout_audit",
                "category": Category.LAYOUT.value,
                "detail": f"{still_count} {unit} clean (layout)",
            })

        # Phase 2: VLM layout review for scenes without deterministic blocking (only if preview available and keys exist)
        # This catches semantic-review-discovered crowding that audit might have missed in Manim path
        keys = _ensure_keys()
        # Early exit if no keys: no VLM available
        if keys:
            try:
                from .... import llm as _llm
                _llm.client(keys[0])
            except Exception:
                keys = []

        if keys:
            candidates = []
            for entry in getattr(context, "scene_plan", []) or []:
                stem = str(getattr(entry, "stem", "") or "").strip()
                if not stem or stem in stems_with_blocking:
                    continue
                artifact = context.code_artifacts.get(stem)
                if artifact is None or artifact.path is None or not artifact.path.exists():
                    continue
                candidates.append((stem, entry, artifact))

            workers = max(
                1,
                cfg.env_int("P2R_VERIFIER_WORKERS", DEFAULT_VERIFIER_WORKERS),
            )

            # Each candidate's VLM review is an independent round trip (own
            # code, own preview); dispatch concurrently rather than one
            # scene at a time, then apply the resulting findings to the
            # shared list back on this thread so nothing here races.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                vlm_results = list(
                    pool.map(
                        lambda c: self._vlm_review_one(context, c[0], c[1], c[2], gate),
                        candidates,
                    )
                )

            for stem, vlm_finding in vlm_results:
                if vlm_finding is None:
                    continue
                # Remove any prior pass for this stem (deterministic clean) to avoid duplicate pass
                findings = [f for f in findings if not (str(f.get("stem") or "") == stem and str(f.get("finding_type")) == "layout_audit" and str(f.get("status")) == "pass")]
                findings.append(vlm_finding)

        context.check_results[self.name] = findings
        return context

    def _vlm_review_one(
        self,
        context: SceneContext,
        stem: str,
        entry,
        artifact,
        gate: bool,
    ) -> tuple[str, dict[str, Any] | None]:
        """One scene's VLM layout review; returns (stem, finding-or-None).

        Split out of ``run()`` so independent scenes' LLM round trips can be
        dispatched to a thread pool without any of them mutating shared
        state directly.

        Preview handling is robust and candidate-aware via
        :mod:`prompt2render.harness.preview`. A missing or truncated preview
        after a bounded regeneration attempt becomes
        ``VERIFICATION_UNAVAILABLE`` (BLOCKING) rather than a crash or a
        silent PASS -- the bug that produced
        ``FileNotFoundError: .../previews/Scene01.png`` during re-verification.
        """
        # Candidate-aware preview resolution
        preview = _preview_path(context, stem)
        has_preview = False
        try:
            ok, _ = _check_preview_exists(preview)
            has_preview = ok and _preview_is_fresh(preview, artifact.path)
        except Exception:
            has_preview = False

        repair_context = getattr(context, "repair_context", {}) or {}
        in_repair = stem in repair_context if isinstance(repair_context, dict) else False

        # If no preview and we're not in a repair cycle, there is no VLM to
        # run -- this verifier is supplementary for Manim and the deterministic
        # audit already decided. Do not fabricate a blocking finding here;
        # the deterministic audit's own VERIFICATION_UNAVAILABLE (when its
        # RenderArtifact.audit is missing) is the correct signal for a
        # renderer that never produced any audit at all.
        if not has_preview and not in_repair:
            return stem, None

        # Attempt to ensure a preview exists (candidate-aware). Use the
        # central helper which extracts from the rendered clip if needed.
        if not has_preview:
            try:
                from ...preview import ensure_preview

                ensured, diag = ensure_preview(context, stem)
                if ensured is not None and ensured.exists():
                    preview = ensured
                    has_preview = _preview_is_fresh(preview, artifact.path) if artifact.path else True
                    # Still verify size
                    ok, _ = _check_preview_exists(preview)
                    has_preview = ok and has_preview
                else:
                    # Preview could not be ensured -- this is a verification
                    # infrastructure failure, not a layout defect.
                    from ...finding import verification_unavailable, Category

                    if gate:
                        return stem, verification_unavailable(
                            verifier=self.name,
                            stem=stem,
                            reason=f"required preview artifact missing -- could not ensure preview for layout verification: {diag}",
                            category=Category.LAYOUT,
                        )
                    return stem, None
            except Exception as exc:
                from ...finding import verification_unavailable, Category

                if gate:
                    return stem, verification_unavailable(
                        verifier=self.name,
                        stem=stem,
                        reason=f"required preview artifact missing -- {exc}",
                        category=Category.LAYOUT,
                    )
                return stem, None

        try:
            code = artifact.path.read_text(encoding="utf-8")
        except Exception as exc:
            from ...finding import verification_unavailable, Category

            return stem, verification_unavailable(
                verifier=self.name,
                stem=stem,
                reason=f"could not read scene source for layout verification: {exc}",
                category=Category.LAYOUT,
            )

        if len(code) > MAX_CODE_CHARS:
            code = code[:MAX_CODE_CHARS] + "\n\n# [CODE TRUNCATED FOR REVIEW]\n"

        # Deterministic preview filename, size-verified, race-safe
        image_b64 = None
        if has_preview:
            try:
                # Re-check existence/size immediately before read to avoid
                # TOCTOU race that previously produced FileNotFoundError
                ok, diag = _check_preview_exists(preview)
                if not ok:
                    from ...finding import verification_unavailable, Category

                    if gate:
                        return stem, verification_unavailable(
                            verifier=self.name,
                            stem=stem,
                            reason=f"required preview artifact missing: {diag}",
                            category=Category.LAYOUT,
                        )
                    return stem, None
                image_b64 = base64.b64encode(preview.read_bytes()).decode("ascii")
            except (OSError, FileNotFoundError) as exc:
                from ...finding import verification_unavailable, Category

                if gate:
                    return stem, verification_unavailable(
                        verifier=self.name,
                        stem=stem,
                        reason=f"required preview artifact missing: {exc}",
                        category=Category.LAYOUT,
                    )
                return stem, None

        prompt = _build_layout_prompt(entry, code, has_preview=has_preview)
        model = _model_name()
        try:
            from ...model_routing import effective_model_env

            layout_model_env = effective_model_env("verifier")
        except Exception:
            layout_model_env = "P2R_SCENE_MODEL"
        try:
            content = llm.complete(
                prompt,
                max_tokens=800,
                model_env=layout_model_env,
                default_model=model,
                label="layout",
                image_base64=image_b64,
                json_object=True,
            )
            # Robust structured-output handling: strict JSON, bounded repair
            parsed = _extract_json(str(content or ""))
            # Attempt a single normalization/repair pass for truncated JSON
            result = _normalize_result(parsed)
            if result is None and parsed is not None:
                # Try to repair common truncations (missing closing brace)
                try:
                    import json as _json

                    # Bounded repair: if the raw content looked like a JSON
                    # prefix, try adding missing braces (at most once)
                    raw = str(content or "").strip()
                    if raw.count("{") > raw.count("}"):
                        repaired = raw + "}" * (raw.count("{") - raw.count("}"))
                        result = _normalize_result(_extract_json(repaired))
                except Exception:
                    result = None

            if result is None:
                from ...finding import verification_unavailable, Category

                raw = (str(content)[:400] if content else "")
                return stem, verification_unavailable(
                    verifier=self.name,
                    stem=stem,
                    reason=f"Layout critic returned invalid structured output; verification unavailable. Raw (truncated): {raw!r}",
                    category=Category.LAYOUT,
                )

            if result.get("status") == "unavailable":
                from ...finding import verification_unavailable, Category

                return stem, verification_unavailable(
                    verifier=self.name,
                    stem=stem,
                    reason=result.get("reason", "layout verification unavailable"),
                    category=Category.LAYOUT,
                )

            if result["status"] == "fail":
                return stem, _make_vlm_layout_finding(stem=stem, result=result, gate=gate)
        except Exception as exc:
            from ...finding import verification_unavailable, Category

            cfg.warn(f"Layout VLM verification failed for {stem}: {exc}")
            # VLM infrastructure failure -- unavailable, not a layout defect
            return stem, verification_unavailable(
                verifier=self.name,
                stem=stem,
                reason=f"Layout VLM verification failed: {exc}",
                category=Category.LAYOUT,
            )

        return stem, None

    def _default_gate(self) -> bool:
        return True
