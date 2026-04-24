"""
rbac_compiler — public API for programmatic use (CLI and future web GUI).

Example:
    from pathlib import Path
    from rbac_compiler import compile_registry

    result = compile_registry(Path("~/registry").expanduser())
    if not result.validation.ok:
        for err in result.validation.errors:
            print(f"ERROR: {err}")
    else:
        print(f"Wrote plan to {result.output_path}")
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
from .operations import (
    CompileResult,
    LoadedRegistry,
    ValidateResult,
    compile_registry,
    load_registry,
    validate,
)
from .validator import ValidationResult, validate_all

__version__ = "0.2.0"

__all__ = [
    "__version__",
    # Operations (high-level API)
    "compile_registry",
    "validate",
    "load_registry",
    "CompileResult",
    "ValidateResult",
    "LoadedRegistry",
    # Core compilation
    "CompiledPlan",
    "compile_plan",
    "ValidationResult",
    "validate_all",
    # Loaders
    "load_constants",
    "load_org_file",
    "load_agent_registry",
    "discover_org_files",
    # Models
    "Constants",
    "OrgDataFile",
    "OrgDefinition",
    "DataEntry",
    "AgentRegistry",
    "Agent",
    "AccessGrant",
    # Errors
    "RegistryError",
    "RegistryWarning",
    "RegistryLoadError",
    "CompilerInternalError",
]
