from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import (
    ADMIN_ROLE_LEVEL,
    ADMIN_ROLE_NAME,
    DEFAULT_ADMIN_PERMISSIONS,
    DEFAULT_MANAGER_PERMISSIONS,
    DEFAULT_USER_PERMISSIONS,
    MANAGER_ROLE_LEVEL,
    MANAGER_ROLE_NAME,
    USER_ROLE_LEVEL,
    USER_ROLE_NAME,
    Permission,
)
from app.core.security import generate_team_join_code
from app.models.role import Role
from app.models.team import Team, TeamMember
from app.models.user import User
from app.repositories.role import RoleRepository
from app.repositories.task import TaskRepository
from app.repositories.team import TeamRepository
from app.schemas.team import TeamCreate, TeamUpdate


def is_admin_role(role: Role) -> bool:
    return (
        role.is_system
        and role.name == ADMIN_ROLE_NAME
        and role.level == ADMIN_ROLE_LEVEL
    )


class TeamService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.team_repo = TeamRepository(session)
        self.role_repo = RoleRepository(session)
        self.task_repo = TaskRepository(session)

    async def _lock_actor_and_role(self, team_id: UUID, user_id: UUID) -> tuple[TeamMember, Role]:
        member = await self.team_repo.get_member(team_id, user_id, for_share=True)
        if member is None:
            raise ForbiddenError("You are not a member of this team")
        role = await self.role_repo.get_by_id(team_id, member.role_id, for_share=True)
        if role is None:
            raise ForbiddenError("Team role not found")
        return member, role

    async def create_team(self, creator: User, data: TeamCreate) -> Team:
        team: Team | None = None
        for _ in range(10):
            code = generate_team_join_code()
            if await self.team_repo.get_by_join_code(code) is not None:
                continue
            try:
                async with self.session.begin_nested():
                    team = await self.team_repo.create(
                        name=data.name,
                        description=data.description,
                        join_code=code,
                        owner_id=creator.id,
                    )
                break
            except IntegrityError:
                continue

        if team is None:
            raise ConflictError("Could not allocate unique team code")

        admin_role = await self.role_repo.create(
            team_id=team.id,
            name=ADMIN_ROLE_NAME,
            level=ADMIN_ROLE_LEVEL,
            permissions=DEFAULT_ADMIN_PERMISSIONS,
            is_system=True,
        )
        await self.role_repo.create(
            team_id=team.id,
            name=MANAGER_ROLE_NAME,
            level=MANAGER_ROLE_LEVEL,
            permissions=DEFAULT_MANAGER_PERMISSIONS,
            is_system=True,
        )
        await self.role_repo.create(
            team_id=team.id,
            name=USER_ROLE_NAME,
            level=USER_ROLE_LEVEL,
            permissions=DEFAULT_USER_PERMISSIONS,
            is_system=True,
        )

        await self.team_repo.add_member(
            team_id=team.id,
            user_id=creator.id,
            role_id=admin_role.id,
        )
        await self.session.commit()
        await self.session.refresh(team)
        return team

    async def list_my_teams(self, user_id: UUID) -> list[Team]:
        return await self.team_repo.list_for_user(user_id)

    async def get_team(self, team_id: UUID) -> Team:
        team = await self.team_repo.get_by_id(team_id)
        if team is None:
            raise NotFoundError("Team not found")
        return team

    async def update_team(
        self,
        team_id: UUID,
        actor: TeamMember,
        data: TeamUpdate,
    ) -> Team:
        _, actor_role = await self._lock_actor_and_role(team_id, actor.user_id)
        if not is_admin_role(actor_role):
            raise ForbiddenError("Only team admin can update team settings")

        team = await self.get_team(team_id)
        if "name" in data.model_fields_set and data.name is not None:
            team.name = data.name
        if "description" in data.model_fields_set:
            team.description = data.description

        await self.session.commit()
        await self.session.refresh(team)
        return team

    async def delete_team(self, team_id: UUID, actor: TeamMember) -> None:
        _, actor_role = await self._lock_actor_and_role(team_id, actor.user_id)
        if not is_admin_role(actor_role):
            raise ForbiddenError("Only team admin can delete the team")

        team = await self.get_team(team_id)
        await self.team_repo.delete(team)
        await self.session.commit()

    async def list_members(self, team_id: UUID) -> list[TeamMember]:
        return await self.team_repo.list_members(team_id)

    async def assign_member_role(
        self,
        team_id: UUID,
        actor: TeamMember,
        target_user_id: UUID,
        role_id: UUID,
    ) -> TeamMember:
        if target_user_id == actor.user_id:
            raise ForbiddenError("Cannot change your own role")

        members = await self.team_repo.get_members_locked(
            team_id,
            {actor.user_id: "share", target_user_id: "update"},
        )
        locked_actor = members[actor.user_id]
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")
        target_member = members[target_user_id]
        if target_member is None:
            raise NotFoundError("Team member not found")

        role_locks: dict[UUID, str] = {
            locked_actor.role_id: "share",
            target_member.role_id: "share",
            role_id: "update",
        }
        roles = await self.role_repo.get_roles_locked(team_id, role_locks)
        actor_role = roles[locked_actor.role_id]
        target_role = roles[target_member.role_id]
        new_role = roles[role_id]

        if actor_role is None or target_role is None:
            raise ForbiddenError("Role state could not be verified")

        actor_permissions = actor_role.permission_set
        if Permission.ROLE_ASSIGN not in actor_permissions:
            raise ForbiddenError("Missing permission to assign roles")

        if new_role is None:
            raise NotFoundError("Role not found")

        if new_role.level >= actor_role.level:
            raise ForbiddenError("Cannot assign a role equal to or higher than your own")

        if not new_role.permission_set.issubset(actor_permissions):
            raise ForbiddenError("Cannot assign a role with permissions you do not possess")

        if target_role.level >= actor_role.level:
            raise ForbiddenError("Cannot modify a member with an equal or higher role")

        target_member.role_id = new_role.id
        try:
            await self.session.flush()
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Could not assign role due to concurrent update") from exc
        await self.session.refresh(target_member)
        return target_member

    async def remove_member(
        self,
        team_id: UUID,
        actor: TeamMember,
        target_user_id: UUID,
    ) -> None:
        now = datetime.now(UTC)
        if actor.user_id == target_user_id:
            locked_self = await self.team_repo.get_member(team_id, target_user_id, for_update=True)
            if locked_self is None:
                raise NotFoundError("Team member not found")
            self_role = await self.role_repo.get_by_id(team_id, locked_self.role_id, for_share=True)
            if self_role is not None and is_admin_role(self_role):
                raise BadRequestError("Team admin cannot leave the team; delete the team instead")
            await self.team_repo.remove_member(locked_self)
            await self.task_repo.unassign_active_for_departing_member(team_id, target_user_id, now)
            await self.session.commit()
            return

        members = await self.team_repo.get_members_locked(
            team_id,
            {actor.user_id: "share", target_user_id: "update"},
        )
        locked_actor = members[actor.user_id]
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")
        target_member = members[target_user_id]
        if target_member is None:
            raise NotFoundError("Team member not found")

        roles = await self.role_repo.get_roles_locked(
            team_id,
            {locked_actor.role_id: "share", target_member.role_id: "share"},
        )
        actor_role = roles[locked_actor.role_id]
        target_role = roles[target_member.role_id]
        if actor_role is None or target_role is None:
            raise ForbiddenError("Role state could not be verified")

        if Permission.TEAM_KICK_MEMBERS not in actor_role.permission_set:
            raise ForbiddenError("Missing permission to remove team members")

        if target_role.level >= actor_role.level:
            raise ForbiddenError("Cannot remove a member with an equal or higher role")

        await self.team_repo.remove_member(target_member)
        await self.task_repo.unassign_active_for_departing_member(team_id, target_user_id, now)
        await self.session.commit()
