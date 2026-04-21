"""Tests for core compilation logic — group computation."""

import pytest

from rbac_compiler.compiler import (
    compile_plan,
    group_name,
    groups_for_agent,
    groups_for_grant,
)
from rbac_compiler.models import AccessGrant, Agent, AgentRegistry, OrgDefinition, OrgDataFile


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_vocab(verticals=None, scopes=None):
    from rbac_compiler.models import Meta, Vocabulary
    return Vocabulary(
        meta=Meta(version="0.1"),
        verticals=verticals or ["tech", "finance"],
        scopes=scopes or ["global", "mz", "rw"],
    )


def _make_org(org_key="arc", max_grade=4):
    from rbac_compiler.models import Meta
    return OrgDataFile(
        meta=Meta(version="0.1"),
        org=org_key,
        definition=OrgDefinition(
            name=org_key.upper(),
            grades={i: "" for i in range(max_grade + 1)},
        ),
        data=[],
    )


def _grant(org="arc", grade=0, vertical="tech", scope="mz"):
    return AccessGrant(org=org, grade=grade, vertical=vertical, scope=scope)


# ── group_name ────────────────────────────────────────────────────────────────

class TestGroupName:
    def test_format(self):
        assert group_name("arc", 2, "finance", "global") == "arc_g2_finance_global"

    def test_zero_grade(self):
        assert group_name("cpf", 0, "tech", "uk") == "cpf_g0_tech_uk"


# ── groups_for_grant ──────────────────────────────────────────────────────────

class TestGroupsForGrant:
    def setup_method(self):
        self.vocab = _make_vocab(verticals=["tech", "finance"], scopes=["global", "mz", "rw"])
        self.org = _make_org("arc", max_grade=4)

    def test_specific_vertical_and_scope(self):
        grant = _grant(grade=3, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert groups == {"arc_g3_tech_mz", "arc_g4_tech_mz"}

    def test_any_vertical_expands_all(self):
        grant = _grant(grade=4, vertical="any", scope="mz")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert groups == {"arc_g4_tech_mz", "arc_g4_finance_mz"}

    def test_global_scope_expands_all_scopes(self):
        grant = _grant(grade=4, vertical="tech", scope="global")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert groups == {"arc_g4_tech_global", "arc_g4_tech_mz", "arc_g4_tech_rw"}

    def test_any_vertical_global_scope_full_matrix(self):
        grant = _grant(grade=4, vertical="any", scope="global")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert len(groups) == 2 * 3  # 2 verticals × 3 scopes, only grade 4
        assert "arc_g4_tech_global" in groups
        assert "arc_g4_finance_rw" in groups

    def test_grade_0_includes_all_grades(self):
        grant = _grant(grade=0, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert groups == {f"arc_g{g}_tech_mz" for g in range(5)}

    def test_grade_envelope_excludes_lower_grades(self):
        grant = _grant(grade=3, vertical="tech", scope="mz")
        groups = groups_for_grant(grant, self.org, self.vocab)
        assert "arc_g0_tech_mz" not in groups
        assert "arc_g2_tech_mz" not in groups
        assert "arc_g3_tech_mz" in groups


# ── groups_for_agent ──────────────────────────────────────────────────────────

class TestGroupsForAgent:
    def setup_method(self):
        self.vocab = _make_vocab(verticals=["tech", "finance"], scopes=["global", "mz"])
        self.arc = _make_org("arc", max_grade=4)
        self.cpf = _make_org("cpf", max_grade=2)
        self.org_map = {"arc": self.arc, "cpf": self.cpf}

    def test_single_grant(self):
        agent = Agent(name="agent_test", access=[_grant(grade=4, vertical="tech", scope="mz")])
        groups = groups_for_agent(agent, self.org_map, self.vocab)
        assert groups == ["arc_g4_tech_mz"]

    def test_multiple_grants_union(self):
        agent = Agent(name="agent_multi", access=[
            _grant(org="arc", grade=4, vertical="tech", scope="mz"),
            _grant(org="cpf", grade=2, vertical="finance", scope="global"),
        ])
        groups = groups_for_agent(agent, self.org_map, self.vocab)
        assert "arc_g4_tech_mz" in groups
        assert "cpf_g2_finance_global" in groups
        assert "cpf_g2_finance_mz" in groups

    def test_output_is_sorted(self):
        agent = Agent(name="agent_sort", access=[
            _grant(grade=3, vertical="finance", scope="mz"),
            _grant(grade=3, vertical="tech", scope="mz"),
        ])
        groups = groups_for_agent(agent, self.org_map, self.vocab)
        assert groups == sorted(groups)

    def test_unknown_org_in_grant_produces_empty(self):
        agent = Agent(name="agent_ghost", access=[
            AccessGrant(org="unknown", grade=0, vertical="tech", scope="mz")
        ])
        groups = groups_for_agent(agent, self.org_map, self.vocab)
        assert groups == []


# ── compile_plan ──────────────────────────────────────────────────────────────

class TestCompilePlan:
    def setup_method(self):
        from rbac_compiler.models import DataEntry, Meta

        self.vocab = _make_vocab(verticals=["tech", "finance"], scopes=["global", "mz"])
        self.org = _make_org("arc", max_grade=4)
        self.org.data = [
            DataEntry(path="arc/Finance", grade=2, vertical="finance", scope="global"),
            DataEntry(path="arc/Tech", grade=3, vertical="tech", scope="mz"),
        ]
        self.agent_registry = AgentRegistry(
            meta=__import__("rbac_compiler.models", fromlist=["Meta"]).Meta(version="0.1"),
            agents=[
                Agent(name="agent_a", access=[_grant(grade=4, vertical="tech", scope="mz")])
            ],
        )
        from pathlib import Path
        self.org_files = [(self.org, Path("orgs/arc.yml"))]

    def test_fileserver_admins_always_present(self):
        from rbac_compiler.models import Meta
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.1"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        assert "fileserver_admins" in plan.required_groups

    def test_data_entry_group_included(self):
        from rbac_compiler.models import Meta
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.1"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        assert "arc_g2_finance_global" in plan.required_groups

    def test_agent_groups_included(self):
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        assert "arc_g4_tech_mz" in plan.required_groups

    def test_directory_classifications_sorted_by_path(self):
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        paths = [dc.path for dc in plan.directory_classifications]
        assert paths == sorted(paths)

    def test_directory_classification_mode(self):
        from rbac_compiler.models import Meta
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=AgentRegistry(meta=Meta(version="0.1"), agents=[]),
            source_paths={},
            source_hashes={},
        )
        for dc in plan.directory_classifications:
            assert dc.mode == "02770"
            assert dc.apply_default_acl is True

    def test_required_groups_sorted(self):
        plan = compile_plan(
            vocab=self.vocab,
            org_files=self.org_files,
            agent_registry=self.agent_registry,
            source_paths={},
            source_hashes={},
        )
        assert plan.required_groups == sorted(plan.required_groups)
