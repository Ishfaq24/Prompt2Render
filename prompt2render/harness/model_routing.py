"""Per-role LLM model selection (Phase 16).

Prompt2Render is not hard-coded around one model. Each pipeline role
resolves its model through its own environment variable and falls back to
the shared ``P2R_SCENE_MODEL``, then to the caller's base default:

    P2R_PLANNER_MODEL            planner_llm / storyboard expansion
    P2R_GENERATOR_MODEL          first-pass scene code generation
    P2R_REPAIR_MODEL             repair regeneration (candidate revisions)
    P2R_VERIFIER_MODEL           LLM-backed verifiers (layout critique ...)
    P2R_SEMANTIC_VERIFIER_MODEL  verifier_semantic
    P2R_VISUAL_VERIFIER_MODEL    visual/post-render critics
    P2R_SCENE_MODEL              shared default for every role

The roles may all point at the same model or at different ones; nothing in
the harness assumes they are identical. Resolution returns the *env var
name* plus the fallback default, which is exactly what
``llm.complete(model_env=..., default_model=...)`` consumes, so the
existing deterministic model/key rotation underneath is unchanged.
"""

from __future__ import annotations

import os

#: role -> the environment variable that selects its model.
ROLE_ENV_VARS: dict[str, str] = {
    "planner": "P2R_PLANNER_MODEL",
    "generator": "P2R_GENERATOR_MODEL",
    "repair": "P2R_REPAIR_MODEL",
    "verifier": "P2R_VERIFIER_MODEL",
    "semantic_verifier": "P2R_SEMANTIC_VERIFIER_MODEL",
    "visual_verifier": "P2R_VISUAL_VERIFIER_MODEL",
}

#: Shared fallback env var consulted when a role-specific one is unset.
SHARED_MODEL_ENV = "P2R_SCENE_MODEL"


def model_env_for(role: str) -> str:
    """The environment variable name that selects this role's model."""

    return ROLE_ENV_VARS.get(str(role), SHARED_MODEL_ENV)


def resolve(role: str, base_default: str) -> tuple[str, str]:
    """Resolve ``(model_env, default_model)`` for one role.

    Pass both straight to ``llm.complete``: the role env var wins when set,
    then ``P2R_SCENE_MODEL``, then ``base_default``.
    """

    env_name = model_env_for(role)
    default = os.environ.get(SHARED_MODEL_ENV, "").strip() or str(base_default)

    return env_name, default


def effective_model_env(role: str) -> str:
    """The env var name that currently holds this role's model selection.

    Role-specific var when set, otherwise the shared ``P2R_SCENE_MODEL``
    when set, otherwise the role's own (unset) var -- which makes
    ``llm.complete`` fall through to its built-in default.
    """

    env_name = model_env_for(role)

    if os.environ.get(env_name, "").strip():
        return env_name

    if os.environ.get(SHARED_MODEL_ENV, "").strip():
        return SHARED_MODEL_ENV

    return env_name


__all__ = [
    "ROLE_ENV_VARS",
    "SHARED_MODEL_ENV",
    "effective_model_env",
    "model_env_for",
    "resolve",
]
