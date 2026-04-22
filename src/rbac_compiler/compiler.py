"""
Core compilation logic — pure functions, no I/O, no side effects.

Takes validated model instances, computes the full set of Linux groups,
agent memberships, and directory classifications needed on the target system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import AccessGrant, Agent, AgentRegistry, Constants, OrgDataFile

__version__ = "0.2.0"


# ── Group name construction ───────────────────────────────────────────────────

def group_name(org: str, grade: int, vertical: str, scope: str) -> str:
    return f"{org}_g{grade}_{vertical}_{scope}"


def groups_for_grant(
    grant: AccessGrant,
    org_file: OrgDataFile,
    constants: Constants,
) -> set[str]:
    """Expand a single access grant into the full set of group names it implies.

    Rules:
      - Clearance envelope: grant.grade and all higher-numbered (less privileged) grades.
      - vertical='any' -> all of this org's verticals, plus the literal 'any' wildcard group.
      - vertical=specific -> that vertical, plus the literal 'any' wildcard group.
      - scope='global' -> all of this org's scopes (which already includes 'global').
      - scope=specific -> that scope, plus the literal 'global' wildcard group.

    The wildcard groups (e.g. arc_gN_any_global) always appear so that data entries
    classified as vertical=any or scope=global match agent group memberships correctly.
    """
    org_def = org_file.org_definition
    any_token = constants.reserved_tokens.any_vertical
    global_token = constants.reserved_tokens.global_scope

    grades_in_envelope = [g for g in sorted(org_def.grades.keys()) if g >= grant.grade]

    if grant.vertical == any_token:
        verticals = list(org_def.verticals) + [any_token]
    else:
        verticals = [grant.vertical, any_token]

    if grant.scope == global_token:
        scopes = list(org_def.scopes)   # org_def.scopes already contains 'global'
    else:
        scopes = [grant.scope, global_token]

    return {
        group_name(grant.org, g, v, s)
        for g in grades_in_envelope
        for v in verticals
        for s in scopes
    }


def groups_for_agent(
    agent: Agent,
    org_files: dict[str, OrgDataFile],
    constants: Constants,
) -> list[str]:
    """Return the sorted, deduplicated list of groups for an agent."""
    groups: set[str] = set()
    for grant in agent.access:
        if grant.org in org_files:
            groups |= groups_for_grant(grant, org_files[grant.org], constants)
    return sorted(groups)


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
class CompiledPlan:
    compiled_at: str
    compiler_version: str
    source_files: dict[str, object]
    source_hashes: dict[str, object]
    required_groups: list[str]
    agent_users: list[AgentUser]
    directory_classifications: list[DirectoryClassification]


# ── Main compilation entry point ──────────────────────────────────────────────

def compile_plan(
    constants: Constants,
    org_files: list[tuple[OrgDataFile, Path]],
    agent_registry: AgentRegistry,
    source_paths: dict[str, object],
    source_hashes: dict[str, object],
) -> CompiledPlan:
    """Compile registry inputs into a concrete plan.

    Always includes 'fileserver_admins' in required_groups.
    Output is deterministic: same input -> same output byte-for-byte.
    """
    org_map: dict[str, OrgDataFile] = {of.org: of for of, _ in org_files}
    all_groups: set[str] = {"fileserver_admins"}

    # ── Directory classifications ─────────────────────────────────────────────
    dir_classifications: list[DirectoryClassification] = []
    for org_file, path in org_files:
        org_key = org_file.org
        for entry in org_file.data:
            grp = group_name(org_key, entry.grade, entry.vertical, entry.scope)
            all_groups.add(grp)
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

    # ── Agent users ───────────────────────────────────────────────────────────
    agent_users: list[AgentUser] = []
    for agent in agent_registry.agents:
        ag_groups = groups_for_agent(agent, org_map, constants)
        all_groups.update(ag_groups)
        agent_users.append(AgentUser(
            name=agent.name,
            description=agent.description,
            groups=ag_groups,
        ))

    return CompiledPlan(
        compiled_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        compiler_version=__version__,
        source_files=source_paths,
        source_hashes=source_hashes,
        required_groups=sorted(all_groups),
        agent_users=agent_users,
        directory_classifications=dir_classifications,
    )
