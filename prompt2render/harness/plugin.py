"""Plugin contract for Prompt2Render harness stages.

Every ordinary pipeline stage implements this interface.

The contract deliberately separates four concerns:

    dependencies  -> what the plugin consumes
    effects       -> what the plugin produces
    run           -> forward execution
    revert        -> recovery/rollback

The harness owns dependency ordering, snapshots, gate evaluation, and
configuration. Plugins should therefore focus on their stage-specific work.

Plugins that perform external side effects (files, renders, API calls, etc.)
may override ``revert`` when restoring ``SceneContext`` alone is insufficient.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from .context import SceneContext


class Plugin(ABC):
    """Base contract implemented by every Prompt2Render harness plugin."""

    #: Stable plugin identifier and config.yaml key.
    name: str = "plugin"

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize a plugin with its configuration.

        A defensive copy prevents a plugin from unexpectedly mutating the
        caller's configuration dictionary.
        """

        self.config: dict[str, Any] = dict(
            config
            or {}
        )

    # ------------------------------------------------------------------
    # Declarative DAG contract
    # ------------------------------------------------------------------

    @abstractmethod
    def declare_dependencies(
        self,
    ) -> list[str]:
        """Return SceneContext fields consumed by this plugin."""

    @abstractmethod
    def declare_effects(
        self,
    ) -> list[str]:
        """Return SceneContext fields produced/updated by this plugin."""

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    def run(
        self,
        context: SceneContext,
    ) -> SceneContext:
        """Execute the plugin against the current SceneContext."""

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def revert(
        self,
        context: SceneContext,
        snapshot: SceneContext,
    ) -> SceneContext:
        """Restore the context to its pre-plugin state.

        The default implementation performs an in-place context restore.
        Plugins may override this when ``run()`` creates external side
        effects that cannot be represented by SceneContext alone.

        Example external side effects requiring a custom revert:

        * generated source files
        * rendered media
        * temporary assets
        * external API state

        The override should remain scoped to the plugin's own effects.
        """

        from .context import restore

        return restore(
            context,
            snapshot,
        )

    # ------------------------------------------------------------------
    # Gate policy
    # ------------------------------------------------------------------

    def is_gate(
        self,
    ) -> bool:
        """Return whether a plugin failure blocks pipeline progression.

        ``gate_override`` in config.yaml has precedence over the plugin's
        default. ``None`` means "use the plugin default".

        This keeps gate policy configurable without requiring the runner to
        hard-code verifier-specific behavior.
        """

        override = self.config.get(
            "gate_override"
        )

        if override is not None:
            return self._coerce_bool(
                override,
                field="gate_override",
            )

        return bool(
            self._default_gate()
        )

    def _default_gate(
        self,
    ) -> bool:
        """Default gate policy.

        Individual plugins may override this when their failure should not
        block the pipeline.
        """

        return True

    # ------------------------------------------------------------------
    # Enablement
    # ------------------------------------------------------------------

    def enabled(
        self,
    ) -> bool:
        """Return whether this plugin participates in the pipeline."""

        value = self.config.get(
            "enabled",
            True,
        )

        return self._coerce_bool(
            value,
            field="enabled",
        )

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_bool(
        value: Any,
        *,
        field: str,
    ) -> bool:
        """Safely coerce common configuration boolean representations.

        Avoids Python's surprising behavior where ``bool("false")`` is True.
        """

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            int,
        ) and value in (
            0,
            1,
        ):
            return bool(
                value
            )

        if isinstance(
            value,
            str,
        ):
            normalized = (
                value.strip()
                .lower()
            )

            if normalized in {
                "true",
                "yes",
                "y",
                "on",
                "1",
            }:
                return True

            if normalized in {
                "false",
                "no",
                "n",
                "off",
                "0",
            }:
                return False

        raise ValueError(
            f"invalid boolean value for "
            f"{field!r}: {value!r}"
        )


__all__ = [
    "Plugin",
]