"""Tests for cross-reference validation."""

from pathlib import Path

import pytest

from rbac_compiler.loader import load_agent_registry, load_constants, load_org_file
from rbac_compiler.validator import (
    validate_agent_registry,
    validate_all,
    validate_org_file,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"


def _constants():
    c, _ = load_constants(VALID / "classification_constants.yml")
    return c


def _org(path):
    of, _ = load_org_file(path)
    return of


def _agents(path):
    r, _ = load_agent_registry(path)
    return r


class TestValidOrgFile:
    def test_valid_arc_passes(self):
        constants = _constants()
        org_file = _org(VALID / "orgs" / "arc.yml")
        result = validate_org_file(org_file, constants, {}, VALID / "orgs" / "arc.yml")
        assert result.ok

    def test_valid_cpf_passes(self):
        constants = _constants()
        org_file = _org(VALID / "orgs" / "cpf.yml")
        result = validate_org_file(org_file, constants, {}, VALID / "orgs" / "cpf.yml")
        assert result.ok


class TestBadGrade:
    def test_bad_grade_is_error(self):
        constants = _constants()
        org_file = _org(INVALID / "bad_grade" / "orgs" / "arc.yml")
        result = validate_org_file(
            org_file, constants, {}, INVALID / "bad_grade" / "orgs" / "arc.yml"
        )
        assert not result.ok
        assert any("grade" in str(e).lower() for e in result.errors)

    def test_error_message_mentions_invalid_grade(self):
        constants = _constants()
        org_file = _org(INVALID / "bad_grade" / "orgs" / "arc.yml")
        result = validate_org_file(
            org_file, constants, {}, INVALID / "bad_grade" / "orgs" / "arc.yml"
        )
        error_text = " ".join(str(e) for e in result.errors)
        assert "99" in error_text


class TestDuplicatePath:
    def test_duplicate_path_is_error(self):
        constants = _constants()
        org_file = _org(INVALID / "duplicate_path" / "orgs" / "arc.yml")
        result = validate_org_file(
            org_file, constants, {}, INVALID / "duplicate_path" / "orgs" / "arc.yml"
        )
        assert not result.ok
        assert any("duplicate" in str(e).lower() for e in result.errors)


class TestDuplicateAgent:
    def test_duplicate_agent_name_is_error(self, constants):
        agents = _agents(INVALID / "duplicate_agent" / "agent_registry.yml")
        result = validate_agent_registry(
            agents, constants, {}, INVALID / "duplicate_agent" / "agent_registry.yml"
        )
        assert not result.ok
        assert any("duplicate" in str(e).lower() for e in result.errors)


class TestMissingOrg:
    def test_agent_referencing_unknown_org_is_error(self, constants):
        agents = _agents(INVALID / "missing_org" / "agent_registry.yml")
        arc_file = _org(INVALID / "missing_org" / "orgs" / "arc.yml")
        known_orgs = {"arc": arc_file}
        result = validate_agent_registry(
            agents, constants, known_orgs, INVALID / "missing_org" / "agent_registry.yml"
        )
        assert not result.ok
        assert any("nonexistent_org" in str(e) for e in result.errors)


class TestSchemaVersionCheck:
    def test_wrong_version_org_file_is_error(self, tmp_path):
        constants = _constants()
        org_path = tmp_path / "orgs" / "arc.yml"
        org_path.parent.mkdir()
        org_path.write_text(
            "meta:\n  version: '0.1'\n"
            "org_definition:\n"
            "  key: arc\n  name: ARC\n"
            "  verticals:\n    - any\n    - tech\n"
            "  scopes:\n    - global\n"
            "  grades:\n    0: ''\n"
            "data: []\n"
        )
        from rbac_compiler.models import AgentRegistry, Meta
        org_file = _org(org_path)
        agents = AgentRegistry(meta=Meta(version="0.2"), agents=[])
        result = validate_all(
            constants,
            VALID / "classification_constants.yml",
            [(org_file, org_path)],
            agents,
            VALID / "agent_registry.yml",
        )
        assert not result.ok
        assert any("version" in str(e).lower() for e in result.errors)


class TestWarnings:
    def test_filename_mismatch_warns(self, tmp_path):
        constants = _constants()
        import shutil
        wrong_name = tmp_path / "orgs" / "wrong.yml"
        wrong_name.parent.mkdir()
        shutil.copy(VALID / "orgs" / "arc.yml", wrong_name)
        org_file = _org(wrong_name)
        result = validate_org_file(org_file, constants, {}, wrong_name)
        assert any("basename" in str(w) for w in result.warnings)


class TestValidateAll:
    def test_full_valid_registry_passes(self, valid_dir):
        constants, _ = load_constants(valid_dir / "classification_constants.yml")
        from rbac_compiler.loader import discover_org_files
        org_paths = discover_org_files(valid_dir)
        org_files = [(load_org_file(p)[0], p) for p in org_paths]
        agents, _ = load_agent_registry(valid_dir / "agent_registry.yml")
        result = validate_all(
            constants,
            valid_dir / "classification_constants.yml",
            org_files,
            agents,
            valid_dir / "agent_registry.yml",
        )
        assert result.ok
