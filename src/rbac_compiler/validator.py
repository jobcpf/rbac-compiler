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
from .models import AgentRegistry, OrgDataFile, Vocabulary


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


def validate_vocabulary(vocab: Vocabulary, path: Path) -> ValidationResult:
    """Semantic checks on the vocabulary file itself (schema already validated by Pydantic)."""
    result = ValidationResult()
    # Nothing cross-file to check here; placeholder for future rules.
    return result


def validate_org_file(
    org_file: OrgDataFile,
    vocab: Vocabulary,
    known_orgs: dict[str, OrgDataFile],
    path: Path,
) -> ValidationResult:
    """Cross-reference checks for a single org data file.

    known_orgs: mapping of org_key -> OrgDataFile for all already-loaded org files,
    used for duplicate-org detection.
    """
    result = ValidationResult()

    # Filename stem should match declared org key
    if path.stem != org_file.org:
        result.warn(
            f"File basename '{path.stem}.yml' doesn't match declared org '{org_file.org}' — "
            "consider renaming the file",
            file=path,
        )

    # Grades must start at 0
    grades = sorted(org_file.org_def.grades.keys())
    if grades and grades[0] != 0:
        result.warn(
            f"Org '{org_file.org}' grade scale doesn't start at 0 (starts at {grades[0]})",
            file=path,
        )

    # Grade scale should have no gaps
    if grades and grades != list(range(grades[0], grades[-1] + 1)):
        result.warn(
            f"Org '{org_file.org}' has gaps in grade scale: {grades}",
            file=path,
        )

    # Validate each data entry against vocabulary
    seen_paths: set[str] = set()
    for entry in org_file.data:

        # Duplicate paths within this file
        if entry.path in seen_paths:
            result.error(
                f"Duplicate path '{entry.path}' in org '{org_file.org}'",
                file=path,
            )
        seen_paths.add(entry.path)

        # Grade defined for this org
        if entry.grade not in org_file.org_def.grades:
            valid = sorted(org_file.org_def.grades.keys())
            result.error(
                f"Path '{entry.path}': grade {entry.grade} not defined for org '{org_file.org}'. "
                f"Valid grades: {valid}",
                file=path,
            )

        # Vertical in vocabulary
        if entry.vertical not in vocab.verticals:
            result.error(
                f"Path '{entry.path}': vertical '{entry.vertical}' not in vocabulary. "
                f"Valid verticals: {vocab.verticals}",
                file=path,
            )

        # Scope in vocabulary
        if entry.scope not in vocab.scopes:
            result.error(
                f"Path '{entry.path}': scope '{entry.scope}' not in vocabulary. "
                f"Valid scopes: {vocab.scopes}",
                file=path,
            )

        # Path should start with org name (convention check)
        if not entry.path.startswith(f"{org_file.org}/"):
            result.warn(
                f"Path '{entry.path}' doesn't start with '{org_file.org}/' — "
                "unexpected for this org file",
                file=path,
            )

        # Spaces in path (valid but surprising)
        if " " in entry.path:
            result.warn(
                f"Path '{entry.path}' contains spaces — valid but may cause issues with some tools",
                file=path,
            )

    return result


def validate_agent_registry(
    registry: AgentRegistry,
    vocab: Vocabulary,
    known_orgs: dict[str, OrgDataFile],
    path: Path,
) -> ValidationResult:
    """Cross-reference checks for the agent registry."""
    result = ValidationResult()

    seen_names: set[str] = set()
    for agent in registry.agents:

        # Duplicate agent names
        if agent.name in seen_names:
            result.error(f"Duplicate agent name '{agent.name}'", file=path)
        seen_names.add(agent.name)

        # No access grants
        if not agent.access:
            result.warn(f"Agent '{agent.name}' has no access grants", file=path)
            continue

        for grant in agent.access:

            # Org must be known (defined by a loaded org file)
            if grant.org not in known_orgs:
                result.error(
                    f"Agent '{agent.name}': org '{grant.org}' has no org file in registry/orgs/. "
                    f"Known orgs: {sorted(known_orgs.keys())}",
                    file=path,
                )
                continue

            org_grades = known_orgs[grant.org].org_def.grades

            # Grade defined for this org
            if grant.grade not in org_grades:
                result.error(
                    f"Agent '{agent.name}': grade {grant.grade} not defined for org '{grant.org}'. "
                    f"Valid grades: {sorted(org_grades.keys())}",
                    file=path,
                )

            # Vertical: specific value must be in vocabulary (or 'any')
            if grant.vertical != "any" and grant.vertical not in vocab.verticals:
                result.error(
                    f"Agent '{agent.name}': vertical '{grant.vertical}' not in vocabulary. "
                    f"Valid verticals: {vocab.verticals} or 'any'",
                    file=path,
                )

            # Scope: specific value must be in vocabulary (or 'global')
            if grant.scope != "global" and grant.scope not in vocab.scopes:
                result.error(
                    f"Agent '{agent.name}': scope '{grant.scope}' not in vocabulary. "
                    f"Valid scopes: {vocab.scopes} or 'global'",
                    file=path,
                )

    return result


def validate_all(
    vocab: Vocabulary,
    vocab_path: Path,
    org_files: list[tuple[OrgDataFile, Path]],
    agent_registry: AgentRegistry,
    agents_path: Path,
) -> ValidationResult:
    """Run all validation passes and return a combined result."""
    combined = ValidationResult()
    known_orgs = {of.org: of for of, _ in org_files}

    combined.merge(validate_vocabulary(vocab, vocab_path))

    for org_file, path in org_files:
        combined.merge(validate_org_file(org_file, vocab, known_orgs, path))

    combined.merge(validate_agent_registry(agent_registry, vocab, known_orgs, agents_path))

    return combined
