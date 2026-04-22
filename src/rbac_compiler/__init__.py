"""
rbac_compiler — public API for programmatic use (CLI and future web GUI).

Example usage:
    from pathlib import Path
    from rbac_compiler import compile_registry

    plan, result = compile_registry(Path("~/registry").expanduser())
    if not result.ok:
        for err in result.errors:
            print(f"ERROR: {err}")
    else:
        print(f"Compiled {len(plan.required_groups)} groups")
"""

from .compiler import CompiledPlan, compile_plan
from .errors import CompilerInternalError, RegistryError, RegistryLoadError, RegistryWarning
from .loader import (
    discover_org_files,
    load_agent_registry,
    load_constants,
    load_org_file,
)
from .models import (
    AccessGrant,
    Agent,
    AgentRegistry,
    Constants,
    DataEntry,
    OrgDataFile,
    OrgDefinition,
)
from .validator import ValidationResult, validate_all

__version__ = "0.2.0"
__all__ = [
    "compile_registry",
    "CompiledPlan",
    "compile_plan",
    "ValidationResult",
    "validate_all",
    "RegistryError",
    "RegistryWarning",
    "RegistryLoadError",
    "CompilerInternalError",
    "Constants",
    "OrgDataFile",
    "OrgDefinition",
    "DataEntry",
    "AgentRegistry",
    "Agent",
    "AccessGrant",
    "load_constants",
    "load_org_file",
    "load_agent_registry",
    "discover_org_files",
]


def compile_registry(
    registry_dir: "Path",  # type: ignore[name-defined]  # noqa: F821
) -> "tuple[CompiledPlan | None, ValidationResult]":
    """High-level convenience API: load, validate, and compile a registry directory.

    Returns (plan, result). If validation fails, plan is None.
    Raises RegistryLoadError on I/O or parse failures.
    """
    from pathlib import Path as _Path

    registry_dir = _Path(registry_dir)
    constants_path = registry_dir / "classification_constants.yml"
    agents_path = registry_dir / "agent_registry.yml"

    constants, constants_hash = load_constants(constants_path)
    agent_reg, agents_hash = load_agent_registry(agents_path)

    org_paths = discover_org_files(registry_dir, constants.compiler.orgs_dir)
    org_files_with_hashes = []
    org_hashes = {}
    for p in org_paths:
        of, h = load_org_file(p)
        org_files_with_hashes.append((of, p))
        org_hashes[of.org] = h

    result = validate_all(
        constants, constants_path, org_files_with_hashes, agent_reg, agents_path
    )
    if not result.ok:
        return None, result

    plan = compile_plan(
        constants=constants,
        org_files=org_files_with_hashes,
        agent_registry=agent_reg,
        source_paths={
            "constants": str(constants_path),
            "agents": str(agents_path),
            "orgs": {of.org: str(p) for of, p in org_files_with_hashes},
        },
        source_hashes={
            "constants": constants_hash,
            "agents": agents_hash,
            "orgs": org_hashes,
        },
    )
    return plan, result
