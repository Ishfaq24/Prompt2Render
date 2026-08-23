from __future__ import annotations

from pathlib import Path

from prompt2render import scenes
from prompt2render.project import Script, Section


def test_default_retry_continues_until_scene_passes(monkeypatch, tmp_path: Path):
    script = Script(meta={"title": "Retry test"}, sections=[Section(1, "Example", "show one thing", "One sentence.")])
    (tmp_path / "build" / "scenes").mkdir(parents=True)

    bad = '''
def states():
    def s01(ax):
        k.hanoi(ax, [[3, 2, 1], [], [], []])
    return [("s01", 0, s01)]
'''
    good = '''
def states():
    def s01(ax):
        k.title(ax, "Valid state")
    return [("s01", 0, s01)]
'''
    replies = iter([bad, good])
    calls = []

    monkeypatch.setenv("P2R_MAX_SCENE_ATTEMPTS", "2")
    monkeypatch.setattr(scenes.align, "load", lambda *_args, **_kwargs: {
        "sentences": [{"start": 0.0, "end": 1.0, "text": "One sentence."}]
    })
    monkeypatch.setattr(scenes.llm, "complete", lambda *args, **kwargs: (calls.append(kwargs) or next(replies)))
    monkeypatch.setattr(scenes.stills, "render_into", lambda *args, **kwargs: [{"i": 0}])

    result = scenes.generate(tmp_path, script, 1)

    assert result.read_text(encoding="utf-8") == good.strip()
    assert len(calls) == 2
    assert "until pass" not in calls[0]["label"]


def test_positive_retries_keeps_legacy_explicit_cap(monkeypatch, tmp_path: Path):
    script = Script(meta={"title": "Retry test"}, sections=[Section(1, "Example", "show one thing", "One sentence.")])
    (tmp_path / "build" / "scenes").mkdir(parents=True)
    bad = '''
def states():
    def s01(ax):
        k.hanoi(ax, [[3, 2, 1], [], [], []])
    return [("s01", 0, s01)]
'''
    monkeypatch.setenv("P2R_MAX_SCENE_ATTEMPTS", "10")
    monkeypatch.setattr(scenes.align, "load", lambda *_args, **_kwargs: {
        "sentences": [{"start": 0.0, "end": 1.0, "text": "One sentence."}]
    })
    monkeypatch.setattr(scenes.llm, "complete", lambda *args, **kwargs: bad)

    try:
        scenes.generate(tmp_path, script, 1, retries=1)
    except SystemExit as exc:
        assert "after 2 total attempts" in str(exc)
    else:
        raise AssertionError("generation unexpectedly accepted invalid source")
