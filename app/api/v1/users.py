from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import BadRequestError
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.common import PaginatedResponse, build_paginated_response
from app.schemas.user import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=PaginatedResponse[UserPublic])
async def list_users(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=1_000_000),
    size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[UserPublic]:
    _ = current_user
    if search is not None and "\x00" in search:
        raise BadRequestError("Search query must not contain NUL bytes")
    users, total = await UserRepository(db).list_users(search=search, page=page, size=size)
    items = [UserPublic.model_validate(user) for user in users]
    return build_paginated_response(items=items, total=total, page=page, size=size)
