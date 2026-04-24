"""Tests for Pydantic model validation (within-file rules)."""

import pytest
from pydantic import ValidationError

from rbac_compiler.models import (
    AccessGrant,
    Agent,
    Constants,
    DataEntry,
    OrgDefinition,
)


class TestConstants:
    def test_valid_defaults(self):
        c = Constants.model_validate({
            "meta": {"version": "0.2"},
        })
        assert c.grade_range.min == 0
        assert c.grade_range.max == 20
        assert c.reserved_tokens.any_vertical == "any"
        assert c.reserved_tokens.global_scope == "global"
        assert c.compiler.schema_version == "0.2"
        assert c.admins == []

    def test_explicit_values_accepted(self):
        c = Constants.model_validate({
            "meta": {"version": "0.2"},
            "grade_range": {"min": 0, "max": 10},
            "reserved_tokens": {"any_vertical": "any", "global_scope": "global"},
            "compiler": {
                "registry_dir": "~/registry",
                "orgs_dir": "orgs",
                "agents_dir": "agents",
                "output_file": ".compiled/compiled_plan.yml",
                "schema_version": "0.2",
            },
            "admins": ["beaver", "ansi"],
        })
        assert c.grade_range.max == 10
        assert c.admins == ["beaver", "ansi"]

    def test_invalid_admin_username_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Constants.model_validate({
                "meta": {"version": "0.2"},
                "admins": ["BadUser"],
            })


class TestOrgDefinition:
    def test_valid(self):
        od = OrgDefinition.model_validate({
            "key": "arc",
            "name": "ARC Power",
            "verticals": ["any", "tech", "finance"],
            "scopes": ["global", "mz"],
            "grades": {0: "", 1: "", 2: ""},
        })
        assert od.key == "arc"
        assert "any" in od.verticals
        assert "global" in od.scopes
        assert 0 in od.grades

    def test_grades_parsed_from_string_keys(self):
        od = OrgDefinition.model_validate({
            "key": "arc",
            "name": "Test",
            "verticals": ["any", "tech"],
            "scopes": ["global"],
            "grades": {"0": "Exec", "1": "Staff"},
        })
        assert od.grades[0] == "Exec"

    def test_missing_any_in_verticals_rejected(self):
        with pytest.raises(ValidationError, match="any"):
            OrgDefinition.model_validate({
                "key": "arc",
                "name": "Test",
                "verticals": ["tech"],
                "scopes": ["global"],
                "grades": {0: ""},
            })

    def test_missing_global_in_scopes_rejected(self):
        with pytest.raises(ValidationError, match="global"):
            OrgDefinition.model_validate({
                "key": "arc",
                "name": "Test",
                "verticals": ["any", "tech"],
                "scopes": ["mz"],
                "grades": {0: ""},
            })

    def test_empty_verticals_rejected(self):
        with pytest.raises(ValidationError):
            OrgDefinition.model_validate({
                "key": "arc",
                "name": "Test",
                "verticals": [],
                "scopes": ["global"],
                "grades": {0: ""},
            })

    def test_empty_grades_rejected(self):
        with pytest.raises(ValidationError, match="empty"):
            OrgDefinition.model_validate({
                "key": "arc",
                "name": "Test",
                "verticals": ["any", "tech"],
                "scopes": ["global"],
                "grades": {},
            })

    def test_invalid_key_rejected(self):
        with pytest.raises(ValidationError):
            OrgDefinition.model_validate({
                "key": "ARC-Power",
                "name": "Test",
                "verticals": ["any", "tech"],
                "scopes": ["global"],
                "grades": {0: ""},
            })


class TestDataEntry:
    def test_valid(self):
        e = DataEntry(path="arc/Finance", grade=2, vertical="finance", scope="global")
        assert e.path == "arc/Finance"

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError, match="\\.\\."):
            DataEntry(path="../secret", grade=0, vertical="tech", scope="global")

    def test_absolute_path_rejected(self):
        with pytest.raises(ValidationError, match="start with"):
            DataEntry(path="/mnt/raid/arc", grade=0, vertical="tech", scope="global")

    def test_empty_path_rejected(self):
        with pytest.raises(ValidationError):
            DataEntry(path="", grade=0, vertical="tech", scope="global")

    def test_any_vertical_accepted_by_model(self):
        e = DataEntry(path="agents/_shared/arc/handoffs", grade=5, vertical="any", scope="global")
        assert e.vertical == "any"


class TestAgent:
    def test_valid_name(self):
        a = Agent(name="agent_arc_tech", access=[
            AccessGrant(org="arc", grade=2, vertical="tech", scope="mz")
        ])
        assert a.name == "agent_arc_tech"

    def test_name_uppercase_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Agent(name="Agent_Arc", access=[
                AccessGrant(org="arc", grade=0, vertical="any", scope="global")
            ])

    def test_name_starts_with_digit_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Agent(name="1agent", access=[
                AccessGrant(org="arc", grade=0, vertical="any", scope="global")
            ])

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Agent(name="a" * 33, access=[
                AccessGrant(org="arc", grade=0, vertical="any", scope="global")
            ])

    def test_name_with_hyphen_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Agent(name="agent-name", access=[
                AccessGrant(org="arc", grade=0, vertical="any", scope="global")
            ])
