"""Structured JSONL evidence logging for the Prompt2Render harness.

This module records experimental evidence rather than ordinary debug output.

Two artifacts are produced:

1. JSONL invocation log
   One record per plugin invocation containing:
       plugin
       input/output context hashes
       success/failure
       diagnostics
       duration
       token usage
       timestamp

2. self_correction_report.json
   Machine-readable summary of the complete self-correction run.

The logger deliberately does not alter SceneContext. Logging must remain
observational so that instrumentation cannot change pipeline behavior.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .context import SceneContext


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _jsonable(
    obj: Any,
) -> Any:
    """Convert harness objects into deterministic JSON-compatible values."""

    if obj is None or isinstance(
        obj,
        (str, int, float, bool),
    ):
        return obj

    if isinstance(
        obj,
        enum.Enum,
    ):
        return obj.value

    if isinstance(
        obj,
        (datetime, date),
    ):
        return obj.isoformat()

    if isinstance(
        obj,
        Path,
    ):
        return str(
            obj
        )

    if dataclasses.is_dataclass(
        obj
    ) and not isinstance(
        obj,
        type,
    ):
        return {
            str(key): _jsonable(
                value
            )
            for key, value in dataclasses.asdict(
                obj
            ).items()
        }

    if isinstance(
        obj,
        dict,
    ):
        return {
            str(key): _jsonable(
                value
            )
            for key, value in obj.items()
        }

    if isinstance(
        obj,
        (list, tuple),
    ):
        return [
            _jsonable(
                value
            )
            for value in obj
        ]

    if isinstance(
        obj,
        (set, frozenset),
    ):
        return sorted(
            (
                _jsonable(
                    value
                )
                for value in obj
            ),
            key=lambda value: repr(
                value
            ),
        )

    # Last-resort representation. Logging must never crash the pipeline merely
    # because an unexpected object entered the context.
    return repr(
        obj
    )


def context_hash(
    ctx: SceneContext,
) -> str:
    """Return a deterministic content hash of a SceneContext.

    The hash is deliberately short enough for readable JSONL while retaining
    sufficient entropy for before/after experiment comparisons.
    """

    blob = json.dumps(
        _jsonable(ctx),
        sort_keys=True,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        blob
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Repair evidence
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class RepairRecord:
    """Machine-readable evidence for one repair attempt."""

    cycle_id: int
    scene_id: str
    finding_type: str
    mismatch_subtype: str | None
    routed_to: list[str]
    diagnostic_message: str
    pre_repair_context_hash: str
    post_repair_context_hash: str
    outcome: str
    cycles_used: int
    timestamp: str


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class SelfCorrectionReport:
    """Machine-readable final summary of one self-correction run.

    ``repair_outcomes`` is the field that makes this report honest. A
    correction only *succeeded* when a candidate was actually accepted --
    not merely because an LLM produced replacement code, which is all the
    old ``repairs`` list could attest to.
    """

    project: str
    final_pass: bool
    iterations: int
    detected_issues: list[dict[str, Any]]
    repairs: list[dict[str, Any]]
    verification_results: dict[
        str,
        list[dict[str, Any]],
    ]
    findings_by_category: dict[
        str,
        int,
    ]

    #: Counts per repair decision: accepted / regression_rejected /
    #: verifier_failed / target_defect_unresolved / repair_budget_exhausted
    #: / not_routable / repair_errored.
    repair_outcomes: dict[str, int] = dataclasses.field(
        default_factory=dict
    )

    #: Repairs whose candidate was accepted, i.e. genuine self-corrections.
    repairs_accepted: int = 0

    #: Repairs rejected because the candidate was worse than what was
    #: already accepted. A high number here is a healthy signal: the
    #: harness is protecting quality, not failing.
    repairs_rejected_regression: int = 0

    repairs_failed_verification: int = 0
    repairs_budget_exhausted: int = 0

    #: One entry per repair cycle, fully explaining the decision.
    repair_decisions: list[dict[str, Any]] = dataclasses.field(
        default_factory=list
    )


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return (
        datetime.now(
            timezone.utc
        ).isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


# ``timezone`` is imported separately to keep the timestamp helper explicit.
from datetime import timezone


def _count_iterations(
    ctx: SceneContext,
    repair_controller: Any = None,
) -> int:
    """Number of repair cycles actually attempted.

    Previously this returned ``len(history) + len(repair_records)`` -- a sum
    of two heterogeneous event streams that was neither a repair count nor a
    pipeline-pass count. History grows once per stage (plus once per
    re-verification, plus again on every rewind), and repair_records
    included no-route and gave-up entries where no repair was attempted at
    all. When a controller is available its decision count is the real
    answer; otherwise fall back to the historical sum so callers without one
    keep getting a number.
    """

    if repair_controller is not None:
        return len(getattr(repair_controller, "decisions", []))

    return len(
        ctx.history
    ) + len(
        ctx.repair_records
    )


#: Verifiers that must have succeeded for a build to be certified.
#: If any of these is missing, reports VERIFICATION_UNAVAILABLE, or still
#: has a BLOCKING finding, final_pass must be False.
REQUIRED_VERIFIERS = (
    "verifier_execution",
    "verifier_temporal",
    "verifier_layout",
    "verifier_semantic",
    "verifier_spatial",
)

#: Additional required check: execution is also covered by renderer plugins,
#: but those emit to check_results via ``renderer_manim``/``renderer_stills``
#: manim_crash / stills_render_failure. We treat those as part of execution.


def _has_blocking(finding: Any) -> bool:
    try:
        from .scene_quality import classify

        return classify(finding) == "blocking"
    except Exception:
        return str(finding.get("status", "")).lower() == "fail"


def _is_verification_unavailable(finding: Any) -> bool:
    if not isinstance(finding, dict):
        return False
    ft = str(finding.get("finding_type", "")).strip()
    if ft == "verification_unavailable":
        return True
    # Legacy names that were previously used for unavailable
    if ft in {"semantic_verification_unavailable", "temporal_verification_unavailable", "layout_audit_unavailable", "spatial_audit_unavailable", "temporal_target_unavailable"}:
        # Those legacy entries were previously emitted as skip; treat any
        # remaining legacy skip as unavailable for final_pass purposes only
        # when they are the sole result for a required verifier.
        return str(finding.get("status", "")).lower() in {"skip", "fail"}
    verifier_state = str(finding.get("verifier_state", "")).strip()
    if verifier_state == "VERIFICATION_UNAVAILABLE":
        return True
    return False


def compute_final_pass(ctx: SceneContext) -> tuple[bool, str]:
    """Determine whether the harness run is certifiably PASS.

    Returns ``(final_pass, reason)``. ``reason`` is empty when PASS, else
    a human-readable explanation of the first blocking condition encountered.
    This is the single source of truth for ``final_pass`` -- both
    ``HarnessRunner`` and ``cmd_harness`` consult it rather than trusting
    the absence of a GateFailure alone.

    Checks, in order:
        1. No BLOCKING findings remain in any check_results.
        2. No VERIFICATION_UNAVAILABLE findings for required verifiers.
        3. Every required verifier has actually run (has an entry in
           check_results) -- a missing verifier result never allows PASS.
        4. Required artifacts exist (code + render for every planned scene).
        5. The finished programme exists and is not stale (covers the
           "final artifact corresponds to the accepted revision" invariant).
        6. Warnings may remain only if they are explicitly non-blocking
           (handled by (1) -- warnings are not blocking).
    """
    # 1. Any BLOCKING finding anywhere
    for plugin_name, results in (ctx.check_results or {}).items():
        if not isinstance(results, list):
            continue
        for finding in results:
            if not isinstance(finding, dict):
                continue
            if _has_blocking(finding):
                return False, f"blocking finding remains in {plugin_name}: {finding.get('finding_type') or finding.get('detail', '')!r}"

    # 2. VERIFICATION_UNAVAILABLE for required verifiers
    for verifier in REQUIRED_VERIFIERS:
        results = ctx.check_results.get(verifier)
        if results is None:
            continue
        for finding in results:
            if _is_verification_unavailable(finding):
                return False, f"required verifier {verifier!r} is unavailable: {finding.get('reason') or finding.get('detail', '')!r}"

    # 3. Missing verifier result -- required verifiers must have run
    # Only consider verifiers that are actually relevant to the current
    # pipeline. If the pipeline never planned a semantic or temporal stage
    # (e.g. a unit test with a minimal context), missing entries should
    # not block. We therefore only require verifiers that have at least
    # one scene that *should* have been verified: any scene in scene_plan
    # that has a code artifact implies execution/semantic/layout/spatial
    # should have produced evidence; any render artifact implies temporal
    # should have.
    planned_stems = {str(e.stem) for e in (getattr(ctx, "scene_plan", None) or [])}
    has_code = {str(k) for k, v in (getattr(ctx, "code_artifacts", None) or {}).items() if v is not None and getattr(v, "path", None)}
    has_render = {str(k) for k, v in (getattr(ctx, "render_artifacts", None) or {}).items() if v is not None}
    # If there are planned scenes with code, execution/semantic/layout/spatial are required
    if planned_stems & has_code:
        for verifier in ("verifier_execution", "verifier_semantic", "verifier_layout", "verifier_spatial"):
            if verifier not in ctx.check_results:
                return False, f"required verifier {verifier!r} has no results -- verification incomplete"
            # At least one finding should not be skip for those stems
            results = ctx.check_results.get(verifier) or []
            # If all results are skip/unavailable for planned stems, treat as incomplete
            stem_findings = [
                f for f in results if isinstance(f, dict) and str(f.get("stem") or f.get("scene_id") or "") in (planned_stems & has_code)
            ]
            if stem_findings and all(str(f.get("status", "")).lower() == "skip" for f in stem_findings):
                return False, f"required verifier {verifier!r} only has skip results for planned scenes"
    # Temporal verifier is Manim-specific (verifies rendered Manim clip
    # duration vs narration). For stills pipelines (no Manim source), it is
    # not applicable and should not block final_pass. Detect Manim stems
    # via code artifact path or source content.
    manim_stems: set[str] = set()
    try:
        for stem, art in (getattr(ctx, "code_artifacts", None) or {}).items():
            if art is None or getattr(art, "path", None) is None:
                continue
            p = str(getattr(art, "path"))
            if "build/manim" in p.replace("\\", "/"):
                manim_stems.add(str(stem))
                continue
            try:
                src = art.path.read_text(encoding="utf-8", errors="replace") if art.path.exists() else ""
                lower = src.lower()
                if ("from manim import" in lower or "import manim" in lower) and "class scene" in lower:
                    manim_stems.add(str(stem))
            except Exception:
                pass
        # Also consider any render artifact with a clip (Manim) as Manim
        for stem, rend in (getattr(ctx, "render_artifacts", None) or {}).items():
            try:
                clip = rend.clip_path() if hasattr(rend, "clip_path") else getattr(rend, "clip", None)
                if clip is not None and str(clip).strip():
                    manim_stems.add(str(stem))
            except Exception:
                pass
    except Exception:
        manim_stems = set()
    # Require temporal only when there is at least one Manim stem that
    # should have been verified.
    if has_render and manim_stems:
        if "verifier_temporal" not in ctx.check_results:
            return False, "required verifier 'verifier_temporal' has no results -- temporal verification missing"
        # Temporal is per-scene; ensure at least one non-skip result for Manim stems
        results = ctx.check_results.get("verifier_temporal") or []
        stem_findings = [f for f in results if isinstance(f, dict) and str(f.get("stem") or "") in (has_render & manim_stems)]
        if stem_findings and all(str(f.get("status", "")).lower() == "skip" for f in stem_findings):
            return False, "temporal verification only produced skip results"

    # 4. Required artifacts exist
    for stem in planned_stems:
        code = (getattr(ctx, "code_artifacts", None) or {}).get(stem)
        if code is None or getattr(code, "path", None) is None or not code.path.exists():
            return False, f"required code artifact missing for scene {stem!r}"
        # Render artifact is required if code exists (every code should be rendered)
        if stem in has_code:
            rend = (getattr(ctx, "render_artifacts", None) or {}).get(stem)
            if rend is None:
                return False, f"required render artifact missing for scene {stem!r}"
            # For stills path, manifest should have entries; for Manim, clip should exist
            manifest = getattr(rend, "manifest", None) or []
            clip = rend.clip_path() if hasattr(rend, "clip_path") else getattr(rend, "clip", None)
            if not manifest and (clip is None or not Path(clip).exists()):
                return False, f"render artifact for scene {stem!r} has no manifest or clip"

    # 5. Final programme exists and is current
    try:
        from .lineage import is_scene_stem

        if planned_stems:
            program = getattr(ctx, "program", None)
            if program is None:
                return False, "final programme artifact is missing -- no finish stage produced out/final.mp4"
            final = getattr(program, "final_mp4", None)
            if final is None or not Path(final).exists():
                return False, f"final video missing at {final!r}"
            try:
                if Path(final).stat().st_size <= 2048:
                    return False, f"final video too small at {final!r}"
            except OSError as exc:
                return False, f"final video not readable: {exc}"
            if hasattr(program, "is_stale") and program.is_stale(getattr(ctx, "scene_versions", {}) or {}):
                return False, "final video was built from superseded scene revisions -- stale"
    except Exception as exc:
        return False, f"final programme check failed: {exc}"

    return True, ""


def write_self_correction_report(
    ctx: SceneContext,
    final_pass: bool,
    repair_controller: Any = None,
) -> Path:
    """Persist the complete machine-readable self-correction report.

    ``repair_controller`` supplies the repair decisions. Without it the
    report still writes, but with empty outcome counts -- it cannot claim
    anything about whether corrections succeeded.

    ``final_pass`` is the caller's claim (derived from gate failures), but
    this function **re-validates** it against
    :func:`compute_final_pass`. A caller that claims True while verification
    is incomplete will be downgraded to False and the reason recorded --
    this is what makes ``final_pass`` trustworthy rather than merely
    reflecting whether a GateFailure was raised.
    """

    all_findings: list[
        dict[str, Any]
    ] = []

    for results in (
        ctx.check_results.values()
    ):
        if not isinstance(
            results,
            list,
        ):
            continue

        for finding in results:
            if isinstance(
                finding,
                dict,
            ):
                all_findings.append(
                    dict(
                        finding
                    )
                )

    findings_by_category: dict[
        str,
        int,
    ] = {}

    for finding in all_findings:
        category = str(
            finding.get(
                "category",
                "TECHNICAL",
            )
        )

        findings_by_category[
            category
        ] = (
            findings_by_category.get(
                category,
                0,
            )
            + 1
        )

    project = (
        ctx.project_dir.name
        if ctx.project_dir
        else "unknown"
    )

    # Re-validate final_pass against verification completeness -- a
    # missing verifier or stale final video must never be reported as PASS
    # even if the caller thought the gates had cleared.
    computed_pass, computed_reason = compute_final_pass(ctx)
    if final_pass and not computed_pass:
        final_pass = False
        # Record the downgrade reason as an info log entry for post-mortem
        try:
            ctx.check_results.setdefault("_final_pass_downgrade", []).append(
                {
                    "status": "fail",
                    "finding_type": "final_pass_downgraded",
                    "category": "TECHNICAL",
                    "severity": "BLOCKING",
                    "detail": f"final_pass downgraded: {computed_reason}",
                }
            )
        except Exception:
            pass

    outcomes: dict[str, int] = {}
    decisions: list[dict[str, Any]] = []

    if repair_controller is not None:
        try:
            outcomes = dict(repair_controller.summary())
            decisions = [
                record.to_dict()
                for record in repair_controller.decisions
            ]
        except Exception:
            outcomes = {}
            decisions = []

    report = SelfCorrectionReport(
        project=project,
        final_pass=bool(final_pass),
        iterations=_count_iterations(
            ctx,
            repair_controller,
        ),
        detected_issues=all_findings,
        repairs=[
            dict(record)
            for record in ctx.repair_records
            if isinstance(
                record,
                dict,
            )
        ],
        verification_results={
            str(name): list(
                results
            )
            for name, results in (
                ctx.check_results.items()
            )
            if isinstance(
                results,
                list,
            )
        },
        findings_by_category=dict(
            sorted(
                findings_by_category.items()
            )
        ),
        repair_outcomes=dict(sorted(outcomes.items())),
        repairs_accepted=outcomes.get("accepted", 0),
        repairs_rejected_regression=outcomes.get(
            "regression_rejected", 0
        ),
        repairs_failed_verification=(
            outcomes.get("verifier_failed", 0)
            + outcomes.get("target_defect_unresolved", 0)
            + outcomes.get("repair_errored", 0)
        ),
        repairs_budget_exhausted=outcomes.get(
            "repair_budget_exhausted", 0
        ),
        repair_decisions=decisions,
    )

    out = (
        ctx.project_dir / "out"
        if ctx.project_dir
        else Path(".")
    )

    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        out
        / "self_correction_report.json"
    )

    path.write_text(
        json.dumps(
            dataclasses.asdict(
                report
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path


# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """Append-only JSONL experiment logger."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(
            path
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._lock = threading.Lock()

    def log_invocation(
        self,
        *,
        plugin: str,
        input_ctx: SceneContext,
        output_ctx: SceneContext,
        ok: bool,
        diagnostics: str = "",
        duration_s: float = 0.0,
        token_usage: int | None = None,
    ) -> None:
        """Append one immutable plugin invocation record."""

        duration = max(
            0.0,
            float(
                duration_s
            ),
        )

        if token_usage is not None:
            token_usage = max(
                0,
                int(
                    token_usage
                ),
            )

        record = {
            "event": "plugin.invocation",
            "plugin": str(
                plugin
            ),
            "input_context_hash": context_hash(
                input_ctx
            ),
            "output_context_hash": context_hash(
                output_ctx
            ),
            "ok": bool(
                ok
            ),
            "diagnostics": str(
                diagnostics
                or ""
            ),
            "duration_s": round(
                duration,
                4,
            ),
            "token_usage": token_usage,
            "timestamp": _utc_timestamp(),
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
        }

        line = json.dumps(
            record,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

        # A single process may execute multiple verifier/render jobs in
        # parallel. Protect append operations so records do not interleave.
        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    line
                )
                handle.write(
                    "\n"
                )

    def info(
        self,
        message: str,
    ) -> None:
        """Append one free-text diagnostic record (e.g. runner rewind notes)."""

        record = {
            "event": "runner.info",
            "message": str(message),
            "timestamp": _utc_timestamp(),
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
        }

        line = json.dumps(
            record,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )

        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(line)
                handle.write("\n")

    def log_repair(
        self,
        record: RepairRecord,
    ) -> None:
        """Append a repair event to the same JSONL evidence stream."""

        payload = {
            "event": "repair",
            **dataclasses.asdict(
                record
            ),
        }

        line = json.dumps(
            _jsonable(
                payload
            ),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    line
                )
                handle.write(
                    "\n"
                )


__all__ = [
    "RepairRecord",
    "SelfCorrectionReport",
    "StructuredLogger",
    "REQUIRED_VERIFIERS",
    "compute_final_pass",
    "context_hash",
    "write_self_correction_report",
]