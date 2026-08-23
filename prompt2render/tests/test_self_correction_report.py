import json
from pathlib import Path

from prompt2render.harness.context import SceneContext
from prompt2render.harness.logging_ import write_self_correction_report


def test_self_correction_report_contains_findings_repairs_and_verifications(tmp_path: Path):
    ctx = SceneContext(project_dir=tmp_path)
    ctx.check_results = {
        "verifier_pedagogy": [{"status": "fail", "category": "PEDAGOGY", "detail": "missing example"}],
        "verifier_storyboard": [{"status": "pass", "category": "STORYBOARD", "detail": "valid"}],
    }
    ctx.repair_records = [{"cycle_id": 1, "outcome": "attempted", "finding_type": "pedagogy_review"}]
    path = write_self_correction_report(ctx, final_pass=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["final_pass"] is False
    assert data["iterations"] == 1
    assert len(data["detected_issues"]) == 2
    assert len(data["repairs"]) == 1
    assert "verifier_pedagogy" in data["verification_results"]
    assert data["findings_by_category"]["PEDAGOGY"] == 1
