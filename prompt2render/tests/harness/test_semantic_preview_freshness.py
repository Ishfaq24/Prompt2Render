"""A preview frame is only evidence if it depicts the current code.

Regression: ``has_preview`` was a bare ``Path.exists()``. Outside a repair
cycle the verifier therefore attached whatever PNG last happened to be on
disk -- typically a render of a *previous* generation of the scene -- and
presented it to the model as evidence for layout. That yields confident
verdicts about a frame the current code never produced, in both directions:
passing a broken scene because the stale frame looked fine, or failing a
fixed scene because the stale frame still shows the old defect.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prompt2render.harness.context import CodeArtifact, SceneContext, ScenePlanEntry
from prompt2render.harness.plugins.verifier_semantic import (
    VerifierSemanticPlugin,
    _preview_is_fresh,
)


def _touch(path: Path, mtime: float, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


# ------------------------------------------------------- _preview_is_fresh --

def test_preview_newer_than_code_is_fresh(tmp_path):
    code = _touch(tmp_path / "scene_01.py", 1000.0)
    preview = _touch(tmp_path / "Scene01.png", 2000.0)
    assert _preview_is_fresh(preview, code) is True


def test_preview_older_than_code_is_stale(tmp_path):
    code = _touch(tmp_path / "scene_01.py", 2000.0)
    preview = _touch(tmp_path / "Scene01.png", 1000.0)
    assert _preview_is_fresh(preview, code) is False


def test_preview_same_age_as_code_is_fresh(tmp_path):
    # Generation and render can land in the same filesystem tick; equal
    # timestamps must not be treated as stale.
    code = _touch(tmp_path / "scene_01.py", 1500.0)
    preview = _touch(tmp_path / "Scene01.png", 1500.0)
    assert _preview_is_fresh(preview, code) is True


def test_missing_file_is_not_fresh(tmp_path):
    code = _touch(tmp_path / "scene_01.py", 1000.0)
    assert _preview_is_fresh(tmp_path / "absent.png", code) is False


# ------------------------------------------------------------- integration --

def _run_with_preview_age(tmp_path, monkeypatch, *, preview_mtime, code_mtime):
    """Run the verifier once and return ``(call_kwargs, prompt_text)``.

    ``llm.complete`` takes the prompt positionally, so it is not in kwargs.
    """
    import prompt2render.harness.plugins.verifier_semantic as sem

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [ScenePlanEntry(index=1, stem="01", title="T")]

    code_file = _touch(tmp_path / "scene_01.py", code_mtime, b"pass")
    ctx.code_artifacts["01"] = CodeArtifact(stem="01", path=code_file)

    _touch(
        tmp_path / "build" / "manim" / "previews" / "Scene01.png",
        preview_mtime,
        b"fake_png_data",
    )

    monkeypatch.setattr(sem.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(sem.llm, "client", lambda k: MagicMock())
    complete = MagicMock(return_value='{"status": "pass"}')
    monkeypatch.setattr(sem.llm, "complete", complete)

    VerifierSemanticPlugin().run(ctx)

    complete.assert_called_once()
    call = complete.call_args
    prompt = call.args[0] if call.args else call.kwargs.get("prompt", "")
    return call.kwargs, prompt


def test_stale_preview_is_not_attached_as_evidence(tmp_path, monkeypatch):
    kwargs, prompt = _run_with_preview_age(
        tmp_path, monkeypatch, preview_mtime=1000.0, code_mtime=2000.0
    )
    assert kwargs["image_base64"] is None
    # And the prompt must not invite the model to judge layout from a frame
    # it was never given.
    assert "No preview frame is available" in prompt


def test_fresh_preview_is_still_attached(tmp_path, monkeypatch):
    kwargs, prompt = _run_with_preview_age(
        tmp_path, monkeypatch, preview_mtime=2000.0, code_mtime=1000.0
    )
    import base64

    assert kwargs["image_base64"] is not None
    assert base64.b64decode(kwargs["image_base64"]) == b"fake_png_data"
    assert "A preview frame is attached" in prompt
