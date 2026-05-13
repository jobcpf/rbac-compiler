"""
Agent surface path resolution.

Both rbac-compile and sync-compile must produce byte-identical paths for the
same (agent, surface) pair — sync-compile uses the path as bisync's --local
target; rbac-compile uses it as a directory_classification. Divergence means
sync writes to one place while RBAC classifies another. Silent breakage.

The reference implementation lives in `sync_compiler.registry.resolve_surface_path()`.
This module replicates the contract. A cross-tool fixture
(tests/fixtures/cross_tool/agent_paths.yml) pins both implementations together.

Surfaces:
  - configs   (agent-private, mode 0700; classified=No)
  - memory    (classified)
  - sessions  (classified)
  - scratch   (classified)

rbac-compile emits relative paths in directory_classifications
(Ansible prepends data_root at apply time). The absolute form is the
cross-tool canonical form; the relative form is derived by stripping
the data_root prefix.
"""

from __future__ import annotations

from .models import Agent

DATA_ROOT = "/mnt/raid/"

# All four surfaces an agent may expose. configs/ is private and not classified,
# but the resolver still gives a path for it (Ansible uses it for ownership
# setup outside the classification mechanism).
ALL_SURFACES = ("configs", "memory", "sessions", "scratch")

# Surfaces that rbac-compile emits directory_classifications for. configs is
# excluded — it's mode 0700, owned by the agent's user, not group-classified.
CLASSIFIED_SURFACES = ("memory", "sessions", "scratch")


def _canonicalise(path: str) -> str:
    """Normalise a user-supplied path: trim whitespace, collapse repeated
    slashes, ensure a single trailing slash. No path resolution (.. is
    left alone — Pydantic-level validation rejects it earlier for data
    entries; shares overrides should be trusted/checked at validation time).
    """
    path = path.strip()
    while "//" in path:
        path = path.replace("//", "/")
    if not path.endswith("/"):
        path = path + "/"
    return path


def resolve_surface_path(agent: Agent, surface: str) -> str | None:
    """Return the absolute path for an agent's surface.

    Resolution rules:
      1. If `agent.shares.<surface>` is set, that override wins (canonicalised).
      2. Otherwise, if `agent.share_class` is set, return the convention path:
         /mnt/raid/<share_class.org>/agents/<agent.name>/<surface>/
      3. Otherwise return None — the agent has no path for this surface.

    Mirrors sync-compile's resolve_surface_path(). Cross-tool fixture verifies
    byte-equivalence.
    """
    if surface not in ALL_SURFACES:
        raise ValueError(
            f"unknown surface '{surface}' (valid: {', '.join(ALL_SURFACES)})"
        )

    if agent.shares is not None:
        override = getattr(agent.shares, surface, None)
        if override:
            return _canonicalise(override)

    if agent.share_class is None:
        return None

    return f"{DATA_ROOT}{agent.share_class.org}/agents/{agent.name}/{surface}/"


def resolve_surface_path_relative(agent: Agent, surface: str) -> str | None:
    """Return the path relative to DATA_ROOT (the form emitted in
    directory_classifications). Raises ValueError if an override path is
    not under DATA_ROOT — rbac-compile cannot classify arbitrary paths.
    """
    abs_path = resolve_surface_path(agent, surface)
    if abs_path is None:
        return None
    if not abs_path.startswith(DATA_ROOT):
        raise ValueError(
            f"agent '{agent.name}' surface '{surface}': path '{abs_path}' "
            f"is not under DATA_ROOT '{DATA_ROOT}' — rbac-compile cannot "
            f"classify paths outside the fileserver data root"
        )
    return abs_path[len(DATA_ROOT):]
