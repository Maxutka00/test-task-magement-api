from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.permissions import Permission
from app.models.role import Role
from app.schemas.common import ensure_no_nul_bytes


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    level: int = Field(ge=0, le=99)
    permissions: list[Permission]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Role name cannot be blank")
        return cleaned


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    level: int | None = Field(default=None, ge=0, le=99)
    permissions: list[Permission] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Role name cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "RoleUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Role name cannot be null")
        if "level" in self.model_fields_set and self.level is None:
            raise ValueError("Role level cannot be null")
        if "permissions" in self.model_fields_set and self.permissions is None:
            raise ValueError("Role permissions cannot be null")
        return self


class AssignRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: UUID


class RoleResponse(BaseModel):
    id: UUID
    team_id: UUID
    name: str
    level: int
    is_system: bool
    permissions: list[Permission]
    created_at: datetime

    @classmethod
    def from_model(cls, role: Role) -> "RoleResponse":
        return cls(
            id=role.id,
            team_id=role.team_id,
            name=role.name,
            level=role.level,
            is_system=role.is_system,
            permissions=sorted(role.permission_set, key=lambda p: p.value),
            created_at=role.created_at,
        )
