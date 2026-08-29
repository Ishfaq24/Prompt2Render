"""Evidence bundles, repair types, scopes, and change contracts (Phases 4-8)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness import evidence
from prompt2render.harness.context import SceneContext

STEM = "06"


def _ctx(tmp_path: Path) -> SceneContext:
    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_versions[STEM] = 1
    ctx.check_results["verifier_execution"] = [
        {
            "stem": STEM,
            "status": "fail",
            "finding_type": "execution_failure",
            "category": "SEMANTIC",
            "severity": "BLOCKING",
            "detail": "CAPPTION_Y is undefined",
            "location": {"file": f"scene_{STEM}.py", "line": 676},
            "fix": "replace CAPPTION_Y with CAPTION_Y",
        }
    ]
    ctx.check_results["verifier_layout"] = [
        {"stem": STEM, "status": "pass", "finding_type": "layout_audit", "category": "LAYOUT"}
    ]
    ctx.check_results["verifier_semantic"] = [
        {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch", "category": "SEMANTIC"}
    ]
    ctx.check_results["verifier_temporal"] = [
        {"stem": STEM, "status": "pass", "finding_type": "temporal_match",
         "category": "TEMPORAL", "difference": 0.1}
    ]
    return ctx


# --------------------------------------------------------------- bundle ---

def test_bundle_checks_map_and_status():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)

    assert bundle["scene_id"] == STEM
    assert bundle["revision"] == 1
    assert bundle["status"] == "fail"
    assert bundle["checks"]["execution"] == "fail"
    assert bundle["checks"]["layout"] == "pass"
    assert bundle["checks"]["semantic"] == "pass"
    assert bundle["checks"]["temporal"] == "pass"
    assert bundle["blocking_count"] == 1


def test_bundle_locked_properties_and_must_preserve():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)

    locked = bundle["locked_properties"]
    assert locked["layout"] is True
    assert locked["semantic"] is True
    assert locked["execution"] is False

    assert "layout" in bundle["passing_properties"]
    assert "execution" not in bundle["passing_properties"]

    # Passing dimensions contribute their preservation targets.
    assert "object positions" in bundle["must_preserve"]
    assert "animation timing" in bundle["must_preserve"]


def test_bundle_findings_carry_repair_type():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)

    failing = [f for f in bundle["findings"] if f.get("status") == "fail"]
    assert failing
    assert failing[0]["repair_type"] == "code_local_repair"


def test_bundle_verifier_specific_fields_preserved():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)

    failing = [f for f in bundle["findings"] if f.get("status") == "fail"][0]
    assert failing["location"] == {"file": f"scene_{STEM}.py", "line": 676}
    assert failing["fix"] == "replace CAPPTION_Y with CAPTION_Y"


# ---------------------------------------------------------- repair types ---

def test_repair_type_mapping_covers_spec_classes():
    table = evidence.REPAIR_TYPE_BY_FINDING_TYPE
    assert table["execution_failure"] == "code_local_repair"
    assert table["undefined_identifier"] == "code_local_repair"
    assert table["invalid_manim_api"] == "manim_api_repair"
    assert table["text_overlap"] == "typography_repair"
    assert table["caption_overflow"] == "caption_layout_repair"
    assert table["semantic_mismatch"] == "semantic_repair"
    assert table["missing_visual_concept"] == "scene_content_repair"
    assert table["timing_mismatch"] == "timing_repair"
    assert table["pedagogy_review"] == "pedagogical_repair"
    assert table["motion_absence"] == "visual_refinement"


# --------------------------------------------------------------- scopes ---

def test_scope_local_for_code_level_failures():
    findings = [{"finding_type": "undefined_identifier", "stem": STEM}]
    assert evidence.classify_repair_scope(findings) == evidence.SCOPE_LOCAL


def test_scope_regional_for_layout_failures():
    findings = [{"finding_type": "crowding", "stem": STEM}]
    assert evidence.classify_repair_scope(findings) == evidence.SCOPE_REGIONAL


def test_scope_local_for_caption_failures():
    # Caption repairs act on one component, so they stay LOCAL.
    findings = [{"finding_type": "caption_collision", "stem": STEM}]
    assert evidence.classify_repair_scope(findings) == evidence.SCOPE_LOCAL


def test_scope_scene_for_semantic_failures():
    findings = [
        {"finding_type": "caption_collision", "stem": STEM},
        {"finding_type": "semantic_mismatch", "stem": STEM},
    ]
    assert evidence.classify_repair_scope(findings) == evidence.SCOPE_SCENE


def test_scope_local_when_locations_present():
    findings = [
        {"finding_type": "mystery", "stem": STEM,
         "location": {"file": "scene_06.py", "line": 3}},
    ]
    assert evidence.classify_repair_scope(findings) == evidence.SCOPE_LOCAL


# ------------------------------------------------------------- contract ---

def test_change_contract_schema():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)
    blocking = [f for f in bundle["findings"] if f.get("status") == "fail"]

    contract = evidence.build_change_contract(
        stem=STEM, parent_revision=1, findings=blocking, bundle=bundle
    )

    assert contract["scene_id"] == STEM
    assert contract["parent_revision"] == 1
    assert contract["repair_scope"] == evidence.SCOPE_LOCAL
    assert "CAPPTION_Y is undefined" in contract["problems"]
    assert any("line 676" in target for target in contract["targets"])
    assert "replace CAPPTION_Y with CAPTION_Y" in contract["required_changes"]
    assert "object positions" in contract["preserve"]
    assert contract["locked_properties"]["layout"] is True
    assert any("layout remains passing" in s for s in contract["success_conditions"])
    assert any("do not redesign" in f for f in contract["forbidden_changes"])


def test_contract_prompt_text_contains_locked_and_forbidden():
    ctx = _ctx(Path("."))
    bundle = evidence.build_evidence_bundle(ctx, STEM)
    blocking = [f for f in bundle["findings"] if f.get("status") == "fail"]

    contract = evidence.build_change_contract(
        stem=STEM, parent_revision=1, findings=blocking, bundle=bundle
    )
    text = evidence.contract_prompt_text(contract)

    assert "CHANGE CONTRACT" in text
    assert "LOCKED PROPERTIES" in text
    assert "FORBIDDEN:" in text
    assert "smallest safe change" in text


# ---------------------------------------------------------- persistence ---

def test_revision_artifacts_written(tmp_path):
    ctx = _ctx(tmp_path)
    bundle = evidence.build_evidence_bundle(ctx, STEM, revision=2)

    evidence.write_evidence_bundle(tmp_path, STEM, 2, bundle)
    evidence.write_change_contract(
        tmp_path, STEM, 2,
        evidence.build_change_contract(
            stem=STEM, parent_revision=1,
            findings=bundle["findings"], bundle=bundle,
        ),
    )
    evidence.write_generation_meta(
        tmp_path, STEM, 2,
        evidence.build_generation_meta(
            ctx, STEM, revision=2, parent_revision=1,
            model_env="P2R_REPAIR_MODEL", model_primary="m",
            trigger_finding_type="execution_failure",
        ),
    )

    rev_dir = tmp_path / "build" / "revisions" / STEM / "revision_02"
    assert (rev_dir / "evidence.json").exists()
    assert (rev_dir / "repair.json").exists()
    assert (rev_dir / "generation.json").exists()

    generation = json.loads((rev_dir / "generation.json").read_text(encoding="utf-8"))
    assert generation["revision"] == 2
    assert generation["parent_revision"] == 1
    assert generation["model_env"] == "P2R_REPAIR_MODEL"
    assert generation["trigger_finding_type"] == "execution_failure"


def test_sync_accepted_dir_points_at_accepted_revision(tmp_path):
    from prompt2render.harness.context import CodeArtifact

    ctx = _ctx(tmp_path)

    source = tmp_path / "build" / "scenes" / f"scene_{STEM}.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# accepted scene\n")
    ctx.code_artifacts[STEM] = CodeArtifact(
        stem=STEM, path=source, generated=True, accepted=True, revision=1
    )

    # Seed the revision-1 archive with a report copy.
    rev_dir = evidence.revision_dir(tmp_path, STEM, 1)
    rev_dir.mkdir(parents=True, exist_ok=True)
    (rev_dir / "report.json").write_text("{}", encoding="utf-8")

    dest = evidence.sync_accepted_dir(ctx, STEM)

    assert dest is not None
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["accepted_revision"] == 1
    assert (dest / f"scene_{STEM}.py").exists()
    assert (dest / "report.json").exists()
