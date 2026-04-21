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
    load_org_file,
    load_vocabulary,
)
from .models import (
    AccessGrant,
    Agent,
    AgentRegistry,
    DataEntry,
    OrgDataFile,
    OrgDefinition,
    Vocabulary,
)
from .validator import ValidationResult, validate_all

__version__ = "0.1.0"
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
    "Vocabulary",
    "OrgDataFile",
    "OrgDefinition",
    "DataEntry",
    "AgentRegistry",
    "Agent",
    "AccessGrant",
    "load_vocabulary",
    "load_org_file",
    "load_agent_registry",
    "discover_org_files",
]


def compile_registry(registry_dir: "Path") -> "tuple[CompiledPlan | None, ValidationResult]":  # noqa: F821
    """High-level convenience API: load, validate, and compile a registry directory.

    Returns (plan, result). If validation fails, plan is None.
    Raises RegistryLoadError on I/O or parse failures.
    """
    from pathlib import Path as _Path

    registry_dir = _Path(registry_dir)
    vocab_path = registry_dir / "classification_vocabulary.yml"
    agents_path = registry_dir / "agent_registry.yml"

    vocab, vocab_hash = load_vocabulary(vocab_path)
    agent_reg, agents_hash = load_agent_registry(agents_path)

    org_paths = discover_org_files(registry_dir)
    org_files = [(load_org_file(p)[0], p) for p in org_paths]
    org_hashes = {of.org: load_org_file(p)[1] for of, p in org_files}

    # Re-load to get hashes cleanly (loader called twice; acceptable for now)
    org_files_with_hashes = []
    org_hashes = {}
    for p in org_paths:
        of, h = load_org_file(p)
        org_files_with_hashes.append((of, p))
        org_hashes[of.org] = h

    result = validate_all(vocab, vocab_path, org_files_with_hashes, agent_reg, agents_path)
    if not result.ok:
        return None, result

    source_files: dict[str, object] = {
        "vocabulary": str(vocab_path),
        "agents": str(agents_path),
        "orgs": {of.org: str(p) for of, p in org_files_with_hashes},
    }
    source_hashes: dict[str, object] = {
        "vocabulary": vocab_hash,
        "agents": agents_hash,
        "orgs": org_hashes,
    }

    plan = compile_plan(
        vocab=vocab,
        org_files=org_files_with_hashes,
        agent_registry=agent_reg,
        source_paths=source_files,
        source_hashes=source_hashes,
    )
    return plan, result
