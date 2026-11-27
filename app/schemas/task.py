from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.task import TaskPriority, TaskStatus
from app.schemas.common import ensure_no_nul_bytes
from app.schemas.user import UserPublic


class TaskSortBy(StrEnum):
    CREATED_AT = "created_at"
    DEADLINE = "deadline"
    PRIORITY = "priority"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


def normalize_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    try:
        return value.astimezone(UTC)
    except OverflowError as exc:
        raise ValueError("Datetime value is out of supported UTC range") from exc


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: UUID | None = None
    deadline: datetime | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Task title cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return ensure_no_nul_bytes(value)

    @field_validator("deadline")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return normalize_utc_datetime(value)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    priority: TaskPriority | None = None
    assignee_id: UUID | None = None
    deadline: datetime | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        ensure_no_nul_bytes(value)
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Task title cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return ensure_no_nul_bytes(value)

    @field_validator("deadline")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return normalize_utc_datetime(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "TaskUpdate":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("Task title cannot be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Task priority cannot be null")
        return self


class TaskStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    author_id: UUID
    assignee_id: UUID | None
    author: UserPublic
    assignee: UserPublic | None
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskStatsResponse(BaseModel):
    total: int
    by_status: dict[TaskStatus, int]
    by_priority: dict[TaskPriority, int]
    overdue: int
    active: int
