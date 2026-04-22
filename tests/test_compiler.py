"""Tests for core compilation logic — group computation."""

from pathlib import Path

import pytest

from rbac_compiler.compiler import (
    compile_plan,
    group_name,
    groups_for_agent,
    groups_for_grant,
)
from rbac_compiler.models import (
    AccessGrant,
    Agent,
    AgentRegistry,
    Constants,
    DataEntry,
    Meta,
    OrgDataFile,
    OrgDefinition,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_constants() -> Constants:
    return Constants.model_validate({"meta": {"version": "0.2"}})


def _make_org(
    org_key: str = "arc",
    max_grade: int = 4,
    verticals: list[str] | None = None,
    scopes: list[str] | None = None,
) -> OrgDataFile:
    return OrgDataFile.model_validate({
        "meta": {"version": "0.2"},
        "org_definition": {
            "key": org_key,
            "name": org_key.upper(),
            "verticals": verticals or ["tech", "finance"],
            "scopes": scopes or ["global", "mz", "rw"],
            "grades": {i: "" for i in range(max_grade + 1)},
        },
        "data": [],
    })


def _grant(org: str = "arc", grade: int = 0, vertical: str = "tech", scope: str = "mz") -> AccessGrant:
    return AccessGrant(org=org, grade=grade, vertical=vertical, scope=scope)


# ── group_name ────────────────────────────────────────────────────────────────

class TestGroupName:
    def test_format(self):
        assert group_name("arc", 2, "finance", "global") == "arc_g2_finance_global"

    def test_zero_grade(self):
        assert group_name("cpf", 0, "tech", "uk") == "cpf_g0_tech_uk"

    def test_wildcard_tokens(self):
        assert group_name("arc", 5, "any", "global") == "arc_g5_any_global"


# ── groups_for_grant ──────────────────────────────────────────────────────────

class TestGroupsForGrant:
    def setup_method(self):
        self.constants = _make_constants()
        # org with verticals=[tech, finance], scopes=[global, mz, rw], grades 0-4
        self.org = _make_org("arc", max_grade=4)

    def test_specific_vertical_and_scope_always_adds_wildcards(self):
        # vertical=tech, scope=mz → also get _any_ and _global wildcard groups
        grant = _grant(grade=3, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.constants)
        # grades [3,4], verticals [tech, any], scopes [mz, global] → 2×2×2 = 8
        assert len(groups) == 8
        assert "arc_g3_tech_mz" in groups
        assert "arc_g3_tech_global" in groups
        assert "arc_g3_any_mz" in groups
        assert "arc_g3_any_global" in groups
        assert "arc_g4_tech_mz" in groups

    def test_any_vertical_expands_all_org_verticals(self):
        grant = _grant(grade=4, vertical="any", scope="mz")
        groups = groups_for_grant(grant, self.org, self.constants)
        # grades [4], verticals [tech, finance, any], scopes [mz, global] → 1×3×2 = 6
        assert len(groups) == 6
        assert "arc_g4_tech_mz" in groups
        assert "arc_g4_finance_mz" in groups
        assert "arc_g4_any_mz" in groups
        assert "arc_g4_tech_global" in groups

    def test_global_scope_expands_all_org_scopes(self):
        grant = _grant(grade=4, vertical="tech", scope="global")
        groups = groups_for_grant(grant, self.org, self.constants)
        # grades [4], verticals [tech, any], scopes [global, mz, rw] → 1×2×3 = 6
        assert len(groups) == 6
        assert "arc_g4_tech_global" in groups
        assert "arc_g4_tech_mz" in groups
        assert "arc_g4_tech_rw" in groups
        assert "arc_g4_any_global" in groups

    def test_any_vertical_global_scope_full_matrix(self):
        grant = _grant(grade=4, vertical="any", scope="global")
        groups = groups_for_grant(grant, self.org, self.constants)
        # grades [4], verticals [tech, finance, any], scopes [global, mz, rw] → 1×3×3 = 9
        assert len(groups) == 9
        assert "arc_g4_tech_global" in groups
        assert "arc_g4_finance_rw" in groups
        assert "arc_g4_any_global" in groups

    def test_grade_0_includes_all_grades(self):
        grant = _grant(grade=0, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.constants)
        # grades [0-4], verticals [tech, any], scopes [mz, global] → 5×2×2 = 20
        assert len(groups) == 20
        for g in range(5):
            assert f"arc_g{g}_tech_mz" in groups

    def test_grade_envelope_excludes_more_privileged_grades(self):
        grant = _grant(grade=3, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.constants)
        assert "arc_g0_tech_mz" not in groups
        assert "arc_g2_tech_mz" not in groups
        assert "arc_g3_tech_mz" in groups


# ── groups_for_agent ──────────────────────────────────────────────────────────

class TestGroupsForAgent:
    def setup_method(self):
        self.constants = _make_constants()
        self.arc = _make_org("arc", max_grade=4)
        self.cpf = _make_org("cpf", max_grade=2, verticals=["advisory", "finance"], scopes=["global", "uk"])
        self.org_map = {"arc": self.arc, "cpf": self.cpf}

    def test_single_grant(self):
        agent = Agent(name="agent_test", access=[_grant(grade=4, vertical="tech", scope="mz")])
        groups = groups_for_agent(agent, self.org_map, self.constants)
        assert "arc_g4_tech_mz" in groups
        assert "arc_g4_any_mz" in groups      # wildcard always added
        assert "arc_g4_tech_global" in groups  # global wildcard always added

    def test_multiple_org_grants_union(self):
        agent = Agent(name="agent_multi", access=[
            _grant(org="arc", grade=4, vertical="tech", scope="mz"),
            _grant(org="cpf", grade=2, vertical="finance", scope="global"),
        ])
        groups = groups_for_agent(agent, self.org_map, self.constants)
        assert "arc_g4_tech_mz" in groups
        assert "cpf_g2_finance_global" in groups
        assert "cpf_g2_finance_uk" in groups   # global expands to all cpf scopes

    def test_output_is_sorted(self):
        agent = Agent(name="agent_sort", access=[
            _grant(grade=3, vertical="finance", scope="mz"),
            _grant(grade=3, vertical="tech", scope="mz"),
        ])
        groups = groups_for_agent(agent, self.org_map, self.constants)
        assert groups == sorted(groups)

    def test_unknown_org_in_grant_skipped(self):
        agent = Agent(name="agent_ghost", access=[
            AccessGrant(org="unknown", grade=0, vertical="tech", scope="mz")
        ])
        groups = groups_for_agent(agent, self.org_map, self.constants)
        assert groups == []


# ── compile_plan ──────────────────────────────────────────────────────────────

class TestCompilePlan:
    def setup_method(self):
        self.constants = _make_constants()
        self.org = _make_org("arc", max_grade=4)
        self.org.data = [
            DataEntry(path="arc/Finance", grade=2, vertical="finance", scope="global"),
            DataEntry(path="arc/Tech", grade=3, vertical="tech", scope="mz"),
        ]
        self.agent_registry = AgentRegistry(
            meta=Meta(version="0.2"),
            agents=[
                Agent(name="agent_a", access=[_grant(grade=4, vertical="tech", scope="mz")])
            ],
        )
        self.org_files = [(self.org, Path("orgs/arc.yml"))]

    def test_fileserver_admins_always_present(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.2"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        assert "fileserver_admins" in plan.required_groups

    def test_data_entry_group_included(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.2"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        assert "arc_g2_finance_global" in plan.required_groups

    def test_agent_groups_included(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        assert "arc_g4_tech_mz" in plan.required_groups
        assert "arc_g4_any_mz" in plan.required_groups

    def test_directory_classifications_sorted_by_path(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        paths = [dc.path for dc in plan.directory_classifications]
        assert paths == sorted(paths)

    def test_directory_classification_mode(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.2"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        for dc in plan.directory_classifications:
            assert dc.mode == "02770"
            assert dc.apply_default_acl is True

    def test_required_groups_sorted(self):
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        assert plan.required_groups == sorted(plan.required_groups)

    def test_any_vertical_data_entry_produces_any_group(self):
        from rbac_compiler.models import DataEntry
        self.org.data.append(
            DataEntry(path="agents/_shared/arc/handoffs", grade=4, vertical="any", scope="global")
        )
        plan = compile_plan(
            constants=self.constants,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.2"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        assert "arc_g4_any_global" in plan.required_groups
