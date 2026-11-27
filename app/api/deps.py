from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.models.team import TeamMember
from app.models.user import User
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")

    payload = decode_token(credentials.credentials, expected_type="access")
    try:
        user_id = UUID(payload["sub"])
    except ValueError as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("User not found")
    return user


async def get_team_member(
    team_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamMember:
    member = await TeamRepository(db).get_member(team_id, current_user.id)
    if member is None:
        raise ForbiddenError("You are not a member of this team")
    return member
