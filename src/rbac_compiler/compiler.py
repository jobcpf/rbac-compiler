"""
Core compilation logic — pure functions, no I/O, no side effects.

Takes validated model instances, computes the full set of Linux groups,
agent memberships, and directory classifications needed on the target system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import AccessGrant, Agent, AgentRegistry, OrgDataFile, Vocabulary

__version__ = "0.1.0"


# ── Group name construction ───────────────────────────────────────────────────

def group_name(org: str, grade: int, vertical: str, scope: str) -> str:
    return f"{org}_g{grade}_{vertical}_{scope}"


def groups_for_grant(grant: AccessGrant, org_file: OrgDataFile, vocab: Vocabulary) -> set[str]:
    """Expand a single access grant into the full set of group names it implies.

    Rules:
      - Clearance envelope: agent gets access to grant.grade AND all higher grades
        (higher number = lower privilege, so the envelope goes upward).
      - vertical='any'   -> all verticals in the vocabulary
      - scope='global'   -> all scopes in the vocabulary
    """
    all_org_grades = sorted(org_file.org_def.grades.keys())
    grades = [g for g in all_org_grades if g >= grant.grade]

    verticals = vocab.verticals if grant.vertical == "any" else [grant.vertical]
    scopes = vocab.scopes if grant.scope == "global" else [grant.scope]

    return {
        group_name(grant.org, g, v, s)
        for g in grades
        for v in verticals
        for s in scopes
    }


def groups_for_agent(
    agent: Agent,
    org_files: dict[str, OrgDataFile],
    vocab: Vocabulary,
) -> list[str]:
    """Return the sorted, deduplicated list of groups for an agent."""
    groups: set[str] = set()
    for grant in agent.access:
        if grant.org in org_files:
            groups |= groups_for_grant(grant, org_files[grant.org], vocab)
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
    vocab: Vocabulary,
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
        for entry in org_file.data:
            grp = group_name(org_file.org, entry.grade, entry.vertical, entry.scope)
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
        ag_groups = groups_for_agent(agent, org_map, vocab)
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
