"""Tests for core compilation logic — v0.3 lazy, data-driven group computation."""

from pathlib import Path

from rbac_compiler.compiler import (
    UsedGroup,
    collect_used_groups,
    compile_plan,
    grant_matches_group,
    group_name,
    groups_for_agent,
)
from rbac_compiler.models import (
    AccessGrant,
    Agent,
    AgentRegistry,
    Constants,
    DataEntry,
    Meta,
    OrgDataFile,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_constants(admins: list[str] | None = None) -> Constants:
    data: dict = {"meta": {"version": "0.3"}}
    if admins is not None:
        data["admins"] = admins
    return Constants.model_validate(data)


def _make_org(
    org_key: str = "arc",
    max_grade: int = 4,
    verticals: list[str] | None = None,
    scopes: list[str] | None = None,
    data: list[dict] | None = None,
) -> OrgDataFile:
    return OrgDataFile.model_validate({
        "meta": {"version": "0.3"},
        "org_definition": {
            "key": org_key,
            "name": org_key.upper(),
            "verticals": verticals or ["any", "tech", "finance"],
            "scopes": scopes or ["global", "uk", "mz", "rw"],
            "grades": {i: "" for i in range(max_grade + 1)},
        },
        "data": data or [],
    })


def _grant(org: str = "arc", grade: int = 0, vertical: str = "tech", scope: str = "mz") -> AccessGrant:
    return AccessGrant(org=org, grade=grade, vertical=vertical, scope=scope)


# ── group_name ────────────────────────────────────────────────────────────────

class TestGroupName:
    def test_format(self):
        assert group_name("arc", 2, "finance", "global") == "arc_g2_finance_global"

    def test_wildcard_tokens(self):
        assert group_name("arc", 5, "any", "global") == "arc_g5_any_global"


# ── collect_used_groups ───────────────────────────────────────────────────────

class TestCollectUsedGroups:
    def test_empty_when_no_data(self):
        org = _make_org("arc", data=[])
        result = collect_used_groups([(org, Path("arc.yml"))])
        assert result == []

    def test_one_group_per_data_entry(self):
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
            {"path": "arc/dirs/b", "grade": 3, "vertical": "finance", "scope": "mz"},
        ])
        result = collect_used_groups([(org, Path("arc.yml"))])
        names = {g.name for g in result}
        assert names == {"arc_g2_tech_uk", "arc_g3_finance_mz"}

    def test_duplicate_classification_dedupes(self):
        """Two directories with the same (grade, vertical, scope) = one group."""
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
            {"path": "arc/dirs/b", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        result = collect_used_groups([(org, Path("arc.yml"))])
        assert len(result) == 1
        assert result[0].name == "arc_g2_tech_uk"

    def test_multi_org(self):
        arc = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        cpf = _make_org("cpf", verticals=["any", "projects"], scopes=["global", "uk"], data=[
            {"path": "cpf/dirs/b", "grade": 1, "vertical": "projects", "scope": "uk"},
        ])
        result = collect_used_groups([(arc, Path("arc.yml")), (cpf, Path("cpf.yml"))])
        names = {g.name for g in result}
        assert names == {"arc_g2_tech_uk", "cpf_g1_projects_uk"}


# ── grant_matches_group ───────────────────────────────────────────────────────

class TestGrantMatchesGroup:
    def _g(self, **kw) -> UsedGroup:
        defaults = {"name": "arc_g3_tech_uk", "org": "arc", "grade": 3, "vertical": "tech", "scope": "uk"}
        defaults.update(kw)
        return UsedGroup(**defaults)

    def test_direct_match(self):
        assert grant_matches_group(_grant(grade=3, vertical="tech", scope="uk"), self._g())

    def test_more_privileged_grade_matches(self):
        assert grant_matches_group(_grant(grade=1, vertical="tech", scope="uk"), self._g())

    def test_less_privileged_grade_does_not_match(self):
        assert not grant_matches_group(_grant(grade=4, vertical="tech", scope="uk"), self._g())

    def test_wrong_org_does_not_match(self):
        assert not grant_matches_group(
            _grant(org="cpf", grade=1, vertical="tech", scope="uk"), self._g()
        )

    def test_agent_any_matches_specific_vertical(self):
        assert grant_matches_group(_grant(grade=1, vertical="any", scope="uk"), self._g())

    def test_dir_any_matches_specific_agent_vertical(self):
        dir_any = self._g(vertical="any", name="arc_g3_any_uk")
        assert grant_matches_group(_grant(grade=1, vertical="tech", scope="uk"), dir_any)

    def test_vertical_mismatch(self):
        assert not grant_matches_group(_grant(grade=1, vertical="finance", scope="uk"), self._g())

    def test_agent_global_matches_specific_scope(self):
        assert grant_matches_group(_grant(grade=1, vertical="tech", scope="global"), self._g())

    def test_dir_global_matches_specific_agent_scope(self):
        dir_global = self._g(scope="global", name="arc_g3_tech_global")
        assert grant_matches_group(_grant(grade=1, vertical="tech", scope="uk"), dir_global)

    def test_scope_mismatch(self):
        assert not grant_matches_group(_grant(grade=1, vertical="tech", scope="mz"), self._g())


# ── groups_for_agent ──────────────────────────────────────────────────────────

class TestGroupsForAgent:
    def test_no_used_groups_no_memberships(self):
        agent = Agent(name="agent_test", access=[_grant()])
        assert groups_for_agent(agent, []) == []

    def test_sorted_output(self):
        used = [
            UsedGroup(name="arc_g3_tech_uk", org="arc", grade=3, vertical="tech", scope="uk"),
            UsedGroup(name="arc_g2_tech_uk", org="arc", grade=2, vertical="tech", scope="uk"),
        ]
        agent = Agent(name="agent_test", access=[_grant(grade=1, vertical="any", scope="global")])
        result = groups_for_agent(agent, used)
        assert result == sorted(result)
        assert result == ["arc_g2_tech_uk", "arc_g3_tech_uk"]

    def test_multiple_grants_union(self):
        used = [
            UsedGroup(name="arc_g2_tech_uk", org="arc", grade=2, vertical="tech", scope="uk"),
            UsedGroup(name="cpf_g3_projects_uk", org="cpf", grade=3, vertical="projects", scope="uk"),
        ]
        agent = Agent(name="agent_multi", access=[
            _grant(org="arc", grade=1, vertical="tech", scope="uk"),
            _grant(org="cpf", grade=1, vertical="projects", scope="uk"),
        ])
        result = groups_for_agent(agent, used)
        assert set(result) == {"arc_g2_tech_uk", "cpf_g3_projects_uk"}


# ── compile_plan (worked example from the v0.3 brief) ─────────────────────────

class TestCompilePlanWorkedExample:
    """Reference scenario from RBAC_Compiler_v0_3_Brief.md §Tests."""

    def setup_method(self):
        self.constants = _make_constants()
        self.org = _make_org(
            "arc",
            max_grade=4,
            verticals=["any", "tech", "commercial", "engineering", "finance", "ops"],
            scopes=["global", "uk", "mz", "rw", "za", "zm"],
            data=[
                {"path": "arc/dirs/t_uk", "grade": 2, "vertical": "tech", "scope": "uk"},
                {"path": "arc/dirs/t_mz", "grade": 2, "vertical": "tech", "scope": "mz"},
                {"path": "arc/dirs/t_rw", "grade": 4, "vertical": "tech", "scope": "rw"},
                {"path": "arc/dirs/any_uk", "grade": 3, "vertical": "any", "scope": "uk"},
                {"path": "arc/dirs/any_global", "grade": 3, "vertical": "any", "scope": "global"},
            ],
        )
        self.agents = AgentRegistry(meta=Meta(version="0.3"), agents=[
            Agent(name="agent_1", access=[_grant(org="arc", grade=1, vertical="any", scope="global")]),
            Agent(name="agent_2", access=[_grant(org="arc", grade=2, vertical="any", scope="mz")]),
            Agent(name="agent_3", access=[_grant(org="arc", grade=3, vertical="tech", scope="global")]),
        ])
        self.org_files = [(self.org, Path("arc.yml"))]

    def test_required_groups_is_exactly_data_defined(self):
        plan, _ = compile_plan(self.constants, self.org_files, self.agents, {}, {})
        assert set(plan.required_groups) == {
            "arc_g2_tech_uk",
            "arc_g2_tech_mz",
            "arc_g4_tech_rw",
            "arc_g3_any_uk",
            "arc_g3_any_global",
        }
        assert len(plan.required_groups) == 5

    def test_agent_1_matches_all_five(self):
        """grade=1 any global → matches every group."""
        plan, _ = compile_plan(self.constants, self.org_files, self.agents, {}, {})
        agent_1 = next(au for au in plan.agent_users if au.name == "agent_1")
        assert set(agent_1.groups) == {
            "arc_g2_tech_uk",
            "arc_g2_tech_mz",
            "arc_g4_tech_rw",
            "arc_g3_any_uk",
            "arc_g3_any_global",
        }

    def test_agent_2_matches_grade_le_2_scope_mz_or_global(self):
        """grade=2 any mz → only groups at grade ≥ 2, scope ∈ {mz, global}."""
        plan, _ = compile_plan(self.constants, self.org_files, self.agents, {}, {})
        agent_2 = next(au for au in plan.agent_users if au.name == "agent_2")
        assert set(agent_2.groups) == {"arc_g2_tech_mz", "arc_g3_any_global"}

    def test_agent_3_matches_grade_le_3_tech_or_any_scope_global(self):
        """grade=3 tech global → grade ≥ 3, vertical ∈ {tech, any}, any scope (via global)."""
        plan, _ = compile_plan(self.constants, self.org_files, self.agents, {}, {})
        agent_3 = next(au for au in plan.agent_users if au.name == "agent_3")
        assert set(agent_3.groups) == {"arc_g3_any_global", "arc_g3_any_uk", "arc_g4_tech_rw"}


# ── compile_plan — admins, warnings, edge cases ───────────────────────────────

class TestAdminUsers:
    def test_admin_user_in_every_required_group(self):
        constants = _make_constants(admins=["beaver"])
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
            {"path": "arc/dirs/b", "grade": 3, "vertical": "finance", "scope": "mz"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert len(plan.admin_users) == 1
        assert plan.admin_users[0].name == "beaver"
        assert set(plan.admin_users[0].groups) == set(plan.required_groups)

    def test_no_admins_block_produces_no_admin_users(self):
        constants = _make_constants()  # admins absent, defaults to []
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert plan.admin_users == []

    def test_admin_with_empty_required_groups_has_empty_list(self):
        """Empty data → admins exist but with no group memberships yet."""
        constants = _make_constants(admins=["beaver"])
        org = _make_org("arc", data=[])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert plan.admin_users[0].groups == []


class TestCompileWarnings:
    def test_empty_data_warns(self):
        constants = _make_constants()
        org = _make_org("arc", data=[])
        _, warnings = compile_plan(constants, [(org, Path("arc.yml"))],
                                   AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert any("no directory classifications" in w for w in warnings)

    def test_unmatched_agent_warns(self):
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        agents = AgentRegistry(meta=Meta(version="0.3"), agents=[
            # grade=3 agent cannot match grade=2 directory (agent too junior)
            Agent(name="agent_niche", access=[_grant(grade=3, vertical="finance", scope="mz")]),
        ])
        _, warnings = compile_plan(constants, [(org, Path("arc.yml"))], agents, {}, {})
        assert any("agent_niche" in w and "matches no" in w for w in warnings)

    def test_matched_agent_does_not_warn(self):
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 3, "vertical": "tech", "scope": "uk"},
        ])
        agents = AgentRegistry(meta=Meta(version="0.3"), agents=[
            Agent(name="agent_ok", access=[_grant(grade=1, vertical="tech", scope="uk")]),
        ])
        _, warnings = compile_plan(constants, [(org, Path("arc.yml"))], agents, {}, {})
        assert not any("agent_ok" in w for w in warnings)

    def test_agent_with_no_grants_does_not_warn_about_matching(self):
        """No access grants → validation already warned; don't double-warn."""
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 3, "vertical": "tech", "scope": "uk"},
        ])
        agents = AgentRegistry(meta=Meta(version="0.3"), agents=[
            Agent(name="agent_empty", access=[]),
        ])
        _, warnings = compile_plan(constants, [(org, Path("arc.yml"))], agents, {}, {})
        assert not any("agent_empty" in w and "matches no" in w for w in warnings)


class TestCompilePlanStructure:
    def test_directory_classifications_sorted_by_path(self):
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/z", "grade": 2, "vertical": "tech", "scope": "uk"},
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        paths = [dc.path for dc in plan.directory_classifications]
        assert paths == sorted(paths)

    def test_directory_classification_mode_and_acl(self):
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        for dc in plan.directory_classifications:
            assert dc.mode == "02770"
            assert dc.apply_default_acl is True

    def test_fileserver_admins_not_injected(self):
        """v0.3 drops the implicit fileserver_admins group."""
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert "fileserver_admins" not in plan.required_groups

    def test_version_bumped(self):
        constants = _make_constants()
        org = _make_org("arc", data=[
            {"path": "arc/dirs/a", "grade": 2, "vertical": "tech", "scope": "uk"},
        ])
        plan, _ = compile_plan(constants, [(org, Path("arc.yml"))],
                               AgentRegistry(meta=Meta(version="0.3"), agents=[]), {}, {})
        assert plan.compiler_version == "0.3.1"
