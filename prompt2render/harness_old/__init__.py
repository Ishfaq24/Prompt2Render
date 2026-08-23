"""Prompt2Render harness package.

Plugin implementations and the registry live in :mod:`prompt2render.harness.plugins`.
This initializer intentionally performs no plugin imports. Keeping package initialization
side-effect-free prevents imports such as ``prompt2render.harness.context`` from trying to
resolve plugin modules from the wrong directory on Windows.
"""

__all__ = []
