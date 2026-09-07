"""Unit tests for VerifierCognitivePlugin in the Prompt2Render harness."""

from __future__ import annotations

import tempfile
from pathlib import Path

from prompt2render.harness.context import (
    CodeArtifact,
    NarrationEntry,
    SceneContext,
    ScenePlanEntry,
)
from prompt2render.harness.plugins import (
    REGISTRY,
    pipeline_registry,
    validate_registry,
)
from prompt2render.harness.plugins.verifier_cognitive import VerifierCognitivePlugin


def test_registry_registration():
    """Ensure verifier_cognitive is cleanly registered in the harness REGISTRY."""
    validate_registry()
    assert "verifier_cognitive" in REGISTRY
    assert "verifier_cognitive" in pipeline_registry()
    assert REGISTRY["verifier_cognitive"] is VerifierCognitivePlugin


def test_verifier_cognitive_pass():
    """Test clean execution where narration, Mobjects, and signaling are balanced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = Path(tmpdir) / "scene_01.py"
        code_file.write_text(
            """
class Scene01(Scene):
    def construct(self):
        resolver_node = Circle()
        root_server = Square()
        title = Text("DNS Lookup")
        self.play(Create(resolver_node), Create(root_server))
        self.play(Indicate(resolver_node))
        self.play(Circumscribe(root_server))
""",
            encoding="utf-8",
        )

        context = SceneContext()
        context.scene_plan = [
            ScenePlanEntry(
                index=1,
                stem="01",
                title="DNS Lookup",
                narration_text=(
                    "The DNS Resolver initiates a query to the Root Server "
                    "to discover the authoritative nameserver addresses."
                ),
            )
        ]
        context.code_artifacts = {
            "01": CodeArtifact(stem="01", path=code_file, generated=True, accepted=True)
        }

        plugin = VerifierCognitivePlugin()
        context = plugin.run(context)

        findings = context.check_results.get(plugin.name, [])
        assert len(findings) > 0
        # No redundancy warning
        assert not any(f.get("finding_type") == "redundancy_overload" for f in findings)
        # Should record cognitive signaling pass
        assert any(f.get("finding_type") == "cognitive_signaling_pass" for f in findings)


def test_verifier_cognitive_redundancy_warning():
    """Test detection of redundant on-screen text overloading the phonological loop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = Path(tmpdir) / "scene_02.py"
        # Code containing verbose cards that verbatim duplicate the narration
        code_file.write_text(
            """
class Scene02(Scene):
    def construct(self):
        txt1 = Text("The quick brown fox jumps over the lazy dog repeatedly and decisively.")
        txt2 = Text("Another verbose sentence displayed on screen while the speaker speaks.")
        txt3 = Text("Yet another paragraph of full text duplicating the spoken voice.")
        self.play(Write(txt1))
""",
            encoding="utf-8",
        )

        context = SceneContext()
        context.scene_plan = [
            ScenePlanEntry(
                index=1,
                stem="02",
                title="Redundancy Test",
                narration_text="The quick brown fox jumps over the lazy dog repeatedly.",
            )
        ]
        context.code_artifacts = {
            "02": CodeArtifact(stem="02", path=code_file, generated=True, accepted=True)
        }

        plugin = VerifierCognitivePlugin()
        context = plugin.run(context)

        findings = context.check_results.get(plugin.name, [])
        assert any(f.get("finding_type") == "redundancy_overload" for f in findings)
        redundancy_findings = [f for f in findings if f.get("finding_type") == "redundancy_overload"]
        assert redundancy_findings[0]["severity"] == "WARNING"
        assert redundancy_findings[0]["status"] == "warn"


def test_verifier_cognitive_split_attention_info():
    """Test detection of un-signaled technical concepts when visual elements exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = Path(tmpdir) / "scene_03.py"
        # Has resolver_node and root_server, but 0 signaling calls
        code_file.write_text(
            """
class Scene03(Scene):
    def construct(self):
        resolver_node = Circle()
        root_server = Square()
        self.play(Create(resolver_node), Create(root_server))
        self.wait(5)
""",
            encoding="utf-8",
        )

        context = SceneContext()
        context.scene_plan = [
            ScenePlanEntry(
                index=1,
                stem="03",
                title="Split Attention Test",
                narration_text=(
                    "The DNS Resolver initiates a query to the Root Server "
                    "to locate the top level domain records."
                ),
            )
        ]
        context.code_artifacts = {
            "03": CodeArtifact(stem="03", path=code_file, generated=True, accepted=True)
        }

        plugin = VerifierCognitivePlugin()
        context = plugin.run(context)

        findings = context.check_results.get(plugin.name, [])
        assert any(f.get("finding_type") == "split_attention" for f in findings)
