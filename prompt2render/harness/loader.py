"""Reads config.yaml, resolves plugin execution order from declared dependencies/effects, and
instantiates enabled plugins. Any plugin is disableable via config alone — no code change.
"""
from __future__ import annotations

from pathlib import Path

from .plugin import Plugin

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

#: Fields that exist from the moment a SceneContext is constructed — no plugin "produces" them,
#: so the dependency resolver must not wait for a producer that will never come.
PRESEEDED_FIELDS = {"prompt", "object_table", "hitl_annotations", "history"}


class DependencyError(RuntimeError):
    pass


def resolve_order(plugins: list[Plugin]) -> list[Plugin]:
    """Topologically sort `plugins` by declare_dependencies()/declare_effects().

    A plugin is schedulable once every field it reads has been written by an
    already-scheduled plugin (or is pre-seeded). Ties broken by input order, so config order is a
    stable secondary sort key.
    """
    remaining = list(plugins)
    available = set(PRESEEDED_FIELDS)
    ordered: list[Plugin] = []

    while remaining:
        ready = [p for p in remaining
                 if set(p.declare_dependencies()) <= available]
        if not ready:
            stuck = {p.name: sorted(set(p.declare_dependencies()) - available)
                     for p in remaining}
            raise DependencyError(
                f"cannot resolve plugin order — unmet dependencies: {stuck}")
        for p in ready:
            ordered.append(p)
            available.update(p.declare_effects())
            remaining.remove(p)
    return ordered


def load_config(path: Path | None = None) -> dict:
    import yaml
    p = path or DEFAULT_CONFIG_PATH
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def build_plugins(config: dict | None = None, config_path: Path | None = None) -> list[Plugin]:
    """Instantiate every registered, enabled *pipeline* plugin, in resolved order.

    Excludes repair_router — it's an event subscriber, not a pipeline stage (see
    prompt2render/harness/plugins/repair_router's docstring); get it from build_repair_router() instead.
    """
    from .plugins import NON_PIPELINE, REGISTRY
    cfg = config if config is not None else load_config(config_path)

    instances = []
    for name, cls in REGISTRY.items():
        if name in NON_PIPELINE:
            continue
        pcfg = dict(cfg.get(name, {}))
        inst = cls(pcfg)
        if inst.enabled():
            instances.append(inst)
    return resolve_order(instances)


def build_repair_router(config: dict | None = None, config_path: Path | None = None):
    """Instantiate repair_router (or None if disabled) — not part of the ordinary pipeline."""
    from .plugins import REGISTRY
    cfg = config if config is not None else load_config(config_path)
    cls = REGISTRY["repair_router"]
    inst = cls(dict(cfg.get("repair_router", {})))
    return inst if inst.enabled() else None
