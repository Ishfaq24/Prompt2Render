"""End-to-end demonstration of the artifact-centric self-correction loop.

    GENERATE -> RENDER -> VERIFY -> EVIDENCE -> TARGETED REPAIR
        -> REGRESSION CHECK -> ACCEPT/ROLLBACK

Runs the REAL RepairController over a synthetic scene with a scripted
generator and scripted verifiers -- no LLM keys, no renderer needed.

Demonstrated:

1. Revision 1 has a caption overflow. The verifier detects it. The repair
   planner builds an evidence bundle + change contract (scope LOCAL, locked
   properties). The targeted repair modifies only the caption. Revision 2
   is ACCEPTED; previously-passing properties remain passing; every
   per-revision artifact (evidence.json / repair.json / generation.json)
   and the accepted/ pointer are written.

2. A deliberately regressive revision 3 "fixes" a new finding but trashes
   the previously-clean layout dimension. The harness detects the hard
   dimension regression, REJECTS the candidate, rolls back to the accepted
   revision, and records everything in revisions.json + events.jsonl.

Run:  python demo_self_correction.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from prompt2render.harness.context import (
    CodeArtifact,
    RenderArtifact,
    SceneContext,
    ScenePlanEntry,
)
from prompt2render.harness.journal import EventJournal
from prompt2render.harness.repair_controller import RepairController
from prompt2render.harness.revision_history import load_revision_history

STEM = "06"

SOURCE_REV1 = """from manim import *
class Scene06(Scene):
    def construct(self):
        title = Text("Binary Search", font_size=44).to_edge(UP, buff=0.35)
        arr = VGroup(*[Square(side_length=0.6) for _ in range(8)]).arrange(RIGHT)
        caption = Text("We halve the search space each step", font_size=24)
        caption.move_to([0, CAPPTION_Y, 0])
        self.play(Write(title), FadeIn(arr), Write(caption))
        self.wait(1.0)
"""

SOURCE_REV2 = """from manim import *
class Scene06(Scene):
    def construct(self):
        title = Text("Binary Search", font_size=44).to_edge(UP, buff=0.35)
        arr = VGroup(*[Square(side_length=0.6) for _ in range(8)]).arrange(RIGHT)
        caption = Text("We halve the search space each step", font_size=24)
        caption.move_to([0, -3.2, 0])
        self.play(Write(title), FadeIn(arr), Write(caption))
        self.wait(1.0)
"""

# "Fixes" the trigger finding but introduces layout crowding everywhere --
# the canonical score-gaming failure the acceptance policy must reject.
SOURCE_REV3_REGRESSIVE = """from manim import *
class Scene06(Scene):
    def construct(self):
        title = Text("Binary Search", font_size=44).to_edge(UP, buff=0.35)
        arr = VGroup(*[Square(side_length=0.2) for _ in range(8)]).arrange(RIGHT)
        caption = Text("ok", font_size=10).move_to([0, -3.2, 0])
        self.play(Write(title), FadeIn(arr), Write(caption))
        self.wait(1.0)
"""


class _Plan:
    def __init__(self, finding_type):
        self.finding_type = finding_type
        self.targets = ["generator_code"]
        self.routable = True


class _Router:
    def __init__(self, scripted_source, finding_type):
        self.scripted_source = scripted_source
        self.finding_type = finding_type

    def plan(self, finding, source):
        return _Plan(self.finding_type)

    def execute(self, plan, context):
        # The "LLM": writes the scripted candidate into the sidecar.
        context.candidate.code_path.write_text(self.scripted_source, encoding="utf-8")

        # The candidate render: same four frames as the accepted revision
        # (a caption fix does not legitimately change the frame inventory).
        sidecar = context.candidate.render_dir
        manifest = [
            {"i": i, "name": f"state_{i}", "png": f"{i}.png"} for i in range(4)
        ]
        (sidecar / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        context.render_artifacts[STEM] = RenderArtifact(
            stem=STEM, outdir=sidecar, manifest=manifest,
            source_revision=context.candidate.revision,
        )

        class _Execution:
            ok = True
            targets_run = ["generator_code"]
            errors = []

        return _Execution()

    def emit(self, name, **kw):
        pass


class _ScriptedVerifier:
    """Returns scripted findings for every scene-scoped verifier."""

    name = "verifier_layout"

    def __init__(self, findings_by_verifier):
        self.findings_by_verifier = findings_by_verifier

    def enabled(self):
        return True

    def run(self, ctx):
        for verifier_name, findings in self.findings_by_verifier.items():
            ctx.check_results[verifier_name] = [dict(f) for f in findings]
        return ctx


def _seed(tmp_path: Path) -> SceneContext:
    script_path = tmp_path / "script.md"
    script_path.write_text(
        "# Binary Search\n\n## 6 - Complexity\n\n"
        "> ANIM: show the halving search space\n\n"
        "We halve the search space each step.\n",
        encoding="utf-8",
    )

    canonical = tmp_path / "build" / "scenes" / f"scene_{STEM}.py"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(SOURCE_REV1, encoding="utf-8")

    render_dir = tmp_path / "build" / "scenes" / STEM
    render_dir.mkdir(parents=True, exist_ok=True)
    manifest = [{"i": i, "name": f"state_{i}", "png": f"{i}.png"} for i in range(4)]
    (render_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ctx = SceneContext(project_dir=tmp_path, prompt=script_path)
    ctx.scene_plan = [
        ScenePlanEntry(index=6, stem=STEM, title="Complexity",
                       anim="show the halving search space",
                       narration_text="We halve the search space each step.")
    ]
    ctx.scene_versions[STEM] = 1
    ctx.code_artifacts[STEM] = CodeArtifact(
        stem=STEM, path=canonical, generated=True, accepted=True, revision=1
    )
    ctx.render_artifacts[STEM] = RenderArtifact(
        stem=STEM, outdir=render_dir, manifest=manifest, source_revision=1
    )
    return ctx


def _caption_overflow_finding() -> dict:
    return {
        "stem": STEM, "status": "fail", "finding_type": "caption_overflow",
        "category": "LAYOUT", "severity": "BLOCKING",
        "detail": "caption exceeds the safe area at the bottom of the frame",
        "location": {"file": f"scene_{STEM}.py", "line": 6},
        "fix": "move the caption into the caption zone (y >= -3.4)",
        "finding_id": "layout-000001",
    }


def main() -> None:
    print("=" * 72)
    print("Prompt2Render: artifact-centric self-correction -- end-to-end demo")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ctx = _seed(tmp_path)
        journal = EventJournal(tmp_path / "events.jsonl")

        # ---------------------------------------------------------- cycle 1
        print("\n[rev 1] seeded: scene has a blocking caption_overflow finding")
        ctx.check_results["verifier_layout"] = [_caption_overflow_finding()]
        ctx.check_results["verifier_semantic"] = [
            {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
             "category": "SEMANTIC"}
        ]
        ctx.check_results["verifier_temporal"] = [
            {"stem": STEM, "status": "pass", "finding_type": "temporal_match",
             "category": "TEMPORAL", "difference": 0.1}
        ]
        ctx.check_results["verifier_execution"] = [
            {"stem": STEM, "status": "pass", "finding_type": "stage_success",
             "category": "TECHNICAL"}
        ]

        # The candidate generator applies the TARGETED fix only.
        router = _Router(SOURCE_REV2, "caption_overflow")
        clean_verifier = _ScriptedVerifier({
            "verifier_layout": [
                {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
                 "category": "LAYOUT"}
            ],
            "verifier_semantic": [
                {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
                 "category": "SEMANTIC"}
            ],
            "verifier_temporal": [
                {"stem": STEM, "status": "pass", "finding_type": "temporal_match",
                 "category": "TEMPORAL", "difference": 0.1}
            ],
            "verifier_execution": [
                {"stem": STEM, "status": "pass", "finding_type": "stage_success",
                 "category": "TECHNICAL"}
            ],
            "verifier_spatial": [],
        })

        controller = RepairController(
            router=router,
            plugins_by_name={
                "verifier_layout": clean_verifier,
                "verifier_semantic": clean_verifier,
                "verifier_spatial": clean_verifier,
                "verifier_temporal": clean_verifier,
                "verifier_execution": clean_verifier,
            },
            log_path=tmp_path / "repair_log.jsonl",
            journal=journal,
        )

        record = controller.repair_scene(
            ctx, STEM, [_caption_overflow_finding()], "verifier_layout"
        )

        print(f"[rev 2] decision: {record.decision}")
        print(f"[rev 2] repair contract (built from rev-1 evidence):")
        contract = record.repair_contract
        print(json.dumps(
            {k: contract.get(k) for k in (
                "repair_scope", "problems", "targets", "required_changes",
                "preserve", "locked_properties", "success_conditions",
                "forbidden_changes")},
            indent=2,
        ))
        assert record.decision == "accepted", record.rejection_reason
        assert ctx.scene_versions[STEM] == 2
        print("[rev 2] ACCEPTED -- previously passing layout/semantic/temporal stayed passing")

        rev2_dir = tmp_path / "build" / "revisions" / STEM / "revision_02"
        print(f"[rev 2] archived artifacts: {sorted(p.name for p in rev2_dir.iterdir())}")
        accepted_dir = tmp_path / "build" / "revisions" / STEM / "accepted"
        assert (accepted_dir / "manifest.json").exists()
        print(f"[rev 2] accepted/ pointer: "
              f"{json.loads((accepted_dir / 'manifest.json').read_text(encoding='utf-8'))['accepted_revision']}")

        # ---------------------------------------------------------- cycle 2
        print("\n[rev 3] a new TIMING finding appears; this 'repair' will cheat:")
        print("        it fixes the timing but trashes the previously-clean layout")

        trigger = {
            "stem": STEM, "status": "fail", "finding_type": "timing_mismatch",
            "category": "TEMPORAL", "severity": "BLOCKING",
            "detail": "scene duration drifts 1.8s from the narration span",
            "difference": 1.8,
            "fix": "extend self.wait so the scene matches the narration span",
        }
        # Accepted rev-2 evidence: layout still clean; temporal now failing.
        ctx.check_results["verifier_layout"] = [
            {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
             "category": "LAYOUT"}
        ]
        ctx.check_results["verifier_temporal"] = [trigger]

        router.scripted_source = SOURCE_REV3_REGRESSIVE
        router.finding_type = "timing_mismatch"

        regressive_verifier = _ScriptedVerifier({
            "verifier_layout": [
                {"stem": STEM, "status": "pass", "finding_type": "layout_audit",
                 "category": "LAYOUT"},
                # Three new advisory layout findings: layout_score 100 -> 85.
                *[
                    {"stem": STEM, "status": "warn", "severity": "WARNING",
                     "finding_type": f"crowding_{i}", "category": "LAYOUT",
                     "detail": f"elements crowded near caption zone ({i})"}
                    for i in range(3)
                ],
            ],
            "verifier_semantic": [
                {"stem": STEM, "status": "pass", "finding_type": "semantic_mismatch",
                 "category": "SEMANTIC"}
            ],
            "verifier_temporal": [
                {"stem": STEM, "status": "pass", "finding_type": "temporal_match",
                 "category": "TEMPORAL", "difference": 0.1}
            ],
            "verifier_execution": [
                {"stem": STEM, "status": "pass", "finding_type": "stage_success",
                 "category": "TECHNICAL"}
            ],
            "verifier_spatial": [],
        })
        controller.plugins_by_name = {
            "verifier_layout": regressive_verifier,
            "verifier_semantic": regressive_verifier,
            "verifier_spatial": regressive_verifier,
            "verifier_temporal": regressive_verifier,
            "verifier_execution": regressive_verifier,
        }

        record3 = controller.repair_scene(ctx, STEM, [trigger], "verifier_layout")

        print(f"[rev 3] decision: {record3.decision}")
        print(f"[rev 3] reason:   {record3.rejection_reason}")
        assert record3.decision == "regression_rejected"
        assert ctx.scene_versions[STEM] == 2, "rollback must preserve rev 2"
        canonical = (tmp_path / "build" / "scenes" / f"scene_{STEM}.py").read_text(encoding="utf-8")
        assert canonical == SOURCE_REV2, "accepted source must survive rejection verbatim"
        print("[rev 3] REJECTED -- accepted rev 2 preserved verbatim (rollback)")

        # -------------------------------------------------------- artifacts
        print("\nRevision history (build/harness/revisions.json):")
        history = load_revision_history(tmp_path)
        for entry in history["scenes"][STEM]["revisions"]:
            print(
                f"  rev {entry['revision']} (parent {entry['parent_revision']}) "
                f"decision={entry['decision']} reason={entry['reason']!r}"
            )
        assert history["scenes"][STEM]["accepted"] == 2

        print("\nJournal events with failure attribution:")
        for event in journal.read(scene_id=STEM):
            if event["event_type"] in ("scene.accepted", "scene.rollback"):
                attribution = (event.get("payload") or {}).get("attribution") or {}
                print(
                    f"  {event['event_type']} rev={event['revision']} "
                    f"cause={attribution.get('cause')} "
                    f"detected_by={attribution.get('detected_by')} "
                    f"result={attribution.get('result')}"
                )

        print("\nDEMONSTRATION COMPLETE")
        print("  targeted repair fixed the reported failure  -> ACCEPTED")
        print("  regressive candidate broke a locked property -> REJECTED + ROLLBACK")
        print("  accepted artifacts survived both cycles intact")


if __name__ == "__main__":
    main()
