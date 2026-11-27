from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_team_member
from app.core.database import get_db
from app.models.team import TeamMember
from app.models.user import User
from app.schemas.invitation import InvitationCreate, InvitationResponse
from app.services.invitation import InvitationService

router = APIRouter(tags=["invitations"])


@router.get("/invitations/me", response_model=list[InvitationResponse])
async def list_my_invitations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InvitationResponse]:
    invitations = await InvitationService(db).list_my_invitations(current_user.id)
    return [InvitationResponse.from_model(inv) for inv in invitations]


@router.post(
    "/teams/{team_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    team_id: UUID,
    payload: InvitationCreate,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationResponse:
    invitation = await InvitationService(db).create_invitation(team_id, actor, payload)
    return InvitationResponse.from_model(invitation)


@router.get("/teams/{team_id}/invitations", response_model=list[InvitationResponse])
async def list_team_invitations(
    team_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InvitationResponse]:
    invitations = await InvitationService(db).list_team_invitations(team_id, actor)
    return [InvitationResponse.from_model(inv) for inv in invitations]


@router.delete(
    "/teams/{team_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    team_id: UUID,
    invitation_id: UUID,
    actor: Annotated[TeamMember, Depends(get_team_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await InvitationService(db).revoke_invitation(team_id, actor, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
