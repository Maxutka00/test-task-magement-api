from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_team_member
from app.core.database import get_db
from app.models.team import TeamMember
from app.schemas.role import RoleCreate, RoleResponse, RoleUpdate
from app.services.role import RoleService

router = APIRouter(prefix="/teams/{team_id}/roles", tags=["roles"])


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RoleResponse]:
    _ = actor
    roles = await RoleService(db).list_roles(team_id)
    return [RoleResponse.from_model(role) for role in roles]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    team_id: UUID,
    payload: RoleCreate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RoleResponse:
    role = await RoleService(db).create_role(team_id, actor, payload)
    return RoleResponse.from_model(role)


@router.patch("/{role_id}", response_model=RoleResponse)
async def update_role(
    team_id: UUID,
    role_id: UUID,
    payload: RoleUpdate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RoleResponse:
    role = await RoleService(db).update_role(team_id, actor, role_id, payload)
    return RoleResponse.from_model(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    team_id: UUID,
    role_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await RoleService(db).delete_role(team_id, actor, role_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
