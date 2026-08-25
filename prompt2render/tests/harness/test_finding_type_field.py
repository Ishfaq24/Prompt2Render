"""`finding_type` belongs to the typed Finding, not to hand-edited dicts.

The routing table keys entirely on ``finding_type``, but it was not a
``Finding`` field: every verifier had to remember to hand-add
``result["finding_type"] = ...`` to the raw dict after serialising, with
nothing to remind it. A forgotten assignment silently fell back to
``_DEFAULT_FINDING_TYPE[source_plugin]``.

The subtle part -- and the reason these tests exist -- is that an *unset*
finding_type must be ABSENT from the serialised dict rather than null.
Consumers read it as ``str(finding.get("finding_type", ""))``; a literal
None stringifies to the truthy ``"None"``, which matches no route and
would disable the fallback for every verifier that does not set it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.finding import (
    Category,
    Finding,
    Severity,
)
from prompt2render.harness.plugins.repair_router.policy import (
    StaticTableRoutingPolicy,
)


def _finding(**kw) -> Finding:
    base = dict(
        finding_id="f-1",
        scene_id="01",
        category=Category.TECHNICAL,
        severity=Severity.BLOCKING,
        message="boom",
    )
    base.update(kw)
    return Finding(**base)


def test_finding_type_is_a_real_field():
    f = _finding(finding_type="execution_failure")
    assert f.finding_type == "execution_failure"


def test_unset_finding_type_is_omitted_not_null():
    result = _finding().as_check_result()
    assert "finding_type" not in result, (
        "an unset finding_type must be absent; a null would stringify to "
        "the truthy 'None' and match no route"
    )


def test_set_finding_type_is_serialized():
    result = _finding(finding_type="execution_failure").as_check_result()
    assert result["finding_type"] == "execution_failure"


def test_unset_finding_type_still_routes_via_the_source_fallback():
    """The dict must look exactly as it did before this field existed, so
    repair_router's `finding.get("finding_type") or _DEFAULT_FINDING_TYPE`
    fallback keeps working."""
    result = _finding().as_check_result()
    resolved = result.get("finding_type") or "execution_failure"
    assert resolved == "execution_failure"
    assert StaticTableRoutingPolicy().decide(
        {**result, "finding_type": resolved}
    ) == ["generator_code"]


def test_typed_finding_routes_without_hand_editing_the_dict():
    result = _finding(finding_type="storyboard_failure").as_check_result()
    assert StaticTableRoutingPolicy().decide(result) == ["planner_llm"]


def test_existing_serialized_keys_are_unchanged():
    result = _finding().as_check_result()
    for key in (
        "finding_id",
        "scene_id",
        "category",
        "severity",
        "message",
        "object_id",
        "status",
        "stem",
        "detail",
    ):
        assert key in result, f"{key} disappeared from the serialized shape"
    assert result["status"] == "fail"
    assert result["stem"] == "01"
    assert result["detail"] == "boom"
