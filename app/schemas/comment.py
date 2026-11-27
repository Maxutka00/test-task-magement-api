from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ensure_no_nul_bytes
from app.schemas.user import UserPublic


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    parent_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Comment content cannot be blank")
        return cleaned


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    author_id: UUID
    author: UserPublic
    parent_id: UUID | None
    content: str
    created_at: datetime
    replies: list["CommentResponse"] = Field(default_factory=list)


CommentResponse.model_rebuild()
