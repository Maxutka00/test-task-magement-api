from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import USER_ROLE_NAME, Permission
from app.models.invitation import InvitationStatus, TeamInvitation
from app.models.role import Role
from app.models.team import TeamMember
from app.models.user import User
from app.repositories.invitation import InvitationRepository
from app.repositories.role import RoleRepository
from app.repositories.team import TeamRepository
from app.repositories.user import UserRepository
from app.schemas.invitation import InvitationCreate


class InvitationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.invitation_repo = InvitationRepository(session)
        self.team_repo = TeamRepository(session)
        self.role_repo = RoleRepository(session)
        self.user_repo = UserRepository(session)

    async def _lock_actor_role(self, team_id: UUID, user_id: UUID) -> Role:
        member = await self.team_repo.get_member(team_id, user_id, for_share=True)
        if member is None:
            raise ForbiddenError("You are not a member of this team")
        role = await self.role_repo.get_by_id(team_id, member.role_id, for_share=True)
        if role is None:
            raise ForbiddenError("Team role not found")
        return role

    async def create_invitation(
        self,
        team_id: UUID,
        actor: TeamMember,
        data: InvitationCreate,
    ) -> TeamInvitation:
        actor_role = await self._lock_actor_role(team_id, actor.user_id)
        if Permission.TEAM_INVITE not in actor_role.permission_set:
            raise ForbiddenError("Missing permission to invite users")

        if data.user_id is not None:
            target_user = await self.user_repo.get_by_id(data.user_id)
        else:
            target_user = await self.user_repo.get_by_email(data.email or "")

        if target_user is None:
            raise NotFoundError("User not found")

        if await self.team_repo.get_member(team_id, target_user.id) is not None:
            raise ConflictError("User is already a member of this team")

        now = datetime.now(UTC)
        existing = await self.invitation_repo.get_pending_for_user_and_team(
            team_id,
            target_user.id,
            for_update=True,
        )
        if existing is not None:
            if existing.expires_at <= now:
                existing.status = InvitationStatus.EXPIRED
                await self.session.flush()
            else:
                raise ConflictError("Pending invitation already exists for this user")

        settings = get_settings()
        expires_at = now + timedelta(days=settings.invitation_expire_days)
        try:
            invitation = await self.invitation_repo.create(
                team_id=team_id,
                invited_user_id=target_user.id,
                invited_by_id=actor.user_id,
                expires_at=expires_at,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("Pending invitation already exists for this user") from exc
        return invitation

    async def list_team_invitations(
        self,
        team_id: UUID,
        actor: TeamMember,
    ) -> list[TeamInvitation]:
        if Permission.TEAM_INVITE not in actor.role.permission_set:
            raise ForbiddenError("Missing permission to view team invitations")
        await self.invitation_repo.expire_stale_for_team(team_id, datetime.now(UTC))
        await self.session.commit()
        return await self.invitation_repo.list_for_team(team_id)

    async def revoke_invitation(
        self,
        team_id: UUID,
        actor: TeamMember,
        invitation_id: UUID,
    ) -> None:
        actor_role = await self._lock_actor_role(team_id, actor.user_id)
        if Permission.TEAM_INVITE not in actor_role.permission_set:
            raise ForbiddenError("Missing permission to revoke invitations")

        invitation = await self.invitation_repo.get_by_id(
            team_id,
            invitation_id,
            for_update=True,
        )
        if invitation is None:
            raise NotFoundError("Invitation not found")

        if invitation.status != InvitationStatus.PENDING:
            raise ConflictError("Only pending invitations can be revoked")

        if invitation.expires_at <= datetime.now(UTC):
            invitation.status = InvitationStatus.EXPIRED
            await self.session.commit()
            raise ConflictError("Only pending invitations can be revoked")

        invitation.status = InvitationStatus.REVOKED
        await self.session.commit()

    async def list_my_invitations(self, user_id: UUID) -> list[TeamInvitation]:
        return await self.invitation_repo.list_pending_for_user(user_id, datetime.now(UTC))

    async def join_team_by_code(self, user: User, code: str) -> TeamMember:
        team = await self.team_repo.get_by_join_code(code)
        if team is None:
            raise ForbiddenError("Invalid team code or no active invitation")

        if await self.team_repo.get_member(team.id, user.id) is not None:
            raise ConflictError("You are already a member of this team")

        invitation = await self.invitation_repo.get_pending_for_user_and_team(
            team.id,
            user.id,
            for_update=True,
        )
        if invitation is None:
            raise ForbiddenError("Invalid team code or no active invitation")

        now = datetime.now(UTC)
        if invitation.expires_at <= now:
            invitation.status = InvitationStatus.EXPIRED
            await self.session.commit()
            raise ForbiddenError("Invalid team code or no active invitation")

        default_role = await self.role_repo.get_by_name(team.id, USER_ROLE_NAME)
        if default_role is None:
            raise NotFoundError("Default team role not found")

        invitation.status = InvitationStatus.ACCEPTED
        try:
            member = await self.team_repo.add_member(
                team_id=team.id,
                user_id=user.id,
                role_id=default_role.id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("You are already a member of this team") from exc
        return member
