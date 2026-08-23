from pathlib import Path

from prompt2render import llm
from prompt2render.pedagogy import revise_script
from prompt2render.project import parse_script


def test_revision_rewrites_all_sections_without_index_error(tmp_path, monkeypatch):
    path = tmp_path / "script.md"
    path.write_text(
        "---\ntitle: Test\n---\n"
        "## 1 - First\n> ANIM: first\n\nFirst explanation.\n\n"
        "## 2 - Second\n> ANIM: second\n\nSecond explanation.\n",
        encoding="utf-8",
    )
    script = parse_script(path)
    monkeypatch.setattr(llm, "keys", lambda: ["test-key"])
    monkeypatch.setattr(
        llm,
        "complete",
        lambda *args, **kwargs: '{"sections": ['
        '{"index": 1, "title": "First revised", "animation": "first state", "narration": "First revised explanation."},'
        '{"index": 2, "title": "Second revised", "animation": "second state", "narration": "Second revised explanation."}'
        ']}',
    )
    revised, _ = revise_script(
        tmp_path,
        script,
        {"pass": False, "profile": "standard", "issues": [{"severity": "blocking", "issue": "add detail"}]},
    )
    assert [s.title for s in revised.sections] == ["First revised", "Second revised"]
    assert "First revised explanation" in path.read_text(encoding="utf-8")
    assert "Second revised explanation" in path.read_text(encoding="utf-8")
