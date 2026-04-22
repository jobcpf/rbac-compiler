"""
Loads registry YAML files from disk.

Returns parsed model instances + SHA-256 hashes of each file.
Raises RegistryLoadError on any I/O or parse failure.
Uses ruamel.yaml (not PyYAML) for better parse error messages with line numbers.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError

from .errors import RegistryLoadError
from .models import AgentRegistry, Constants, OrgDataFile


def _load_yaml(path: Path) -> tuple[Any, str]:
    """Read a YAML file. Returns (parsed_data, sha256_hex).

    Raises RegistryLoadError on missing file, permission error, or YAML parse failure.
    """
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        raise RegistryLoadError(f"File not found: {path}")
    except PermissionError as exc:
        raise RegistryLoadError(f"Permission denied reading {path}: {exc}")
    except OSError as exc:
        raise RegistryLoadError(f"Cannot read {path}: {exc}")

    sha256 = hashlib.sha256(content).hexdigest()

    yaml = YAML()
    yaml.preserve_quotes = True
    try:
        data = yaml.load(content)
    except DuplicateKeyError as exc:
        raise RegistryLoadError(f"Duplicate key in {path}: {exc}")
    except Exception as exc:
        raise RegistryLoadError(f"YAML parse error in {path}: {exc}")

    if data is None:
        raise RegistryLoadError(f"File is empty or contains only comments: {path}")
    if not isinstance(data, dict):
        raise RegistryLoadError(
            f"{path}: expected a YAML mapping at top level, got {type(data).__name__}"
        )

    return data, sha256


def load_constants(path: Path) -> tuple[Constants, str]:
    data, sha256 = _load_yaml(path)
    try:
        return Constants.model_validate(data), sha256
    except Exception as exc:
        raise RegistryLoadError(f"{path}: schema error: {exc}") from exc


def load_org_file(path: Path) -> tuple[OrgDataFile, str]:
    data, sha256 = _load_yaml(path)
    try:
        return OrgDataFile.model_validate(data), sha256
    except Exception as exc:
        raise RegistryLoadError(f"{path}: schema error: {exc}") from exc


def load_agent_registry(path: Path) -> tuple[AgentRegistry, str]:
    data, sha256 = _load_yaml(path)
    try:
        return AgentRegistry.model_validate(data), sha256
    except Exception as exc:
        raise RegistryLoadError(f"{path}: schema error: {exc}") from exc


def discover_org_files(registry_dir: Path, orgs_subdir: str = "orgs") -> list[Path]:
    """Return all .yml files under registry_dir/<orgs_subdir>/, sorted by name."""
    orgs_dir = registry_dir / orgs_subdir
    if not orgs_dir.is_dir():
        return []
    return sorted(orgs_dir.glob("*.yml"))
