"""Single source of truth for which Manim release this build targets.

``P2R_MANIM_VERSION`` declares the target; it does not silence a mismatch.
Setting it re-targets the generator prompts, the static verifier's messages,
and the render guard all at once -- this is how the Manim 0.19.0 Code2Video
comparison (docs/MANIM_EXPERIMENT_PROTOCOL.md) stays reproducible after the
project default moves to 0.21.0.
"""

from __future__ import annotations

import os

SUPPORTED_VERSION = "0.21.0"


def target_version() -> str:
    """Return the Manim version this build declares itself to target."""
    env = os.environ.get("P2R_MANIM_VERSION", "").strip()
    if env:
        return env
    inst = installed_version()
    if inst:
        return inst
    return SUPPORTED_VERSION


def installed_version() -> str | None:
    """Return the installed Manim's ``__version__``, or None if absent."""

    try:
        import manim
    except ImportError:
        return None

    return getattr(manim, "__version__", None)


def status() -> tuple[str, str | None, bool]:
    """Return ``(target, installed, matches)``.

    ``matches`` is True only when Manim is installed and its version equals
    the declared target exactly.
    """

    target = target_version()
    installed = installed_version()
    return target, installed, installed == target


__all__ = [
    "SUPPORTED_VERSION",
    "installed_version",
    "status",
    "target_version",
]
