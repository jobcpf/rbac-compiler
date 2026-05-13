"""Unit tests for the agent surface path resolver."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from rbac_compiler.models import Agent
from rbac_compiler.resolver import (
    ALL_SURFACES,
    CLASSIFIED_SURFACES,
    DATA_ROOT,
    resolve_surface_path,
    resolve_surface_path_relative,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agent(**kw) -> Agent:
    return Agent.model_validate({
        "name": kw.pop("name", "agent_test"),
        "access": [],
        **kw,
    })


# ── Surface constants ─────────────────────────────────────────────────────────

class TestSurfaceConstants:
    def test_all_surfaces_includes_four(self):
        assert set(ALL_SURFACES) == {"configs", "memory", "sessions", "scratch"}

    def test_classified_surfaces_excludes_configs(self):
        # configs is private (mode 0700), never group-classified
        assert "configs" not in CLASSIFIED_SURFACES
        assert set(CLASSIFIED_SURFACES) == {"memory", "sessions", "scratch"}


# ── resolve_surface_path (absolute) ───────────────────────────────────────────

class TestResolveAbsolute:
    def test_convention_path(self):
        a = _agent(
            name="agent_arc_research_mz",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
        )
        assert resolve_surface_path(a, "memory") == "/mnt/raid/arc/agents/agent_arc_research_mz/memory/"

    def test_top_org_no_special_case(self):
        a = _agent(
            name="agent_oversight",
            share_class={"org": "top", "grade": 0, "vertical": "any", "scope": "global"},
        )
        assert resolve_surface_path(a, "scratch") == "/mnt/raid/top/agents/agent_oversight/scratch/"

    def test_shares_override_wins(self):
        a = _agent(
            name="agent_arc_finance",
            share_class={"org": "arc", "grade": 5, "vertical": "finance", "scope": "global"},
            shares={"memory": "/mnt/raid/elsewhere/mem/"},
        )
        assert resolve_surface_path(a, "memory") == "/mnt/raid/elsewhere/mem/"

    def test_partial_override(self):
        # Only memory is overridden; other surfaces fall back to convention.
        a = _agent(
            name="agent_x",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
            shares={"memory": "/mnt/raid/custom/mem/"},
        )
        assert resolve_surface_path(a, "memory") == "/mnt/raid/custom/mem/"
        assert resolve_surface_path(a, "sessions") == "/mnt/raid/arc/agents/agent_x/sessions/"

    def test_no_share_class_no_path(self):
        a = _agent(name="agent_orphan")
        for surface in ALL_SURFACES:
            assert resolve_surface_path(a, surface) is None

    def test_trailing_slash_added_to_override(self):
        a = _agent(
            name="agent_x",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
            shares={"scratch": "/mnt/raid/foo/bar"},   # no trailing slash
        )
        assert resolve_surface_path(a, "scratch") == "/mnt/raid/foo/bar/"

    def test_unknown_surface_rejected(self):
        a = _agent(name="agent_x")
        with pytest.raises(ValueError, match="unknown surface"):
            resolve_surface_path(a, "garbage")


# ── resolve_surface_path_relative ─────────────────────────────────────────────

class TestResolveRelative:
    def test_convention_path_strips_prefix(self):
        a = _agent(
            name="agent_x",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
        )
        assert resolve_surface_path_relative(a, "memory") == "arc/agents/agent_x/memory/"

    def test_override_under_data_root(self):
        a = _agent(
            name="agent_x",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
            shares={"scratch": "/mnt/raid/shared/pa_scratch/"},
        )
        assert resolve_surface_path_relative(a, "scratch") == "shared/pa_scratch/"

    def test_override_outside_data_root_rejected(self):
        a = _agent(
            name="agent_x",
            share_class={"org": "arc", "grade": 3, "vertical": "tech", "scope": "mz"},
            shares={"memory": "/var/lib/elsewhere/mem/"},
        )
        with pytest.raises(ValueError, match="not under DATA_ROOT"):
            resolve_surface_path_relative(a, "memory")

    def test_no_share_class_returns_none(self):
        a = _agent(name="agent_orphan")
        assert resolve_surface_path_relative(a, "memory") is None


# ── Cross-tool fixture (the shared contract with sync-compile) ────────────────

CROSS_TOOL_FIXTURE = Path(__file__).parent / "fixtures" / "cross_tool" / "agent_paths.yml"


def _load_cross_tool_cases():
    yaml = YAML()
    with CROSS_TOOL_FIXTURE.open(encoding="utf-8") as f:
        data = yaml.load(f)
    return data["cases"]


class TestCrossToolFixture:
    """Every case in the shared cross-tool fixture must produce the listed
    absolute + relative paths. When sync-compile imports this fixture, the
    equivalent test on their side asserts byte-equivalence on the 'absolute'
    column. Together this pins both tools to the same path resolution.
    """

    @pytest.mark.parametrize("case", _load_cross_tool_cases(), ids=lambda c: c["name"])
    def test_case_paths_match_fixture(self, case):
        agent = Agent.model_validate({
            "name": case["agent"]["name"],
            "access": [],
            **{k: v for k, v in case["agent"].items() if k != "name"},
        })
        for surface in ALL_SURFACES:
            expected = case["expected"][surface]
            if expected is None:
                assert resolve_surface_path(agent, surface) is None
                assert resolve_surface_path_relative(agent, surface) is None
            else:
                assert resolve_surface_path(agent, surface) == expected["absolute"], (
                    f"absolute mismatch for {case['name']}/{surface}"
                )
                assert resolve_surface_path_relative(agent, surface) == expected["relative"], (
                    f"relative mismatch for {case['name']}/{surface}"
                )
