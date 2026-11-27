from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_team_member
from app.core.database import get_db
from app.models.team import TeamMember
from app.schemas.comment import CommentCreate, CommentResponse
from app.schemas.common import PaginatedResponse
from app.services.comment import CommentService

router = APIRouter(prefix="/teams/{team_id}/tasks/{task_id}/comments", tags=["comments"])


@router.post("", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    team_id: UUID,
    task_id: UUID,
    payload: CommentCreate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommentResponse:
    return await CommentService(db).create_comment(team_id, actor, task_id, payload)


@router.get("", response_model=PaginatedResponse[CommentResponse])
async def list_comments(
    team_id: UUID,
    task_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1, le=1_000_000),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[CommentResponse]:
    return await CommentService(db).list_comments(team_id, actor, task_id, page, size)
