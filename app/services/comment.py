from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.permissions import Permission
from app.models.comment import Comment
from app.models.team import TeamMember
from app.repositories.comment import CommentRepository
from app.repositories.role import RoleRepository
from app.repositories.task import TaskRepository
from app.repositories.team import TeamRepository
from app.schemas.comment import CommentCreate, CommentResponse
from app.schemas.common import PaginatedResponse, build_paginated_response
from app.schemas.user import UserPublic

MAX_COMMENT_DEPTH = 10
MAX_COMMENT_REPLIES_PER_PAGE = 500


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.comment_repo = CommentRepository(session)
        self.task_repo = TaskRepository(session)
        self.team_repo = TeamRepository(session)
        self.role_repo = RoleRepository(session)

    def _to_response(self, comment: Comment) -> CommentResponse:
        return CommentResponse(
            id=comment.id,
            task_id=comment.task_id,
            author_id=comment.author_id,
            author=UserPublic.model_validate(comment.author),
            parent_id=comment.parent_id,
            content=comment.content,
            created_at=comment.created_at,
            replies=[],
        )

    async def create_comment(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
        data: CommentCreate,
    ) -> CommentResponse:
        locked_actor = await self.team_repo.get_member(team_id, actor.user_id, for_share=True)
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")
        actor_role = await self.role_repo.get_by_id(team_id, locked_actor.role_id, for_share=True)
        if actor_role is None:
            raise ForbiddenError("Team role not found")

        permissions = actor_role.permission_set
        if Permission.TASK_READ not in permissions or Permission.COMMENT_CREATE not in permissions:
            raise ForbiddenError("Insufficient permissions to comment on tasks")

        task = await self.task_repo.get_by_id(team_id, task_id, for_key_share=True)
        if task is None:
            raise NotFoundError("Task not found")

        if data.parent_id is not None:
            parent = await self.comment_repo.get_by_id(task_id, data.parent_id)
            if parent is None:
                raise NotFoundError("Parent comment not found in this task")
            parent_depth = await self.comment_repo.get_depth(task_id, parent.id)
            if parent_depth + 1 > MAX_COMMENT_DEPTH:
                raise BadRequestError("Maximum comment reply nesting depth exceeded")

        try:
            comment = await self.comment_repo.create(
                task_id=task_id,
                author_id=actor.user_id,
                content=data.content,
                parent_id=data.parent_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise NotFoundError("Task or parent comment not found") from exc
        return self._to_response(comment)

    async def list_comments(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
        page: int,
        size: int,
    ) -> PaginatedResponse[CommentResponse]:
        if Permission.TASK_READ not in actor.role.permission_set:
            raise ForbiddenError("Missing permission to read comments")

        task = await self.task_repo.get_by_id(team_id, task_id)
        if task is None:
            raise NotFoundError("Task not found")

        roots, descendants, total = await self.comment_repo.list_roots_with_replies(
            task_id=task_id,
            page=page,
            size=size,
            max_depth=MAX_COMMENT_DEPTH,
            max_replies=MAX_COMMENT_REPLIES_PER_PAGE,
        )

        nodes: dict[UUID, CommentResponse] = {}
        root_responses: list[CommentResponse] = []
        for root in roots:
            node = self._to_response(root)
            nodes[node.id] = node
            root_responses.append(node)

        for reply in descendants:
            node = self._to_response(reply)
            nodes[node.id] = node

        for reply in descendants:
            if reply.parent_id is not None and reply.parent_id in nodes:
                nodes[reply.parent_id].replies.append(nodes[reply.id])

        return build_paginated_response(
            items=root_responses,
            total=total,
            page=page,
            size=size,
        )
