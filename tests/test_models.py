"""Tests for Pydantic model validation (within-file rules)."""

import pytest
from pydantic import ValidationError

from rbac_compiler.models import (
    AccessGrant,
    Agent,
    DataEntry,
    OrgDefinition,
    Vocabulary,
)


class TestVocabulary:
    def test_valid(self):
        v = Vocabulary.model_validate({
            "meta": {"version": "0.1"},
            "verticals": ["tech", "finance"],
            "scopes": ["global", "mz"],
        })
        assert "global" in v.scopes

    def test_missing_global_scope(self):
        with pytest.raises(ValidationError, match="global"):
            Vocabulary.model_validate({
                "meta": {"version": "0.1"},
                "verticals": ["tech"],
                "scopes": ["mz"],
            })

    def test_empty_verticals(self):
        with pytest.raises(ValidationError):
            Vocabulary.model_validate({
                "meta": {"version": "0.1"},
                "verticals": [],
                "scopes": ["global"],
            })

    def test_empty_scopes(self):
        with pytest.raises(ValidationError):
            Vocabulary.model_validate({
                "meta": {"version": "0.1"},
                "verticals": ["tech"],
                "scopes": [],
            })


class TestOrgDefinition:
    def test_valid(self):
        od = OrgDefinition.model_validate({
            "name": "ARC Power",
            "grades": {0: "", 1: "", 2: ""},
        })
        assert 0 in od.grades
        assert 2 in od.grades

    def test_grades_parsed_from_int_keys(self):
        od = OrgDefinition.model_validate({
            "name": "Test",
            "grades": {"0": "Exec", "1": "Staff"},
        })
        assert od.grades[0] == "Exec"

    def test_empty_grades(self):
        with pytest.raises(ValidationError, match="empty"):
            OrgDefinition.model_validate({"name": "Test", "grades": {}})


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
