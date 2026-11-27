from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_team_member
from app.core.database import get_db
from app.models.team import TeamMember
from app.models.user import User
from app.schemas.role import AssignRoleRequest
from app.schemas.team import (
    JoinTeamRequest,
    TeamCreate,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdate,
)
from app.services.invitation import InvitationService
from app.services.team import TeamService

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    team = await TeamService(db).create_team(current_user, payload)
    return TeamResponse.model_validate(team)


@router.get("", response_model=list[TeamResponse])
async def list_my_teams(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TeamResponse]:
    teams = await TeamService(db).list_my_teams(current_user.id)
    return [TeamResponse.model_validate(team) for team in teams]


@router.post("/join", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def join_team(
    payload: JoinTeamRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamMemberResponse:
    member = await InvitationService(db).join_team_by_code(current_user, payload.code)
    return TeamMemberResponse.from_model(member)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    _ = actor
    team = await TeamService(db).get_team(team_id)
    return TeamResponse.model_validate(team)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamResponse:
    team = await TeamService(db).update_team(team_id, actor, payload)
    return TeamResponse.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await TeamService(db).delete_team(team_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_members(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TeamMemberResponse]:
    _ = actor
    members = await TeamService(db).list_members(team_id)
    return [TeamMemberResponse.from_model(member) for member in members]


@router.patch("/{team_id}/members/{user_id}/role", response_model=TeamMemberResponse)
async def assign_member_role(
    team_id: UUID,
    user_id: UUID,
    payload: AssignRoleRequest,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamMemberResponse:
    member = await TeamService(db).assign_member_role(
        team_id=team_id,
        actor=actor,
        target_user_id=user_id,
        role_id=payload.role_id,
    )
    return TeamMemberResponse.from_model(member)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await TeamService(db).remove_member(team_id=team_id, actor=actor, target_user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
