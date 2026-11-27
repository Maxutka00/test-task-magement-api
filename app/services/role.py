from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import (
    ADMIN_ROLE_NAME,
    Permission,
    validate_permission_dependencies,
)
from app.models.role import Role
from app.models.team import TeamMember
from app.repositories.role import RoleRepository
from app.repositories.team import TeamRepository
from app.schemas.role import RoleCreate, RoleUpdate


class RoleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.role_repo = RoleRepository(session)
        self.team_repo = TeamRepository(session)

    async def list_roles(self, team_id: UUID) -> list[Role]:
        return await self.role_repo.list_for_team(team_id)

    async def create_role(
        self,
        team_id: UUID,
        actor: TeamMember,
        data: RoleCreate,
    ) -> Role:
        locked_actor = await self.team_repo.get_member(team_id, actor.user_id, for_share=True)
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")
        actor_role = await self.role_repo.get_by_id(team_id, locked_actor.role_id, for_share=True)
        if actor_role is None:
            raise ForbiddenError("Team role not found")

        actor_permissions = actor_role.permission_set
        if Permission.ROLE_CREATE not in actor_permissions:
            raise ForbiddenError("Missing permission to create roles")

        if data.level >= actor_role.level:
            raise ForbiddenError("Cannot create a role equal to or higher than your own")

        new_permissions = set(data.permissions)
        validate_permission_dependencies(new_permissions)
        if not new_permissions.issubset(actor_permissions):
            raise ForbiddenError("Cannot grant permissions you do not possess")

        if await self.role_repo.get_by_name(team_id, data.name) is not None:
            raise ConflictError("Role with this name already exists in the team")

        try:
            role = await self.role_repo.create(
                team_id=team_id,
                name=data.name,
                level=data.level,
                permissions=new_permissions,
                is_system=False,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Role with this name already exists in the team") from exc
        return role

    async def update_role(
        self,
        team_id: UUID,
        actor: TeamMember,
        role_id: UUID,
        data: RoleUpdate,
    ) -> Role:
        locked_actor = await self.team_repo.get_member(team_id, actor.user_id, for_share=True)
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")

        role_locks = {locked_actor.role_id: "share", role_id: "update"}
        roles = await self.role_repo.get_roles_locked(team_id, role_locks)
        actor_role = roles[locked_actor.role_id]
        role = roles[role_id]

        if actor_role is None:
            raise ForbiddenError("Team role not found")

        actor_permissions = actor_role.permission_set
        if Permission.ROLE_EDIT not in actor_permissions:
            raise ForbiddenError("Missing permission to edit roles")

        if role is None:
            raise NotFoundError("Role not found")

        if role.is_system and role.name == ADMIN_ROLE_NAME:
            raise ForbiddenError("Admin role cannot be modified")

        if role.level >= actor_role.level:
            raise ForbiddenError("Cannot modify a role equal to or higher than your own")

        if not role.permission_set.issubset(actor_permissions):
            raise ForbiddenError("Cannot modify a role that has permissions you do not possess")

        if "name" in data.model_fields_set and data.name is not None and data.name != role.name:
            if role.is_system:
                raise BadRequestError("System roles cannot be renamed")
            if await self.role_repo.get_by_name(team_id, data.name) is not None:
                raise ConflictError("Role with this name already exists in the team")
            role.name = data.name

        if "level" in data.model_fields_set and data.level is not None:
            if data.level >= actor_role.level:
                raise ForbiddenError("Cannot set role level equal to or higher than your own")
            role.level = data.level

        try:
            if "permissions" in data.model_fields_set and data.permissions is not None:
                new_permissions = set(data.permissions)
                validate_permission_dependencies(new_permissions)
                if not new_permissions.issubset(actor_permissions):
                    raise ForbiddenError("Cannot grant permissions you do not possess")
                await self.role_repo.replace_permissions(role, new_permissions)

            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Role with this name already exists in the team") from exc

        await self.session.refresh(role)
        return role

    async def delete_role(
        self,
        team_id: UUID,
        actor: TeamMember,
        role_id: UUID,
    ) -> None:
        locked_actor = await self.team_repo.get_member(team_id, actor.user_id, for_share=True)
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")

        role_locks = {locked_actor.role_id: "share", role_id: "update"}
        roles = await self.role_repo.get_roles_locked(team_id, role_locks)
        actor_role = roles[locked_actor.role_id]
        role = roles[role_id]

        if actor_role is None:
            raise ForbiddenError("Team role not found")

        actor_permissions = actor_role.permission_set
        if Permission.ROLE_EDIT not in actor_permissions:
            raise ForbiddenError("Missing permission to delete roles")

        if role is None:
            raise NotFoundError("Role not found")

        if role.is_system:
            raise BadRequestError("System roles cannot be deleted")

        if role.level >= actor_role.level:
            raise ForbiddenError("Cannot delete a role equal to or higher than your own")

        if not role.permission_set.issubset(actor_permissions):
            raise ForbiddenError("Cannot delete a role that has permissions you do not possess")

        if await self.team_repo.count_members_with_role(role.id) > 0:
            raise ConflictError("Cannot delete a role currently assigned to team members")

        try:
            await self.role_repo.delete(role)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Cannot delete a role currently assigned to team members") from exc
