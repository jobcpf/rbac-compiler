"""
Pydantic models for the RBAC registry files.

File roles:
  classification_constants.yml  ->  Constants    (grade_range, reserved_tokens, compiler config)
  orgs/<org>.yml                ->  OrgDataFile  (org definition + data entries)
  agent_registry.yml            ->  AgentRegistry
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

LINUX_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
ORG_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


# ── Shared ────────────────────────────────────────────────────────────────────

class Meta(BaseModel):
    version: str
    stage: str | None = None
    last_modified: str | None = None
    last_modified_by: str | None = None
    description: str | None = None


# ── classification_constants.yml ──────────────────────────────────────────────

class GradeRange(BaseModel):
    min: int = 0
    max: int = 20


class ReservedTokens(BaseModel):
    any_vertical: str = "any"
    global_scope: str = "global"


class CompilerConfig(BaseModel):
    registry_dir: str = "~/ansible/registry"
    orgs_dir: str = "orgs"
    agents_dir: str = "agents"
    output_file: str = ".compiled/compiled_plan.yml"
    schema_version: str = "0.3"


class Constants(BaseModel):
    # extra='allow' tolerates fields owned by other platform tools (e.g.
    # agent_user_defaults consumed by apply_rbac_plan.yml, directory_defaults
    # reserved for future use). The compiler does not validate them.
    model_config = ConfigDict(extra="allow")

    meta: Meta
    grade_range: GradeRange = Field(default_factory=GradeRange)
    reserved_tokens: ReservedTokens = Field(default_factory=ReservedTokens)
    compiler: CompilerConfig = Field(default_factory=CompilerConfig)
    admins: list[str] = Field(default_factory=list)

    @field_validator("admins")
    @classmethod
    def admins_are_valid_usernames(cls, v: list[str]) -> list[str]:
        for name in v:
            if not LINUX_USERNAME_RE.match(name):
                raise ValueError(
                    f"admin '{name}' is not a valid Linux username "
                    "(lowercase, alphanumeric + underscores, ≤ 32 chars, must start with a letter)"
                )
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
    """Org metadata and vocabulary declared at the top of each orgs/<org>.yml."""

    key: str
    name: str
    description: str | None = None
    website: str | None = None
    verticals: list[str]
    scopes: list[str]
    grades: dict[int, str]

    @field_validator("key")
    @classmethod
    def key_valid(cls, v: str) -> str:
        if not ORG_KEY_RE.match(v):
            raise ValueError(
                f"'{v}' is not a valid org key "
                "(lowercase alphanumeric + underscores, ≤ 32 chars, must start with a letter)"
            )
        return v

    @field_validator("verticals", "scopes")
    @classmethod
    def lists_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("verticals")
    @classmethod
    def verticals_has_any(cls, v: list[str]) -> list[str]:
        if "any" not in v:
            raise ValueError("verticals must contain the wildcard 'any'")
        return v

    @field_validator("scopes")
    @classmethod
    def scopes_has_global(cls, v: list[str]) -> list[str]:
        if "global" not in v:
            raise ValueError("scopes must contain the wildcard 'global'")
        return v

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
    """Represents one orgs/<org>.yml file."""

    meta: Meta
    org_definition: OrgDefinition
    data: list[DataEntry] = Field(default_factory=list)

    @property
    def org(self) -> str:
        return self.org_definition.key


# ── agent_registry.yml ────────────────────────────────────────────────────────

class AccessGrant(BaseModel):
    org: str
    grade: int
    vertical: str   # specific vertical name or the reserved 'any' token
    scope: str      # specific scope name or the reserved 'global' token


class Agent(BaseModel):
    # extra='allow' tolerates fields owned by other platform tools (e.g.
    # 'cert:' for dprox certificate issuance, 'local_user:' for samba/shell
    # provisioning by apply_rbac_plan.yml). The compiler does not validate
    # them. To add validation, define the field here.
    model_config = ConfigDict(extra="allow")

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
