"""
High-level operations called by the CLI (and by a future GUI).

Each operation returns a structured result object so callers can display
or serialise the outcome without re-running logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import loader
from .compiler import CompiledPlan, compile_plan
from .emitter import emit
from .models import AgentRegistry, Constants, OrgDataFile
from .validator import ValidationResult, validate_all


# ── Result objects ────────────────────────────────────────────────────────────

@dataclass
class LoadedRegistry:
    """Bundle of everything the loader produces."""

    constants: Constants
    org_files: list[tuple[OrgDataFile, Path]]
    agent_registry: AgentRegistry
    constants_path: Path
    agents_path: Path
    constants_hash: str
    agents_hash: str
    org_hashes: dict[str, str]


@dataclass
class ValidateResult:
    loaded: LoadedRegistry
    validation: ValidationResult


@dataclass
class CompileResult:
    loaded: LoadedRegistry
    validation: ValidationResult
    plan: CompiledPlan | None
    output_path: Path | None


# ── Load ──────────────────────────────────────────────────────────────────────

def load_registry(registry_dir: Path) -> LoadedRegistry:
    """Load constants, all org files, and the agent registry from one directory."""
    constants_path = registry_dir / "classification_constants.yml"
    agents_path = registry_dir / "agent_registry.yml"

    constants, constants_hash = loader.load_constants(constants_path)
    agent_registry, agents_hash = loader.load_agent_registry(agents_path)

    org_paths = loader.discover_org_files(registry_dir, constants.compiler.orgs_dir)
    org_files: list[tuple[OrgDataFile, Path]] = []
    org_hashes: dict[str, str] = {}
    for p in org_paths:
        of, h = loader.load_org_file(p)
        org_files.append((of, p))
        org_hashes[of.org] = h

    return LoadedRegistry(
        constants=constants,
        org_files=org_files,
        agent_registry=agent_registry,
        constants_path=constants_path,
        agents_path=agents_path,
        constants_hash=constants_hash,
        agents_hash=agents_hash,
        org_hashes=org_hashes,
    )


# ── Validate ──────────────────────────────────────────────────────────────────

def validate(registry_dir: Path) -> ValidateResult:
    """Run schema + cross-reference validation. Does not emit output."""
    loaded = load_registry(registry_dir)
    result = validate_all(
        loaded.constants,
        loaded.constants_path,
        loaded.org_files,
        loaded.agent_registry,
        loaded.agents_path,
    )
    return ValidateResult(loaded=loaded, validation=result)


# ── Compile ───────────────────────────────────────────────────────────────────

def compile_registry(
    registry_dir: Path,
    output: Path | None = None,
    fmt: str = "yaml",
    check_only: bool = False,
) -> CompileResult:
    """Validate and (unless check_only) emit the compiled plan."""
    loaded = load_registry(registry_dir)
    result = validate_all(
        loaded.constants,
        loaded.constants_path,
        loaded.org_files,
        loaded.agent_registry,
        loaded.agents_path,
    )

    if not result.ok:
        return CompileResult(loaded=loaded, validation=result, plan=None, output_path=None)

    plan, compile_warnings = compile_plan(
        constants=loaded.constants,
        org_files=loaded.org_files,
        agent_registry=loaded.agent_registry,
        source_paths={
            "constants": str(loaded.constants_path),
            "agents": str(loaded.agents_path),
            "orgs": {of.org: str(p) for of, p in loaded.org_files},
        },
        source_hashes={
            "constants": loaded.constants_hash,
            "agents": loaded.agents_hash,
            "orgs": loaded.org_hashes,
        },
    )

    # Merge compile-phase warnings into the single warning bucket the GUI/CLI
    # both consume. Emitted YAML stays pure data.
    for msg in compile_warnings:
        result.warn(msg)

    if check_only:
        return CompileResult(loaded=loaded, validation=result, plan=plan, output_path=None)

    out = output or _default_output_path(loaded.constants, registry_dir)
    emit(plan, out, fmt=fmt)
    return CompileResult(loaded=loaded, validation=result, plan=plan, output_path=out)


def _default_output_path(constants: Constants, registry_dir: Path) -> Path:
    return registry_dir / constants.compiler.output_file


__all__ = [
    "LoadedRegistry",
    "ValidateResult",
    "CompileResult",
    "load_registry",
    "validate",
    "compile_registry",
]
