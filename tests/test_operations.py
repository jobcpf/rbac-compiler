"""Tests for the high-level operations layer (consumed by CLI and future GUI)."""

from pathlib import Path

import pytest

from rbac_compiler.operations import (
    CompileResult,
    ValidateResult,
    compile_registry,
    load_registry,
    validate,
)

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"


class TestLoadRegistry:
    def test_loads_everything(self):
        loaded = load_registry(VALID)
        assert loaded.constants is not None
        assert len(loaded.org_files) == 3
        assert {of.org for of, _ in loaded.org_files} == {"arc", "cpf", "top"}
        assert loaded.agent_registry is not None
        assert loaded.constants_hash
        assert loaded.agents_hash
        assert set(loaded.org_hashes.keys()) == {"arc", "cpf", "top"}


class TestValidate:
    def test_valid_registry_ok(self):
        result: ValidateResult = validate(VALID)
        assert result.validation.ok
        assert result.loaded is not None

    def test_bad_grade_not_ok(self, tmp_path):
        import shutil
        reg = tmp_path / "registry"
        shutil.copytree(VALID, reg)
        shutil.copy(
            INVALID / "bad_grade" / "orgs" / "arc.yml",
            reg / "orgs" / "arc.yml",
        )
        result = validate(reg)
        assert not result.validation.ok


class TestCompileRegistry:
    def test_check_only_does_not_write(self, tmp_path):
        import shutil
        reg = tmp_path / "registry"
        shutil.copytree(VALID, reg)
        result: CompileResult = compile_registry(reg, check_only=True)
        assert result.validation.ok
        assert result.plan is not None
        assert result.output_path is None
        assert not (reg / ".compiled").exists()

    def test_writes_default_path(self, tmp_path):
        import shutil
        reg = tmp_path / "registry"
        shutil.copytree(VALID, reg)
        result = compile_registry(reg)
        assert result.validation.ok
        assert result.output_path == reg / ".compiled" / "compiled_plan.yml"
        assert result.output_path.exists()

    def test_writes_explicit_output(self, tmp_path):
        import shutil
        reg = tmp_path / "registry"
        shutil.copytree(VALID, reg)
        out = tmp_path / "plan.yml"
        result = compile_registry(reg, output=out)
        assert result.output_path == out
        assert out.exists()

    def test_validation_failure_returns_no_plan(self, tmp_path):
        import shutil
        reg = tmp_path / "registry"
        shutil.copytree(VALID, reg)
        shutil.copy(
            INVALID / "bad_grade" / "orgs" / "arc.yml",
            reg / "orgs" / "arc.yml",
        )
        result = compile_registry(reg)
        assert not result.validation.ok
        assert result.plan is None
        assert result.output_path is None
