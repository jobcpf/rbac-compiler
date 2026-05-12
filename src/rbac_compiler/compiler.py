"""
Core compilation logic — pure functions, no I/O, no side effects.

v0.3 model: `required_groups` is *data-driven*. Only groups referenced by a
directory classification exist. Agents are matched lazily against that set.
Admin users (from `constants.admins`) are added to every group in the set.

See RBAC_Compiler_v0_3_Brief.md for the full specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .matching import grade_match, scope_match, vertical_match
from .models import AccessGrant, Agent, AgentRegistry, Constants, OrgDataFile

__version__ = "0.3.1"


# ── Group name construction ───────────────────────────────────────────────────

def group_name(org: str, grade: int, vertical: str, scope: str) -> str:
    return f"{org}_g{grade}_{vertical}_{scope}"


# ── Used group (a group that at least one directory classifies to) ────────────

@dataclass(frozen=True)
class UsedGroup:
    name: str
    org: str
    grade: int
    vertical: str
    scope: str


def collect_used_groups(
    org_files: list[tuple[OrgDataFile, Path]],
) -> list[UsedGroup]:
    """Walk every data entry across every org and collect the unique set of
    (org, grade, vertical, scope) tuples. Two directories may share a group;
    it still counts as one group on the system.
    """
    seen: dict[str, UsedGroup] = {}
    for org_file, _ in org_files:
        for entry in org_file.data:
            name = group_name(org_file.org, entry.grade, entry.vertical, entry.scope)
            if name not in seen:
                seen[name] = UsedGroup(
                    name=name,
                    org=org_file.org,
                    grade=entry.grade,
                    vertical=entry.vertical,
                    scope=entry.scope,
                )
    return sorted(seen.values(), key=lambda g: g.name)


# ── Agent → group matching ────────────────────────────────────────────────────

def grant_matches_group(grant: AccessGrant, group: UsedGroup) -> bool:
    """All three dimensions must agree for an agent grant to gain access."""
    return (
        grant.org == group.org
        and grade_match(grant.grade, group.grade)
        and vertical_match(grant.vertical, group.vertical)
        and scope_match(grant.scope, group.scope)
    )


def groups_for_agent(
    agent: Agent,
    used_groups: list[UsedGroup],
) -> list[str]:
    """Return the sorted set of group names the agent matches at least once."""
    matched: set[str] = set()
    for grant in agent.access:
        for group in used_groups:
            if grant_matches_group(grant, group):
                matched.add(group.name)
    return sorted(matched)


# ── Output data structures ────────────────────────────────────────────────────

@dataclass
class DirectoryClassification:
    path: str
    group: str
    mode: str
    apply_default_acl: bool
    description: str | None
    source_file: str


@dataclass
class AgentUser:
    name: str
    description: str | None
    groups: list[str]


@dataclass
class AdminUser:
    """A pre-existing Linux user (human or system account) that should be
    added to every required group. Ansible ensures the account exists and
    manages its group memberships; the compiler only specifies intent.
    """

    name: str
    groups: list[str]


@dataclass
class CompiledPlan:
    compiled_at: str
    compiler_version: str
    source_files: dict[str, object]
    source_hashes: dict[str, object]
    required_groups: list[str]
    agent_users: list[AgentUser]
    admin_users: list[AdminUser]
    directory_classifications: list[DirectoryClassification]


# ── Main compilation entry point ──────────────────────────────────────────────

def compile_plan(
    constants: Constants,
    org_files: list[tuple[OrgDataFile, Path]],
    agent_registry: AgentRegistry,
    source_paths: dict[str, object],
    source_hashes: dict[str, object],
) -> tuple[CompiledPlan, list[str]]:
    """Compile registry inputs into a concrete plan.

    Returns (plan, warnings). Warnings are compile-time observations (empty
    data, unmatched agent) that callers typically merge into the pipeline's
    ValidationResult so the GUI/CLI see them alongside validation warnings.

    Output is deterministic: same input -> same output byte-for-byte.
    """
    warnings: list[str] = []

    # ── Phase 3: collect used_groups from data ────────────────────────────────
    used_groups = collect_used_groups(org_files)
    required_group_names = [g.name for g in used_groups]

    if not used_groups:
        warnings.append(
            "Registry has no directory classifications — "
            "required_groups will be empty and no agent will be a member of any group"
        )

    # ── Phase 4: match agents against used_groups ─────────────────────────────
    agent_users: list[AgentUser] = []
    for agent in agent_registry.agents:
        matched = groups_for_agent(agent, used_groups)
        if agent.access and not matched:
            warnings.append(
                f"Agent '{agent.name}' matches no directory groups — "
                "registry may be incomplete or grants miscalibrated. "
                "Agent user will be created with no group memberships."
            )
        agent_users.append(AgentUser(
            name=agent.name,
            description=agent.description,
            groups=matched,
        ))

    # ── Admin users: membership of every required group ──────────────────────
    admin_users: list[AdminUser] = [
        AdminUser(name=name, groups=list(required_group_names))
        for name in constants.admins
    ]

    # ── Phase 5: directory classifications ────────────────────────────────────
    dir_classifications: list[DirectoryClassification] = []
    for org_file, path in org_files:
        org_key = org_file.org
        for entry in org_file.data:
            grp = group_name(org_key, entry.grade, entry.vertical, entry.scope)
            dir_classifications.append(DirectoryClassification(
                path=entry.path,
                group=grp,
                mode="02770",
                apply_default_acl=True,
                description=entry.description,
                source_file=path.name,
            ))
    # Sort by path so parents appear before children (Ansible applies top-down)
    dir_classifications.sort(key=lambda d: d.path)

    plan = CompiledPlan(
        compiled_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        compiler_version=__version__,
        source_files=source_paths,
        source_hashes=source_hashes,
        required_groups=required_group_names,
        agent_users=agent_users,
        admin_users=admin_users,
        directory_classifications=dir_classifications,
    )
    return plan, warnings
