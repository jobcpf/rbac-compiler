"""
Cross-reference validation across all registry files.

Collects all errors and warnings — does not stop at the first failure.
Schema validation (types, required fields) is handled by Pydantic in models.py.
This module handles cross-file consistency and semantic checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .errors import RegistryError, RegistryWarning
from .models import AgentRegistry, Constants, OrgDataFile


@dataclass
class ValidationResult:
    errors: list[RegistryError] = field(default_factory=list)
    warnings: list[RegistryWarning] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def error(self, message: str, file: Path | None = None, line: int | None = None) -> None:
        self.errors.append(RegistryError(message=message, file=file, line=line))

    def warn(self, message: str, file: Path | None = None, line: int | None = None) -> None:
        self.warnings.append(RegistryWarning(message=message, file=file, line=line))

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


# rbac-compile v0.3.x accepts only this schema version on input files.
SUPPORTED_SCHEMA_VERSION = "0.3"


def _migration_message_v02_to_v03(detected_version: str) -> str:
    return (
        f"detected rbac-compile v0.2 input layout (meta.version='{detected_version}'). "
        f"This rbac-compile is v0.3.\n\n"
        f"To migrate:\n"
        f"  1. Bump `meta.version` to \"0.3\" in:\n"
        f"       - classification_constants.yml\n"
        f"       - agent_registry.yml\n"
        f"       - orgs/<org>.yml  (each)\n"
        f"  2. In classification_constants.yml also update:\n"
        f"       compiler:\n"
        f"         registry_dir: \"~/registry\"      # fileserver working copy path\n"
        f"         schema_version: \"0.3\"\n"
        f"  3. Re-run rbac-compile.\n\n"
        f"See 'RBAC Compiler Architecture v0.3.md' for the full schema."
    )


def validate_constants(constants: Constants, path: Path) -> ValidationResult:
    result = ValidationResult()
    if constants.grade_range.min > constants.grade_range.max:
        result.error("grade_range.min must be ≤ grade_range.max", file=path)

    # Fail-fast on v0.2 layouts (operator-facing migration guidance).
    if constants.meta.version != SUPPORTED_SCHEMA_VERSION:
        result.error(_migration_message_v02_to_v03(constants.meta.version), file=path)

    return result


def validate_org_file(
    org_file: OrgDataFile,
    constants: Constants,
    known_orgs: dict[str, OrgDataFile],
    path: Path,
) -> ValidationResult:
    """Cross-reference checks for a single org data file."""
    result = ValidationResult()
    org_def = org_file.org_definition
    org_key = org_def.key
    grade_min = constants.grade_range.min
    grade_max = constants.grade_range.max

    # Filename stem should match declared org key
    if path.stem != org_key:
        result.warn(
            f"File basename '{path.stem}.yml' doesn't match declared org key '{org_key}' — "
            "consider renaming the file",
            file=path,
        )

    # Duplicate org key
    if org_key in known_orgs:
        result.error(f"Org key '{org_key}' already defined in another file", file=path)
        return result

    # Org grades must be within the platform grade_range
    for g in org_def.grades:
        if not (grade_min <= g <= grade_max):
            result.error(
                f"Org '{org_key}': grade {g} out of platform range [{grade_min}, {grade_max}]",
                file=path,
            )

    # Validate each data entry
    seen_paths: set[str] = set()
    for entry in org_file.data:

        if entry.path in seen_paths:
            result.error(f"Duplicate path '{entry.path}' in org '{org_key}'", file=path)
        seen_paths.add(entry.path)

        # Grade must be declared in this org's grade scale
        if entry.grade not in org_def.grades:
            valid = sorted(org_def.grades.keys())
            result.error(
                f"Path '{entry.path}': grade {entry.grade} not defined for org '{org_key}'. "
                f"Valid grades: {valid}",
                file=path,
            )

        # Vertical must be in this org's verticals (which includes 'any' by construction)
        if entry.vertical not in org_def.verticals:
            result.error(
                f"Path '{entry.path}': vertical '{entry.vertical}' not in org '{org_key}' "
                f"verticals ({org_def.verticals})",
                file=path,
            )

        # Scope must be in this org's scopes (which includes 'global' by construction)
        if entry.scope not in org_def.scopes:
            result.error(
                f"Path '{entry.path}': scope '{entry.scope}' not in org '{org_key}' "
                f"scopes ({org_def.scopes})",
                file=path,
            )

        if " " in entry.path:
            result.warn(
                f"Path '{entry.path}' contains spaces — valid but may cause issues with some tools",
                file=path,
            )

    return result


def validate_agent_registry(
    registry: AgentRegistry,
    constants: Constants,
    known_orgs: dict[str, OrgDataFile],
    path: Path,
) -> ValidationResult:
    """Cross-reference checks for the agent registry."""
    result = ValidationResult()

    seen_names: set[str] = set()
    for agent in registry.agents:

        if agent.name in seen_names:
            result.error(f"Duplicate agent name '{agent.name}'", file=path)
        seen_names.add(agent.name)

        if not agent.access:
            result.warn(f"Agent '{agent.name}' has no access grants", file=path)
            continue

        for grant in agent.access:

            if grant.org not in known_orgs:
                result.error(
                    f"Agent '{agent.name}': org '{grant.org}' has no org file in registry. "
                    f"Known orgs: {sorted(known_orgs.keys())}",
                    file=path,
                )
                continue

            org_def = known_orgs[grant.org].org_definition

            if grant.grade not in org_def.grades:
                result.error(
                    f"Agent '{agent.name}': grade {grant.grade} not defined for org '{grant.org}'. "
                    f"Valid grades: {sorted(org_def.grades.keys())}",
                    file=path,
                )

            if grant.vertical not in org_def.verticals:
                result.error(
                    f"Agent '{agent.name}': vertical '{grant.vertical}' not in org '{grant.org}' "
                    f"verticals ({org_def.verticals})",
                    file=path,
                )

            if grant.scope not in org_def.scopes:
                result.error(
                    f"Agent '{agent.name}': scope '{grant.scope}' not in org '{grant.org}' "
                    f"scopes ({org_def.scopes})",
                    file=path,
                )

    return result


def validate_all(
    constants: Constants,
    constants_path: Path,
    org_files: list[tuple[OrgDataFile, Path]],
    agent_registry: AgentRegistry,
    agents_path: Path,
) -> ValidationResult:
    """Run all validation passes and return a combined result."""
    combined = ValidationResult()
    schema_version = constants.compiler.schema_version

    combined.merge(validate_constants(constants, constants_path))

    # Schema version check across all registry files
    for org_file, path in org_files:
        if org_file.meta.version != schema_version:
            combined.error(
                f"Schema version mismatch: expected '{schema_version}', "
                f"got '{org_file.meta.version}'",
                file=path,
            )

    if agent_registry.meta.version != schema_version:
        combined.error(
            f"Schema version mismatch: expected '{schema_version}', "
            f"got '{agent_registry.meta.version}'",
            file=agents_path,
        )

    known_orgs: dict[str, OrgDataFile] = {}
    for org_file, path in org_files:
        combined.merge(validate_org_file(org_file, constants, known_orgs, path))
        if org_file.org not in known_orgs:
            known_orgs[org_file.org] = org_file

    combined.merge(validate_agent_registry(agent_registry, constants, known_orgs, agents_path))

    return combined
