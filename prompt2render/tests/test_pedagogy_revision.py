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


def test_revision_prompt_warns_against_abbreviations(tmp_path, monkeypatch):
    path = tmp_path / "script.md"
    path.write_text(
        "---\ntitle: Test\n---\n"
        "## 1 - First\n> ANIM: first\n\nFirst explanation.\n",
        encoding="utf-8",
    )
    script = parse_script(path)
    monkeypatch.setattr(llm, "keys", lambda: ["test-key"])

    captured_prompts = []

    def fake_complete(prompt, *args, **kwargs):
        captured_prompts.append(prompt)
        return '{"sections": [{"index": 1, "title": "First", "animation": "first state", "narration": "First explanation."}]}'

    monkeypatch.setattr(llm, "complete", fake_complete)
    revise_script(
        tmp_path,
        script,
        {"pass": False, "profile": "standard", "issues": [{"severity": "blocking", "issue": "add detail"}]},
    )
    assert captured_prompts, "expected revise_script to call llm.complete"
    assert "force-aligned word-for-word" in captured_prompts[0]
    assert "abbreviations" in captured_prompts[0]
