"""The Plugin contract every harness stage implements, per the migration brief."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .context import SceneContext


class Plugin(ABC):
    #: Overridden by subclasses; also the key looked up in config.yaml.
    name: str = "plugin"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    @abstractmethod
    def declare_dependencies(self) -> list[str]:
        """Which SceneContext fields this plugin reads."""

    @abstractmethod
    def declare_effects(self) -> list[str]:
        """Which SceneContext fields this plugin writes."""

    @abstractmethod
    def run(self, context: SceneContext) -> SceneContext:
        ...

    def revert(self, context: SceneContext, snapshot: SceneContext) -> SceneContext:
        """Default revert: restore the pre-run snapshot. Plugins rarely need to override this —
        the harness core's copy-on-write snapshot already gives every plugin a correct revert for
        free; this hook exists for a plugin that needs to do more (e.g. undo a side effect outside
        SceneContext, like a file it wrote)."""
        from .context import restore
        return restore(context, snapshot)

    def is_gate(self) -> bool:
        """Does failure here block progression? Config-overridable, never hardcoded by a caller —
        subclasses set `_default_gate`; config.yaml's `gate_override` (True/False/null) wins."""
        override = self.config.get("gate_override")
        if override is not None:
            return bool(override)
        return self._default_gate()

    def _default_gate(self) -> bool:
        return True

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))
