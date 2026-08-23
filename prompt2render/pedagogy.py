"""Pedagogy review and revision helpers for the harness.

The reviewer is intentionally video-level rather than one request per scene.
It combines deterministic structural checks with an optional single LLM review.

The revision path is deliberately conservative:
    review -> revise -> re-review

A revision is never considered successful merely because the LLM returned a
replacement. The revised script must be reviewed again by the verifier.

Malformed or unavailable model responses never overwrite the user's script.
Unexpected programming errors are allowed to propagate so they are not silently
converted into false pedagogy passes.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import llm
from .project import Script, parse_script


def _section_payload(script: Script) -> list[dict]:
    """Convert a Script into the compact representation sent to the reviewer."""
    return [
        {
            "index": s.index,
            "title": s.title,
            "animation": s.anim,
            "narration": s.narration,
        }
        for s in script.sections
    ]


def depth_profile(script: Script) -> str:
    """Determine the requested pedagogical depth."""
    configured = os.environ.get("P2R_PEDAGOGY_DEPTH", "auto").strip().lower()

    if configured in {"brief", "standard", "deep"}:
        return configured

    text = f"{script.title} {script.meta.get('topic', '')}".lower()

    complex_markers = (
        "algorithm",
        "proof",
        "complexity",
        "recursion",
        "calculus",
        "probability",
        "data structure",
        "machine learning",
        "distributed",
        "operating system",
    )

    return "deep" if any(x in text for x in complex_markers) else "standard"


def deterministic_review(script: Script) -> dict:
    """Check pedagogical requirements that do not need subject-matter knowledge."""
    issues: list[dict] = []
    sections = script.sections

    if not sections:
        issues.append(
            {
                "severity": "blocking",
                "category": "structure",
                "issue": "script has no sections",
            }
        )

    for sec in sections:
        if not sec.narration.strip():
            issues.append(
                {
                    "severity": "blocking",
                    "category": "narration",
                    "section": sec.index,
                    "issue": "section has no narration",
                }
            )

        if not sec.anim.strip():
            issues.append(
                {
                    "severity": "blocking",
                    "category": "animation",
                    "section": sec.index,
                    "issue": "section has no ANIM brief",
                }
            )

        words = len(sec.narration.split())

        if words > 240:
            issues.append(
                {
                    "severity": "warning",
                    "category": "pacing",
                    "section": sec.index,
                    "issue": (
                        f"section has {words} words; split or add "
                        "progressive states"
                    ),
                }
            )

        if words < 18:
            issues.append(
                {
                    "severity": "warning",
                    "category": "depth",
                    "section": sec.index,
                    "issue": (
                        "section is very short; add the why, a concrete "
                        "value, or a transition"
                    ),
                }
            )

    if len(sections) == 1 and len(sections[0].narration.split()) > 180:
        issues.append(
            {
                "severity": "warning",
                "category": "structure",
                "issue": (
                    "one long section should usually be split into "
                    "teachable steps"
                ),
            }
        )

    blocking = sum(i["severity"] == "blocking" for i in issues)
    warnings = sum(i["severity"] == "warning" for i in issues)

    return {
        "version": 1,
        "profile": depth_profile(script),
        "pass": blocking == 0,
        "score": max(0, 100 - 25 * blocking - 8 * warnings),
        "issues": issues,
        "source": "deterministic",
    }


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from an LLM response.

    Accepts both raw JSON and JSON enclosed in markdown fences. If the model
    adds surrounding prose, the outermost JSON object is attempted.
    """
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            text,
            flags=re.I | re.S,
        ).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None

    return None


def _valid_review(data: dict | None) -> bool:
    """Validate the minimum schema required from an LLM pedagogy review."""
    if not isinstance(data, dict):
        return False

    if not isinstance(data.get("issues", []), list):
        return False

    if "pass" in data and not isinstance(data["pass"], bool):
        return False

    if "score" in data:
        try:
            score = float(data["score"])
        except (TypeError, ValueError):
            return False

        if not 0 <= score <= 100:
            return False

    for issue in data.get("issues", []):
        if not isinstance(issue, dict):
            return False

        severity = issue.get("severity")
        if severity not in {"blocking", "warning"}:
            return False

        if not str(issue.get("issue", "")).strip():
            return False

    return True


def review_script(script: Script, label: str = "pedagogy review") -> dict:
    """Review the complete script.

    Deterministic structural checks are authoritative. The optional LLM review
    adds subject-matter and teaching-quality feedback, but can never override
    a deterministic structural blocker.

    If the LLM is unavailable or returns malformed JSON, the deterministic
    review is returned unchanged.
    """
    base = deterministic_review(script)

    try:
        configured_keys = llm.keys()
    except SystemExit:
        return base

    if not configured_keys:
        return base

    prompt = f"""You are the senior editor for an educational explainer.

Review the complete script below for an audience of
{script.meta.get('audience', 'undergraduates')}.

The requested depth profile is {depth_profile(script)}.

Check:

- learning objective
- prerequisite ordering
- conceptual accuracy as stated
- progressive explanation
- concrete worked example
- narration-to-animation agreement
- state/value continuity
- pacing and cognitive load
- edge cases or common misconceptions
- concise recap

Do not demand a worked example when the topic genuinely needs a proof or
derivation. Instead demand the appropriate evidence for that topic.

A blocking issue is one that makes the explanation misleading, incomplete for
the requested depth, or visibly inconsistent with its animation.

Warnings are improvements that do not make the video incorrect.

Return ONLY JSON with this shape:

{{
  "pass": true,
  "score": 0-100,
  "summary": "...",
  "issues": [
    {{
      "severity": "blocking|warning",
      "section": 1,
      "category": "...",
      "issue": "...",
      "repair": "..."
    }}
  ]
}}

SCRIPT:
{json.dumps(_section_payload(script), ensure_ascii=False, indent=2)}
"""

    try:
        response = llm.complete(
            prompt,
            max_tokens=2500,
            label=label,
        )
    except SystemExit:
        return base

    result = _extract_json(response)

    if not _valid_review(result):
        return base

    assert result is not None

    result.setdefault("version", 1)
    result.setdefault("profile", depth_profile(script))
    result.setdefault("issues", [])
    result.setdefault("score", 0)
    result.setdefault(
        "pass",
        not any(
            isinstance(i, dict) and i.get("severity") == "blocking"
            for i in result["issues"]
        ),
    )
    result["source"] = "llm+deterministic"

    # Deterministic structural blockers are authoritative.
    base_blockers = [
        i for i in base["issues"]
        if i.get("severity") == "blocking"
    ]

    if base_blockers:
        result["pass"] = False
        result["issues"] = base_blockers + list(result.get("issues", []))

    return result


def _validate_revisions(
    script: Script,
    revisions: list[dict],
) -> tuple[bool, str]:
    """Ensure the LLM returned a complete, structurally usable revision."""
    if not isinstance(revisions, list):
        return False, "revision response did not contain a sections list"

    expected = {s.index for s in script.sections}
    received: set[int] = set()

    for revision in revisions:
        if not isinstance(revision, dict):
            return False, "revision contains a non-object section"

        raw_index = revision.get("index")

        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return False, f"revision has invalid section index: {raw_index!r}"

        if index not in expected:
            return False, f"revision returned unknown section {index}"

        if index in received:
            return False, f"revision returned section {index} more than once"

        title = str(revision.get("title", "")).strip()
        animation = str(revision.get("animation", "")).strip()
        narration = str(revision.get("narration", "")).strip()

        if not title:
            return False, f"section {index} has no title"

        if not animation:
            return False, f"section {index} has no animation brief"

        if not narration:
            return False, f"section {index} has no narration"

        received.add(index)

    missing = expected - received

    if missing:
        return False, (
            "revision omitted section(s): "
            + ", ".join(str(i) for i in sorted(missing))
        )

    return True, ""


def _replace_sections(
    raw: str,
    script: Script,
    revisions: list[dict],
) -> str:
    """Replace complete section bodies using a validated revision list."""
    by_index = {
        int(r["index"]): r
        for r in revisions
    }

    lines = raw.splitlines(keepends=True)

    heads: list[tuple[int, int, str]] = []
    head_re = re.compile(r"^(##)\s+(\d+)\s*[-–—.:]?\s*(.*)$")

    for pos, line in enumerate(lines):
        match = head_re.match(line.rstrip("\n"))
        if match:
            heads.append(
                (
                    pos,
                    int(match.group(2)),
                    match.group(3).strip(),
                )
            )

    if not heads:
        return raw

    expected = {s.index for s in script.sections}

    if {index for _, index, _ in heads} != expected:
        return raw

    out = list(lines)

    for pos_idx in range(len(heads) - 1, -1, -1):
        start, index, old_title = heads[pos_idx]
        end = (
            heads[pos_idx + 1][0]
            if pos_idx + 1 < len(heads)
            else len(lines)
        )

        sec = next(
            (s for s in script.sections if s.index == index),
            None,
        )
        revision = by_index.get(index)

        if not sec or not revision:
            continue

        title = str(
            revision.get("title") or sec.title
        ).strip()

        animation = str(
            revision.get("animation") or sec.anim
        ).strip()

        narration = str(
            revision.get("narration") or sec.narration
        ).strip()

        replacement = [
            f"## {index} - {title}\n",
            f"> ANIM: {animation}\n",
            "\n",
            f"{narration}\n",
            "\n",
        ]

        out[start:end] = replacement

    return "".join(out)


def revise_script(
    proj: Path,
    script: Script,
    review: dict,
    label: str = "pedagogy revision",
) -> tuple[Script, dict]:
    """Attempt one conservative LLM revision.

    The function does not claim that the revision fixed the review. The caller
    must run review_script() again on the returned Script.
    """
    if review.get("pass"):
        return script, review

    try:
        configured_keys = llm.keys()
    except SystemExit:
        return script, review

    if not configured_keys:
        return script, review

    prompt = f"""You are revising an educational explainer script.

Keep the topic, audience ({script.meta.get('audience', 'undergraduates')}),
and factual intent.

Repair the listed pedagogy issues without inflating every section.

Use the {review.get('profile', 'standard')} depth profile.

Preserve concrete values across sections when an example continues.

Each animation brief must describe visible state changes that the narration
supports.

Math may remain in LaTeX delimiters for display; it will be converted
separately for speech.

Return ONLY JSON:

{{
  "sections": [
    {{
      "index": 1,
      "title": "...",
      "animation": "...",
      "narration": "..."
    }}
  ]
}}

You MUST return every existing section exactly once.

Do not create or delete sections unless explicitly required by a listed
structure issue.

ISSUES:
{json.dumps(review.get('issues', []), ensure_ascii=False, indent=2)}

CURRENT SCRIPT:
{json.dumps(_section_payload(script), ensure_ascii=False, indent=2)}
"""

    try:
        response = llm.complete(
            prompt,
            max_tokens=5000,
            label=label,
        )
    except SystemExit:
        return script, review

    data = _extract_json(response)

    if not isinstance(data, dict):
        return script, review

    revisions = data.get("sections", [])

    valid, reason = _validate_revisions(script, revisions)

    if not valid:
        return script, review

    raw_path = proj / "script.md"

    try:
        raw = raw_path.read_text(encoding="utf-8")
    except OSError:
        return script, review

    updated = _replace_sections(
        raw,
        script,
        revisions,
    )

    # Never write if replacement failed to produce a meaningful change.
    if updated == raw:
        return script, review

    try:
        raw_path.write_text(
            updated,
            encoding="utf-8",
        )
    except OSError:
        return script, review

    revised = parse_script(raw_path)

    # Basic post-write sanity check. If parsing produced a structurally
    # different script, restore the original file rather than accepting
    # an unsafe partial mutation.
    if len(revised.sections) != len(script.sections):
        raw_path.write_text(raw, encoding="utf-8")
        return script, review

    expected_indices = {s.index for s in script.sections}
    revised_indices = {s.index for s in revised.sections}

    if revised_indices != expected_indices:
        raw_path.write_text(raw, encoding="utf-8")
        return script, review

    return revised, review


def revise_and_rereview(
    proj: Path,
    script: Script,
    review: dict,
    *,
    label: str = "pedagogy self-correction",
) -> tuple[Script, dict, bool]:
    """Perform one review -> revision -> re-review cycle.

    Returns:
        revised_script
        new_review
        changed_and_passed

    A revision is considered successful only when the fresh review passes.
    """
    revised_script, original_review = revise_script(
        proj,
        script,
        review,
        label=f"{label}: revision",
    )

    if revised_script is script:
        return script, original_review, False

    new_review = review_script(
        revised_script,
        label=f"{label}: re-review",
    )

    return revised_script, new_review, bool(new_review.get("pass"))