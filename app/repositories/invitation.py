from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import InvitationStatus, TeamInvitation


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        team_id: UUID,
        invited_user_id: UUID,
        invited_by_id: UUID,
        expires_at: datetime,
    ) -> TeamInvitation:
        invitation = TeamInvitation(
            team_id=team_id,
            invited_user_id=invited_user_id,
            invited_by_id=invited_by_id,
            status=InvitationStatus.PENDING,
            expires_at=expires_at,
        )
        self.session.add(invitation)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def get_by_id(
        self,
        team_id: UUID,
        invitation_id: UUID,
        for_update: bool = False,
    ) -> TeamInvitation | None:
        stmt = select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.id == invitation_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_for_user_and_team(
        self,
        team_id: UUID,
        user_id: UUID,
        for_update: bool = False,
    ) -> TeamInvitation | None:
        stmt = select(TeamInvitation).where(
            TeamInvitation.team_id == team_id,
            TeamInvitation.invited_user_id == user_id,
            TeamInvitation.status == InvitationStatus.PENDING,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def expire_stale_for_team(self, team_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(TeamInvitation)
            .where(
                TeamInvitation.team_id == team_id,
                TeamInvitation.status == InvitationStatus.PENDING,
                TeamInvitation.expires_at <= now,
            )
            .values(status=InvitationStatus.EXPIRED)
        )
        await self.session.flush()

    async def list_for_team(self, team_id: UUID) -> list[TeamInvitation]:
        stmt = (
            select(TeamInvitation)
            .where(TeamInvitation.team_id == team_id)
            .order_by(TeamInvitation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_user(
        self,
        user_id: UUID,
        now: datetime,
    ) -> list[TeamInvitation]:
        stmt = (
            select(TeamInvitation)
            .where(
                TeamInvitation.invited_user_id == user_id,
                TeamInvitation.status == InvitationStatus.PENDING,
                TeamInvitation.expires_at > now,
            )
            .order_by(TeamInvitation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
