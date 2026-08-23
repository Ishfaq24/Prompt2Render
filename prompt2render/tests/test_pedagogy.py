from pathlib import Path

from prompt2render.pedagogy import deterministic_review
from prompt2render.project import parse_script


def _script(tmp_path: Path, body: str):
    path = tmp_path / "script.md"
    path.write_text("---\ntitle: Sorting\naudience: undergraduate computer science\n---\n" + body, encoding="utf-8")
    return parse_script(path)


def test_pedagogy_accepts_complete_section(tmp_path):
    script = _script(tmp_path, "## 1 - Idea\n> ANIM: show [5, 2] and swap the values\n\nCompare the two values and explain why the smaller value moves first.\n")
    result = deterministic_review(script)
    assert result["pass"] is True
    assert result["profile"] in {"standard", "deep"}


def test_pedagogy_rejects_missing_narration_and_animation(tmp_path):
    script = _script(tmp_path, "## 1 - Idea\n> ANIM:\n\n")
    result = deterministic_review(script)
    assert result["pass"] is False
    categories = {issue["category"] for issue in result["issues"]}
    assert "narration" in categories
    assert "animation" in categories
