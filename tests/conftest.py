"""Shared pytest fixtures."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_dir() -> Path:
    return FIXTURES / "valid"


@pytest.fixture
def constants(valid_dir):
    from rbac_compiler.loader import load_constants
    c, _ = load_constants(valid_dir / "classification_constants.yml")
    return c


@pytest.fixture
def org_files(valid_dir):
    from rbac_compiler.loader import discover_org_files, load_org_file
    paths = discover_org_files(valid_dir)
    return [(load_org_file(p)[0], p) for p in paths]


@pytest.fixture
def agent_registry(valid_dir):
    from rbac_compiler.loader import load_agent_registry
    reg, _ = load_agent_registry(valid_dir / "agent_registry.yml")
    return reg
