import pytest

from prompt2render import manimver


def test_target_version_defaults_to_supported(monkeypatch):
    monkeypatch.delenv("P2R_MANIM_VERSION", raising=False)
    assert manimver.target_version() == manimver.SUPPORTED_VERSION


def test_target_version_honors_env_override(monkeypatch):
    monkeypatch.setenv("P2R_MANIM_VERSION", "0.19.0")
    assert manimver.target_version() == "0.19.0"


def test_target_version_ignores_blank_override(monkeypatch):
    monkeypatch.setenv("P2R_MANIM_VERSION", "   ")
    assert manimver.target_version() == manimver.SUPPORTED_VERSION


def test_installed_version_reports_none_when_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "manim":
            raise ImportError("no manim")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert manimver.installed_version() is None


def test_status_reports_mismatch(monkeypatch):
    monkeypatch.setenv("P2R_MANIM_VERSION", "9.9.9")
    target, installed, matches = manimver.status()
    assert target == "9.9.9"
    assert matches is False
    # installed may be None or a real version depending on the environment,
    # but it must never equal the deliberately-impossible target above.
    assert installed != "9.9.9"


@pytest.mark.skipif(
    manimver.installed_version() is None,
    reason="manim is not installed in this environment",
)
def test_status_matches_when_target_equals_installed(monkeypatch):
    installed = manimver.installed_version()
    monkeypatch.setenv("P2R_MANIM_VERSION", installed)
    target, reported_installed, matches = manimver.status()
    assert target == installed
    assert reported_installed == installed
    assert matches is True
