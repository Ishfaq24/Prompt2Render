"""Regression guard: verifier_semantic and verifier_layout must review
independent scenes concurrently, not one scene at a time.

Before this fix, each scene's vision-LLM round trip ran strictly
sequentially in a for-loop, so N scenes cost N times one call's latency --
minutes per pipeline run in practice. Both verifiers now dispatch
independent scenes' LLM calls to a thread pool. These tests fake
`llm.complete` with a fixed sleep and assert the wall-clock time for
several scenes is well under the fully-serial sum, which only holds if the
calls actually overlap.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from prompt2render.harness.context import CodeArtifact, SceneContext, ScenePlanEntry

N_SCENES = 4
SLEEP_S = 0.15


def _touch(path: Path, mtime: float, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def test_verifier_semantic_reviews_scenes_concurrently(tmp_path, monkeypatch):
    import prompt2render.harness.plugins.verifier_semantic as sem

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [
        ScenePlanEntry(index=i, stem=f"{i:02d}", title=f"T{i}")
        for i in range(1, N_SCENES + 1)
    ]
    for i in range(1, N_SCENES + 1):
        code_file = _touch(tmp_path / f"scene_{i:02d}.py", 1000.0, b"pass")
        ctx.code_artifacts[f"{i:02d}"] = CodeArtifact(stem=f"{i:02d}", path=code_file)

    monkeypatch.setattr(sem.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(sem.llm, "client", lambda k: MagicMock())

    def slow_complete(*a, **kw):
        time.sleep(SLEEP_S)
        return '{"status": "pass"}'

    monkeypatch.setattr(sem.llm, "complete", slow_complete)

    start = time.monotonic()
    sem.VerifierSemanticPlugin().run(ctx)
    elapsed = time.monotonic() - start

    serial_time = SLEEP_S * N_SCENES
    assert elapsed < serial_time * 0.75, (
        f"expected concurrent reviews to beat serial time ({serial_time:.2f}s), "
        f"took {elapsed:.2f}s -- looks like scenes ran one at a time"
    )


def test_verifier_layout_reviews_scenes_concurrently(tmp_path, monkeypatch):
    import prompt2render.harness.plugins.verifier_layout as lay

    ctx = SceneContext(project_dir=tmp_path)
    ctx.scene_plan = [
        ScenePlanEntry(index=i, stem=f"{i:02d}", title=f"T{i}")
        for i in range(1, N_SCENES + 1)
    ]
    for i in range(1, N_SCENES + 1):
        stem = f"{i:02d}"
        code_file = _touch(tmp_path / f"scene_{stem}.py", 1000.0, b"pass")
        ctx.code_artifacts[stem] = CodeArtifact(stem=stem, path=code_file)
        _touch(
            tmp_path / "build" / "manim" / "previews" / f"Scene{stem}.png",
            2000.0,
            b"fake_png_data",
        )

    monkeypatch.setattr(lay.llm, "keys", lambda: ["fake_key"])
    monkeypatch.setattr(lay.llm, "client", lambda k: MagicMock())

    def slow_complete(*a, **kw):
        time.sleep(SLEEP_S)
        return '{"status": "pass"}'

    monkeypatch.setattr(lay.llm, "complete", slow_complete)

    start = time.monotonic()
    lay.VerifierLayoutPlugin().run(ctx)
    elapsed = time.monotonic() - start

    serial_time = SLEEP_S * N_SCENES
    assert elapsed < serial_time * 0.75, (
        f"expected concurrent reviews to beat serial time ({serial_time:.2f}s), "
        f"took {elapsed:.2f}s -- looks like scenes ran one at a time"
    )
