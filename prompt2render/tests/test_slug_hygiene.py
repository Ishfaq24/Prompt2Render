import pytest
from pathlib import Path
from prompt2render import cfg, project


def test_slugify_basic():
    assert cfg.slugify("Hanoi Problem") == "hanoi-problem"
    assert cfg.slugify("How Diffie Hellman Key Exchange Works") == "how-diffie-hellman-key-exchange-works"
    assert cfg.slugify("History and Definition of Pi") == "history-and-definition-of-pi"
    assert cfg.slugify("Neural Network Structure") == "neural-network-structure"


def test_slugify_special_characters():
    assert cfg.slugify("How Quantum Computers Work?!") == "how-quantum-computers-work"
    assert cfg.slugify("  Spaces   &   tabs  \t ") == "spaces-tabs"
    assert cfg.slugify("___Under_score_test___") == "under-score-test"
    assert cfg.slugify("..Leading.dots..") == "leading.dots"
    assert cfg.slugify("Special #$% Characters *&^") == "special-characters"


def test_slugify_conforms_to_validate_slug():
    test_cases = [
        "Hanoi Problem",
        "_auto-smoke-test",
        "Binary-Search",
        "QuickSort",
        "How Diffie Hellman Key Exchange Works",
        "123 numbers and spaces",
        "---dashes---",
        "special/path/characters\\backslashes",
    ]
    for tc in test_cases:
        slug = cfg.slugify(tc)
        # Must not raise an exception
        validated = cfg.validate_slug(slug, exit_on_error=False)
        assert validated == slug
        assert not any(c in slug for c in " /\\:\0")


def test_new_project_auto_slugify(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "PROJECTS", tmp_path)
    # Passing an un-slugified title with spaces should create a clean directory
    d = project.new_project("My Cool Algorithm", minutes=1)
    assert d.name == "my-cool-algorithm"
    assert d.is_dir()
    assert (d / "script.md").is_file()
    assert (d / "sections").is_dir()
