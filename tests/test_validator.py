"""Tests for cross-reference validation."""

from pathlib import Path

import pytest

from rbac_compiler.loader import load_agent_registry, load_org_file, load_vocabulary
from rbac_compiler.validator import (
    validate_agent_registry,
    validate_all,
    validate_org_file,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"


def _vocab():
    v, _ = load_vocabulary(VALID / "classification_vocabulary.yml")
    return v


def _org(path):
    of, _ = load_org_file(path)
    return of


def _agents(path):
    r, _ = load_agent_registry(path)
    return r


class TestValidOrgFile:
    def test_valid_arc_passes(self):
        vocab = _vocab()
        org_file = _org(VALID / "orgs" / "arc.yml")
        result = validate_org_file(org_file, vocab, {}, VALID / "orgs" / "arc.yml")
        assert result.ok

    def test_valid_cpf_passes(self):
        vocab = _vocab()
        org_file = _org(VALID / "orgs" / "cpf.yml")
        result = validate_org_file(org_file, vocab, {}, VALID / "orgs" / "cpf.yml")
        assert result.ok


class TestBadGrade:
    def test_bad_grade_is_error(self):
        vocab = _vocab()
        org_file = _org(INVALID / "bad_grade" / "orgs" / "arc.yml")
        result = validate_org_file(org_file, vocab, {}, INVALID / "bad_grade" / "orgs" / "arc.yml")
        assert not result.ok
        assert any("grade" in str(e).lower() for e in result.errors)

    def test_error_message_mentions_valid_grades(self):
        vocab = _vocab()
        org_file = _org(INVALID / "bad_grade" / "orgs" / "arc.yml")
        result = validate_org_file(org_file, vocab, {}, INVALID / "bad_grade" / "orgs" / "arc.yml")
        error_text = " ".join(str(e) for e in result.errors)
        assert "99" in error_text


class TestDuplicatePath:
    def test_duplicate_path_is_error(self):
        vocab = _vocab()
        org_file = _org(INVALID / "duplicate_path" / "orgs" / "arc.yml")
        result = validate_org_file(org_file, vocab, {}, INVALID / "duplicate_path" / "orgs" / "arc.yml")
        assert not result.ok
        assert any("duplicate" in str(e).lower() for e in result.errors)


class TestDuplicateAgent:
    def test_duplicate_agent_name_is_error(self, vocab):
        agents = _agents(INVALID / "duplicate_agent" / "agent_registry.yml")
        known_orgs = {}  # not needed for name-dup check
        result = validate_agent_registry(
            agents, vocab, known_orgs, INVALID / "duplicate_agent" / "agent_registry.yml"
        )
        assert not result.ok
        assert any("duplicate" in str(e).lower() for e in result.errors)


class TestMissingOrg:
    def test_agent_referencing_unknown_org_is_error(self, vocab):
        agents = _agents(INVALID / "missing_org" / "agent_registry.yml")
        arc_file = _org(INVALID / "missing_org" / "orgs" / "arc.yml")
        known_orgs = {"arc": arc_file}
        result = validate_agent_registry(
            agents, vocab, known_orgs, INVALID / "missing_org" / "agent_registry.yml"
        )
        assert not result.ok
        assert any("nonexistent_org" in str(e) for e in result.errors)


class TestWarnings:
    def test_filename_mismatch_warns(self, tmp_path):
        """Org file named differently from declared org key should warn."""
        vocab = _vocab()
        import shutil
        wrong_name = tmp_path / "orgs" / "wrong.yml"
        wrong_name.parent.mkdir()
        shutil.copy(VALID / "orgs" / "arc.yml", wrong_name)
        org_file = _org(wrong_name)
        result = validate_org_file(org_file, vocab, {}, wrong_name)
        assert any("basename" in str(w) for w in result.warnings)

    def test_path_not_starting_with_org_warns(self, tmp_path):
        """Data entry path not starting with org name should warn."""
        vocab = _vocab()
        org_file_path = tmp_path / "orgs" / "arc.yml"
        org_file_path.parent.mkdir()
        org_file_path.write_text(
            "meta:\n  version: '0.1'\norg: arc\n"
            "definition:\n  name: ARC\n  grades:\n    0: ''\n    1: ''\n"
            "data:\n  - path: dropbox/Finance\n    grade: 1\n    vertical: finance\n    scope: global\n"
        )
        org_file = _org(org_file_path)
        result = validate_org_file(org_file, vocab, {}, org_file_path)
        assert any("arc/" in str(w) for w in result.warnings)


class TestValidateAll:
    def test_full_valid_registry_passes(self, valid_dir):
        vocab, _ = load_vocabulary(valid_dir / "classification_vocabulary.yml")
        from rbac_compiler.loader import discover_org_files
        org_paths = discover_org_files(valid_dir)
        org_files = [(load_org_file(p)[0], p) for p in org_paths]
        agents, _ = load_agent_registry(valid_dir / "agent_registry.yml")
        result = validate_all(vocab, valid_dir / "classification_vocabulary.yml", org_files, agents, valid_dir / "agent_registry.yml")
        assert result.ok
