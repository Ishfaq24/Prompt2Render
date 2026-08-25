from pathlib import Path

from prompt2render.pedagogy import deterministic_review
from prompt2render.project import Script, Section, parse_script


def _script(tmp_path: Path, body: str):
    path = tmp_path / "script.md"
    path.write_text("---\ntitle: Sorting\naudience: undergraduate computer science\n---\n" + body, encoding="utf-8")
    return parse_script(path)


def test_pedagogy_accepts_complete_section(tmp_path):
    script = _script(tmp_path, "## 1 - Idea\n> ANIM: show [5, 2] and swap the values\n\nCompare the two values and explain why the smaller value moves first.\n")
    result = deterministic_review(script)
    assert result["pass"] is True
    assert result["profile"] in {"standard", "deep"}


def test_pedagogy_rejects_missing_narration_and_animation():
    # Built directly rather than via parse_script(): project.py's own
    # parse-time validation now hard-rejects (SystemExit) a section with an
    # empty ANIM brief before deterministic_review ever sees it, so this
    # exercises deterministic_review's narration/animation checks as a unit,
    # independent of that separate, stricter parse-time gate.
    script = Script(
        meta={"title": "Sorting", "audience": "undergraduate computer science"},
        sections=[Section(index=1, title="Idea", anim="", narration="")],
    )
    result = deterministic_review(script)
    assert result["pass"] is False
    categories = {issue["category"] for issue in result["issues"]}
    assert "narration" in categories
    assert "animation" in categories
