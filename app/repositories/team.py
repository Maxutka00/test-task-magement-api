from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamMember


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        name: str,
        description: str | None,
        join_code: str,
        owner_id: UUID,
    ) -> Team:
        team = Team(
            name=name,
            description=description,
            join_code=join_code,
            owner_id=owner_id,
        )
        self.session.add(team)
        await self.session.flush()
        return team

    async def get_by_id(self, team_id: UUID) -> Team | None:
        result = await self.session.execute(select(Team).where(Team.id == team_id))
        return result.scalar_one_or_none()

    async def get_by_join_code(self, join_code: str) -> Team | None:
        result = await self.session.execute(select(Team).where(Team.join_code == join_code))
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[Team]:
        stmt = (
            select(Team)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == user_id)
            .order_by(Team.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_member(
        self,
        team_id: UUID,
        user_id: UUID,
        for_update: bool = False,
        for_share: bool = False,
    ) -> TeamMember | None:
        stmt = select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        elif for_share:
            stmt = stmt.with_for_update(read=True).execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_members_locked(
        self,
        team_id: UUID,
        user_locks: dict[UUID, str],
    ) -> dict[UUID, TeamMember | None]:
        locked: dict[UUID, TeamMember | None] = {}
        for uid in sorted(user_locks):
            mode = user_locks[uid]
            locked[uid] = await self.get_member(
                team_id,
                uid,
                for_update=(mode == "update"),
                for_share=(mode == "share"),
            )
        return locked

    async def add_member(
        self,
        team_id: UUID,
        user_id: UUID,
        role_id: UUID,
    ) -> TeamMember:
        member = TeamMember(team_id=team_id, user_id=user_id, role_id=role_id)
        self.session.add(member)
        await self.session.flush()
        await self.session.refresh(member)
        return member

    async def list_members(self, team_id: UUID) -> list[TeamMember]:
        stmt = (
            select(TeamMember)
            .where(TeamMember.team_id == team_id)
            .order_by(TeamMember.joined_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_members_with_role(self, role_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(TeamMember.user_id)).where(TeamMember.role_id == role_id)
        )
        return result.scalar_one()

    async def remove_member(self, member: TeamMember) -> None:
        await self.session.delete(member)
        await self.session.flush()

    async def delete(self, team: Team) -> None:
        await self.session.execute(
            delete(TeamMember).where(TeamMember.team_id == team.id)
        )
        await self.session.delete(team)
        await self.session.flush()
