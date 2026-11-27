from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from app.models.invitation import InvitationStatus, TeamInvitation
from app.schemas.user import UserPublic


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    user_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return None
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_single_identifier(self) -> "InvitationCreate":
        if (self.email is None) == (self.user_id is None):
            raise ValueError("Provide exactly one of email or user_id")
        return self


class InvitationResponse(BaseModel):
    id: UUID
    team_id: UUID
    team_name: str
    invited_user: UserPublic
    invited_by: UserPublic
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime

    @classmethod
    def from_model(cls, invitation: TeamInvitation) -> "InvitationResponse":
        return cls(
            id=invitation.id,
            team_id=invitation.team_id,
            team_name=invitation.team.name,
            invited_user=UserPublic.model_validate(invitation.invited_user),
            invited_by=UserPublic.model_validate(invitation.invited_by),
            status=invitation.status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
