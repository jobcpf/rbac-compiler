"""Tests for Pydantic model validation (within-file rules)."""

import pytest
from pydantic import ValidationError

from rbac_compiler.models import (
    AccessGrant,
    Agent,
    Constants,
    DataEntry,
    OrgDefinition,
    ShareClass,
    Shares,
)


class TestConstants:
    def test_valid_defaults(self):
        c = Constants.model_validate({
            "meta": {"version": "0.4"},
        })
        assert c.grade_range.min == 0
        assert c.grade_range.max == 20
        assert c.reserved_tokens.any_vertical == "any"
        assert c.reserved_tokens.global_scope == "global"
        assert c.compiler.schema_version == "0.4"
        assert c.admins == []

    def test_explicit_values_accepted(self):
        c = Constants.model_validate({
            "meta": {"version": "0.4"},
            "grade_range": {"min": 0, "max": 10},
            "reserved_tokens": {"any_vertical": "any", "global_scope": "global"},
            "compiler": {
                "registry_dir": "~/registry",
                "orgs_dir": "orgs",
                "agents_dir": "agents",
                "output_file": ".compiled/compiled_plan.yml",
                "schema_version": "0.4",
            },
            "admins": ["beaver", "ansi"],
        })
        assert c.grade_range.max == 10
        assert c.admins == ["beaver", "ansi"]

    def test_invalid_admin_username_rejected(self):
        with pytest.raises(ValidationError, match="valid Linux username"):
            Constants.model_validate({
                "meta": {"version": "0.4"},
                "admins": ["BadUser"],
            })

    def test_extra_fields_accepted(self):
        """Constants tolerates fields owned by other platform tools."""
        c = Constants.model_validate({
            "meta": {"version": "0.4"},
            "agent_user_defaults": {
                "samba_enabled": True,
                "shell": "/usr/sbin/nologin",
                "create_home": False,
            },
            "directory_defaults": {"mode": "02770", "apply_default_acl": True},
        })
        # Extra fields are preserved on the model instance but not validated.
        assert c.meta.version == "0.4"


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

    def test_extra_fields_accepted(self):
        """Agent tolerates fields owned by other platform tools (cert, local_user)."""
        a = Agent.model_validate({
            "name": "agent_arc_exec",
            "description": "ARC Exec Agent",
            "access": [{"org": "arc", "grade": 0, "vertical": "any", "scope": "global"}],
            "local_user": {"samba_enabled": True},
            "cert": {"issue": True, "validity_days": 365},
        })
        assert a.name == "agent_arc_exec"


class TestShareClass:
    def test_valid(self):
        sc = ShareClass(org="arc", grade=3, vertical="tech", scope="mz")
        assert sc.org == "arc"
        assert sc.grade == 3


class TestShares:
    def test_all_fields_optional(self):
        s = Shares()
        assert s.configs is None
        assert s.memory is None
        assert s.sessions is None
        assert s.scratch is None

    def test_partial_override(self):
        s = Shares(scratch="/mnt/raid/custom/scratch/")
        assert s.scratch == "/mnt/raid/custom/scratch/"
        assert s.memory is None


class TestAgentV04Schema:
    def test_share_class_optional(self):
        """An agent without share_class is valid (just no classified surfaces)."""
        a = Agent.model_validate({
            "name": "agent_orphan",
            "access": [{"org": "arc", "grade": 5, "vertical": "tech", "scope": "uk"}],
        })
        assert a.share_class is None

    def test_share_class_attached(self):
        a = Agent.model_validate({
            "name": "agent_x",
            "share_class": {"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
        })
        assert a.share_class is not None
        assert a.share_class.org == "arc"
        assert a.access == []  # access[] is optional in v0.4

    def test_sub_agents_valid_identifiers(self):
        a = Agent.model_validate({
            "name": "agent_x",
            "sub_agents": ["literature_review", "fact_check"],
        })
        assert a.sub_agents == ["literature_review", "fact_check"]

    def test_sub_agent_main_reserved(self):
        with pytest.raises(ValidationError, match="reserved"):
            Agent.model_validate({"name": "agent_x", "sub_agents": ["main"]})

    def test_sub_agent_duplicate_rejected(self):
        with pytest.raises(ValidationError, match="duplicate"):
            Agent.model_validate({"name": "agent_x", "sub_agents": ["foo", "foo"]})

    def test_sub_agent_invalid_chars_rejected(self):
        with pytest.raises(ValidationError, match="not a valid identifier"):
            Agent.model_validate({"name": "agent_x", "sub_agents": ["Bad-Name"]})

    def test_shares_block(self):
        a = Agent.model_validate({
            "name": "agent_x",
            "share_class": {"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
            "shares": {"scratch": "/mnt/raid/custom/scratch/"},
        })
        assert a.shares is not None
        assert a.shares.scratch == "/mnt/raid/custom/scratch/"
        assert a.shares.memory is None
