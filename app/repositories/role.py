from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Permission
from app.models.role import Role, RolePermission


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        team_id: UUID,
        name: str,
        level: int,
        permissions: Iterable[Permission],
        is_system: bool = False,
    ) -> Role:
        role = Role(
            team_id=team_id,
            name=name,
            level=level,
            is_system=is_system,
        )
        self.session.add(role)
        await self.session.flush()

        for perm in set(permissions):
            self.session.add(RolePermission(role_id=role.id, permission=perm.value))
        await self.session.flush()
        await self.session.refresh(role)
        return role

    async def get_by_id(
        self,
        team_id: UUID,
        role_id: UUID,
        for_update: bool = False,
        for_share: bool = False,
    ) -> Role | None:
        stmt = select(Role).where(Role.team_id == team_id, Role.id == role_id)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        elif for_share:
            stmt = stmt.with_for_update(read=True).execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_roles_locked(
        self,
        team_id: UUID,
        role_locks: dict[UUID, str],
    ) -> dict[UUID, Role | None]:
        locked: dict[UUID, Role | None] = {}
        for rid in sorted(role_locks):
            mode = role_locks[rid]
            locked[rid] = await self.get_by_id(
                team_id,
                rid,
                for_update=(mode == "update"),
                for_share=(mode == "share"),
            )
        return locked

    async def get_by_name(self, team_id: UUID, name: str) -> Role | None:
        result = await self.session.execute(
            select(Role).where(Role.team_id == team_id, Role.name == name)
        )
        return result.scalar_one_or_none()

    async def list_for_team(self, team_id: UUID) -> list[Role]:
        stmt = (
            select(Role)
            .where(Role.team_id == team_id)
            .order_by(Role.level.desc(), Role.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace_permissions(
        self,
        role: Role,
        permissions: Iterable[Permission],
    ) -> Role:
        await self.session.execute(
            delete(RolePermission).where(RolePermission.role_id == role.id)
        )
        await self.session.flush()
        for perm in set(permissions):
            self.session.add(RolePermission(role_id=role.id, permission=perm.value))
        await self.session.flush()
        await self.session.refresh(role)
        return role

    async def delete(self, role: Role) -> None:
        await self.session.delete(role)
        await self.session.flush()
