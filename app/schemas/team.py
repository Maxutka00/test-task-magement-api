from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.team import TeamMember
from app.schemas.common import ensure_no_nul_bytes
from app.schemas.role import RoleResponse
from app.schemas.user import UserPublic


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Team name cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return ensure_no_nul_bytes(value)


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Team name cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return ensure_no_nul_bytes(value)

    @model_validator(mode="after")
    def reject_null_name(self) -> "TeamUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Team name cannot be null")
        return self


class JoinTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    join_code: str
    owner_id: UUID
    created_at: datetime


class TeamMemberResponse(BaseModel):
    team_id: UUID
    user: UserPublic
    role: RoleResponse
    joined_at: datetime

    @classmethod
    def from_model(cls, member: TeamMember) -> "TeamMemberResponse":
        return cls(
            team_id=member.team_id,
            user=UserPublic.model_validate(member.user),
            role=RoleResponse.from_model(member.role),
            joined_at=member.joined_at,
        )
