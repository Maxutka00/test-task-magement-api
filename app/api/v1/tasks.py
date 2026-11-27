from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_team_member
from app.core.database import get_db
from app.core.exceptions import BadRequestError
from app.models.task import TaskPriority, TaskStatus
from app.models.team import TeamMember
from app.schemas.common import PaginatedResponse
from app.schemas.task import (
    SortOrder,
    TaskCreate,
    TaskResponse,
    TaskSortBy,
    TaskStatsResponse,
    TaskStatusUpdate,
    TaskUpdate,
    normalize_utc_datetime,
)
from app.services.task import TaskService

router = APIRouter(prefix="/teams/{team_id}/tasks", tags=["tasks"])


def _parse_utc_query(dt: datetime | None) -> datetime | None:
    try:
        return normalize_utc_datetime(dt)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    team_id: UUID,
    payload: TaskCreate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    task = await TaskService(db).create_task(team_id, actor, payload)
    return TaskResponse.model_validate(task)


@router.get("", response_model=PaginatedResponse[TaskResponse])
async def list_tasks(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=200),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = Query(default=None),
    assignee_id: UUID | None = Query(default=None),
    deadline_from: datetime | None = Query(default=None),
    deadline_to: datetime | None = Query(default=None),
    sort_by: TaskSortBy | None = Query(default=None),
    sort_order: SortOrder | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1_000_000),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[TaskResponse]:
    if search is not None and "\x00" in search:
        raise BadRequestError("Search query must not contain NUL bytes")
    return await TaskService(db).list_tasks(
        team_id=team_id,
        actor=actor,
        search=search,
        status=status_filter,
        priority=priority,
        assignee_id=assignee_id,
        deadline_from=_parse_utc_query(deadline_from),
        deadline_to=_parse_utc_query(deadline_to),
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        size=size,
    )


@router.get("/overdue", response_model=PaginatedResponse[TaskResponse])
async def list_overdue_tasks(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1, le=1_000_000),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[TaskResponse]:
    return await TaskService(db).list_overdue_tasks(
        team_id=team_id,
        actor=actor,
        page=page,
        size=size,
    )


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskStatsResponse:
    return await TaskService(db).get_stats(team_id=team_id, actor=actor)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    team_id: UUID,
    task_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    task = await TaskService(db).get_task(team_id, actor, task_id)
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    team_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    task = await TaskService(db).update_task(team_id, actor, task_id, payload)
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def change_task_status(
    team_id: UUID,
    task_id: UUID,
    payload: TaskStatusUpdate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskResponse:
    task = await TaskService(db).change_status(team_id, actor, task_id, payload.status)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    team_id: UUID,
    task_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await TaskService(db).delete_task(team_id, actor, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
