"""
Pydantic models for the RBAC registry files.

Revised design: org definitions (name, grades, etc.) live in the individual org
files (orgs/<org>.yml), NOT in classification_vocabulary.yml. This means adding
a new org requires only dropping in a single file.

File roles:
  classification_vocabulary.yml  ->  Vocabulary   (verticals + scopes only)
  orgs/<org>.yml                 ->  OrgDataFile  (org definition + data entries)
  agent_registry.yml             ->  AgentRegistry
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

LINUX_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ── Shared ────────────────────────────────────────────────────────────────────

class Meta(BaseModel):
    version: str
    stage: str | None = None
    last_modified: str | None = None
    last_modified_by: str | None = None
    description: str | None = None


# ── classification_vocabulary.yml ─────────────────────────────────────────────

class Vocabulary(BaseModel):
    """Platform-wide vocabulary: verticals and scopes only.

    Org definitions (name, grades, website) live in orgs/<org>.yml so that
    adding a new organisation requires only one new file.
    """

    meta: Meta
    verticals: list[str]
    scopes: list[str]

    @field_validator("verticals", "scopes")
    @classmethod
    def lists_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("scopes")
    @classmethod
    def scopes_has_global(cls, v: list[str]) -> list[str]:
        if "global" not in v:
            raise ValueError("scopes must contain 'global'")
        return v


# ── orgs/<org>.yml ────────────────────────────────────────────────────────────

class DataEntry(BaseModel):
    path: str
    grade: int
    vertical: str
    scope: str
    description: str | None = None

    @field_validator("path")
    @classmethod
    def path_valid(cls, v: str) -> str:
        if not v:
            raise ValueError("path must not be empty")
        if ".." in v:
            raise ValueError("path must not contain '..'")
        if v.startswith("/"):
            raise ValueError("path must not start with '/'")
        return v


class OrgDefinition(BaseModel):
    """Org metadata declared at the top of each orgs/<org>.yml file."""

    name: str
    description: str | None = None
    website: str | None = None
    grades: dict[int, str]

    @field_validator("grades", mode="before")
    @classmethod
    def parse_grades(cls, v: Any) -> dict[int, str]:
        if not isinstance(v, dict):
            raise ValueError("grades must be a mapping")
        return {int(k): str(val) for k, val in v.items()}

    @field_validator("grades")
    @classmethod
    def grades_nonempty(cls, v: dict[int, str]) -> dict[int, str]:
        if not v:
            raise ValueError("grades must not be empty")
        return v


class OrgDataFile(BaseModel):
    """Represents one orgs/<org>.yml file.

    The top-level `org` key is the canonical org identifier (must be a simple
    lowercase string). The `org_def` block carries metadata; `data` carries
    the classification entries.
    """

    meta: Meta
    org: str
    org_def: OrgDefinition = Field(alias="definition")
    data: list[DataEntry] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── agent_registry.yml ────────────────────────────────────────────────────────

class AccessGrant(BaseModel):
    org: str
    grade: int
    vertical: str   # specific vertical or 'any'
    scope: str      # specific scope or 'global'


class Agent(BaseModel):
    name: str
    description: str | None = None
    access: list[AccessGrant]

    @field_validator("name")
    @classmethod
    def valid_linux_username(cls, v: str) -> str:
        if not LINUX_USERNAME_RE.match(v):
            raise ValueError(
                f"'{v}' is not a valid Linux username "
                "(lowercase, alphanumeric + underscores, ≤ 32 chars, must start with a letter)"
            )
        return v


class AgentRegistry(BaseModel):
    meta: Meta
    agents: list[Agent] = Field(default_factory=list)
