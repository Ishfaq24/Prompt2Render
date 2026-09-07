"""Prompt2Render harness plugin loader and dependency resolver.

This module is responsible for:

    config.yaml
        ↓
    enabled plugin instances
        ↓
    dependency/effect DAG resolution
        ↓
    ordered pipeline

Plugin dependencies/effects are the authoritative ordering mechanism.
Registry order is used only as a deterministic tie-break when multiple
plugins are simultaneously schedulable.

``repair_router`` is intentionally constructed separately because it is an
event subscriber rather than an ordinary pipeline stage.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .plugin import Plugin


DEFAULT_CONFIG_PATH = (
    Path(__file__).parent / "config.yaml"
)


# Fields that already exist on a freshly constructed SceneContext and
# therefore do not need a producing plugin.
#
# Keep this set semantic: a field is pre-seeded only when a plugin may safely
# consume its initial value without another stage producing it first.
# These fields are append/update sinks shared by multiple verifier stages.
# They are intentionally not single-owner DAG artifacts.
MERGEABLE_EFFECTS = frozenset({"check_results", "retrieval_context", "asset_provenance"})


PRESEEDED_FIELDS = frozenset(
    {
        "prompt",
        "object_table",
        "hitl_annotations",
        "history",
        "project_dir",
        "repair_context",
        "repair_records",
        "pedagogy_review",
        "storyboard_plan",
        "retrieval_context",
        "asset_provenance",
        "retriever_manim_rag",
        "check_results",
    }
)


class DependencyError(RuntimeError):
    """Raised when the plugin dependency graph cannot be resolved."""


class ConfigError(ValueError):
    """Raised when harness configuration has an invalid structure."""


def _names(
    plugins: list[Plugin],
) -> list[str]:
    return [
        str(p.name)
        for p in plugins
    ]


def _validate_plugins(
    plugins: list[Plugin],
) -> None:
    """Validate plugin declarations before attempting topological sorting."""

    seen: dict[str, int] = {}

    for plugin in plugins:
        name = str(
            plugin.name
        ).strip()

        if not name:
            raise DependencyError(
                "plugin has an empty name"
            )

        seen[name] = (
            seen.get(name, 0) + 1
        )

        dependencies = list(
            plugin.declare_dependencies()
            or []
        )

        effects = list(
            plugin.declare_effects()
            or []
        )

        if any(
            not isinstance(
                value,
                str,
            )
            or not value.strip()
            for value in dependencies
        ):
            raise DependencyError(
                f"plugin {name!r} declares "
                "an invalid dependency"
            )

        if any(
            not isinstance(
                value,
                str,
            )
            or not value.strip()
            for value in effects
        ):
            raise DependencyError(
                f"plugin {name!r} declares "
                "an invalid effect"
            )

        overlap = (
            set(dependencies)
            & set(effects)
        )

        if overlap:
            raise DependencyError(
                f"plugin {name!r} both reads and "
                f"produces {sorted(overlap)}; "
                "declare a separate effect only when "
                "the plugin actually owns that field."
            )

    duplicates = {
        name: count
        for name, count in seen.items()
        if count > 1
    }

    if duplicates:
        raise DependencyError(
            "duplicate enabled plugin names: "
            f"{duplicates}"
        )


def resolve_order(
    plugins: list[Plugin],
) -> list[Plugin]:
    """Topologically order plugins by declared dependencies/effects.

    A plugin is schedulable when every declared dependency is either:

    * a pre-seeded SceneContext field, or
    * an effect produced by a plugin already scheduled.

    Multiple ready plugins are emitted in their original input order. This
    makes config/registry order a stable deterministic tie-break without
    making it the actual dependency mechanism.

    Raises:
        DependencyError: if a cycle or otherwise unresolved dependency exists.
    """

    plugins = list(
        plugins
    )

    _validate_plugins(
        plugins
    )

    remaining = list(
        plugins
    )

    available = set(
        PRESEEDED_FIELDS
    )

    ordered: list[
        Plugin
    ] = []

    # Track which plugin owns each produced field. This gives much clearer
    # diagnostics when two plugins claim the same artifact.
    producers: dict[
        str,
        str,
    ] = {}

    for plugin in plugins:
        for effect in (
            plugin.declare_effects()
            or []
        ):
            previous = producers.get(
                effect
            )

            if effect in MERGEABLE_EFFECTS:
                continue

            if (
                previous is not None
                and previous != plugin.name
            ):
                raise DependencyError(
                    f"multiple plugins produce "
                    f"field {effect!r}: "
                    f"{previous!r}, {plugin.name!r}"
                )

            producers[
                effect
            ] = plugin.name

    while remaining:

        ready: list[
            Plugin
        ] = []

        for plugin in remaining:
            dependencies = set(
                plugin.declare_dependencies()
                or []
            )

            if dependencies <= available:
                ready.append(
                    plugin
                )

        if not ready:
            stuck: dict[
                str,
                list[str],
            ] = {}

            for plugin in remaining:
                unmet = sorted(
                    set(
                        plugin.declare_dependencies()
                        or []
                    )
                    - available
                )

                stuck[
                    plugin.name
                ] = unmet

            # Identify dependencies that are expected to be produced by
            # plugins still in the unresolved set. This makes cycle errors
            # considerably easier to diagnose.
            remaining_names = {
                p.name
                for p in remaining
            }

            waiting_on = {
                plugin.name: {
                    dependency: producers.get(
                        dependency
                    )
                    for dependency in unmet
                    if producers.get(
                        dependency
                    ) in remaining_names
                }
                for plugin_name, unmet in stuck.items()
                for plugin in remaining
                if plugin.name == plugin_name
            }

            raise DependencyError(
                "cannot resolve plugin order. "
                f"Unmet dependencies: {stuck}. "
                f"Waiting on unresolved producers: {waiting_on}. "
                f"Already available fields: "
                f"{sorted(available)}"
            )

        # Input order is the deterministic tie-break.
        for plugin in ready:
            ordered.append(
                plugin
            )

            effects = set(
                plugin.declare_effects()
                or []
            )

            available.update(
                effects
            )

            remaining.remove(
                plugin
            )

    return ordered


def load_config(
    path: Path | None = None,
) -> dict[str, Any]:
    """Load and validate ``config.yaml``.

    Missing configuration is valid and produces an empty configuration.
    """

    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            "PyYAML is required to load harness configuration."
        ) from exc

    config_path = (
        Path(path)
        if path is not None
        else DEFAULT_CONFIG_PATH
    )

    if not config_path.exists():
        return {}

    try:
        value = yaml.safe_load(
            config_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise ConfigError(
            f"could not parse {config_path}: {exc}"
        ) from exc

    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ConfigError(
            f"{config_path} must contain a YAML mapping at its root."
        )

    return value


def _plugin_config(
    config: dict[str, Any],
    name: str,
) -> dict[str, Any]:
    """Extract one plugin's configuration safely."""

    value = config.get(
        name,
        {},
    )

    if value is None:
        return {}

    if not isinstance(
        value,
        dict,
    ):
        raise ConfigError(
            f"configuration for plugin {name!r} "
            "must be a mapping."
        )

    return dict(
        value
    )


def build_plugins(
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> list[Plugin]:
    """Instantiate enabled ordinary pipeline plugins and resolve their order.

    ``repair_router`` is excluded because it is event-driven infrastructure,
    not a DAG stage.
    """

    from .plugins import (
        NON_PIPELINE,
        REGISTRY,
    )

    cfg = (
        dict(config)
        if config is not None
        else load_config(
            config_path
        )
    )

    if not isinstance(
        cfg,
        dict,
    ):
        raise ConfigError(
            "harness configuration must be a mapping."
        )

    instances: list[
        Plugin
    ] = []

    for name, cls in REGISTRY.items():

        if name in NON_PIPELINE:
            continue

        plugin_config = _plugin_config(
            cfg,
            name,
        )

        try:
            instance = cls(
                plugin_config
            )
        except Exception as exc:
            raise ConfigError(
                f"could not instantiate plugin "
                f"{name!r}: {exc}"
            ) from exc

        if instance.enabled():
            instances.append(
                instance
            )

    return resolve_order(
        instances
    )


def build_repair_router(
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
):
    """Instantiate the event-driven repair router.

    Returns ``None`` when disabled by configuration.
    """

    from .plugins import REGISTRY

    cfg = (
        dict(config)
        if config is not None
        else load_config(
            config_path
        )
    )

    if not isinstance(
        cfg,
        dict,
    ):
        raise ConfigError(
            "harness configuration must be a mapping."
        )

    try:
        cls = REGISTRY[
            "repair_router"
        ]
    except KeyError as exc:
        raise ConfigError(
            "registry does not contain repair_router"
        ) from exc

    plugin_config = _plugin_config(
        cfg,
        "repair_router",
    )

    instance = cls(
        plugin_config
    )

    return (
        instance
        if instance.enabled()
        else None
    )


def build_repair_controller(
    plugins: list[Plugin],
    *,
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
    logger: Any = None,
    log_path: Path | None = None,
    journal: Any = None,
):
    """Assemble the authoritative repair controller for a pipeline.

    Returns ``None`` when ``repair_router`` is disabled -- a run with no
    router simply does not repair, and every gate behaves as it would have
    without one.

    Budget keys live under ``repair_router`` in config.yaml so the whole
    repair subsystem stays configured in one place.
    """

    from .repair_controller import (
        DEFAULT_MAX_REPAIRS_PER_SCENE,
        DEFAULT_MAX_TOTAL_REPAIRS,
        RepairController,
    )

    router = build_repair_router(
        config=config,
        config_path=config_path,
    )

    if router is None:
        return None

    plugins_by_name = {
        plugin.name: plugin
        for plugin in plugins
    }

    router.attach(
        plugins_by_name=plugins_by_name,
        log_path=log_path,
    )

    settings = router.config or {}

    def _int(key: str, default: int) -> int:
        try:
            return max(0, int(settings.get(key, default)))
        except (TypeError, ValueError):
            return default

    return RepairController(
        router=router,
        plugins_by_name=plugins_by_name,
        logger=logger,
        log_path=log_path,
        max_repairs_per_scene=_int(
            "max_repairs_per_scene",
            DEFAULT_MAX_REPAIRS_PER_SCENE,
        ),
        max_total_repairs=_int(
            "max_total_repairs",
            DEFAULT_MAX_TOTAL_REPAIRS,
        ),
        journal=journal,
    )


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "PRESEEDED_FIELDS",
    "DependencyError",
    "ConfigError",
    "resolve_order",
    "load_config",
    "build_plugins",
    "build_repair_controller",
    "build_repair_router",
]