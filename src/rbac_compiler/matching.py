"""
Pure match functions used by the compiler to intersect agent grants with
data-defined groups.

No state, no I/O. The three functions below are the entire authority for
"does this agent gain access via this group?" — if you need to change RBAC
semantics, change them here and nowhere else.
"""

from __future__ import annotations


def grade_match(agent_grade: int, dir_grade: int) -> bool:
    """Hierarchical: agent is at least as privileged as the directory.

    Grades are integers where lower = more privileged (military convention).
    """
    return agent_grade <= dir_grade


def vertical_match(agent_v: str, dir_v: str) -> bool:
    """Symmetric wildcard: 'any' on either side matches everything."""
    return agent_v == "any" or dir_v == "any" or agent_v == dir_v


def scope_match(agent_s: str, dir_s: str) -> bool:
    """Symmetric wildcard: 'global' on either side matches everything.

    Note: the scope wildcard is 'global' (not 'any'). A scope of 'any' is
    not a wildcard — it would be an invalid scope name.
    """
    return agent_s == "global" or dir_s == "global" or agent_s == dir_s
