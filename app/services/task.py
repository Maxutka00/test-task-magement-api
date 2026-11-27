from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import Permission
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.team import TeamMember
from app.repositories.role import RoleRepository
from app.repositories.task import TaskRepository
from app.repositories.team import TeamRepository
from app.schemas.common import PaginatedResponse, build_paginated_response
from app.schemas.task import (
    SortOrder,
    TaskCreate,
    TaskResponse,
    TaskSortBy,
    TaskStatsResponse,
    TaskUpdate,
)

MAX_ACTIVE_TASKS_PER_ASSIGNEE = 10

ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.BACKLOG: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.REVIEW, TaskStatus.CANCELLED}),
    TaskStatus.REVIEW: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.task_repo = TaskRepository(session)
        self.team_repo = TeamRepository(session)
        self.role_repo = RoleRepository(session)

    def _require_read(self, actor: TeamMember) -> set[Permission]:
        permissions = actor.role.permission_set
        if Permission.TASK_READ not in permissions:
            raise ForbiddenError("Missing permission to read tasks")
        return permissions

    async def _lock_actor_permissions(
        self,
        team_id: UUID,
        actor_user_id: UUID,
        assignee_id: UUID | None = None,
    ) -> tuple[set[Permission], TeamMember | None]:
        member_locks: dict[UUID, str] = {actor_user_id: "share"}
        if assignee_id is not None:
            member_locks[assignee_id] = "update"

        members = await self.team_repo.get_members_locked(team_id, member_locks)
        locked_actor = members[actor_user_id]
        if locked_actor is None:
            raise ForbiddenError("You are not a member of this team")

        actor_role = await self.role_repo.get_by_id(team_id, locked_actor.role_id, for_share=True)
        if actor_role is None:
            raise ForbiddenError("Team role not found")

        permissions = actor_role.permission_set
        if Permission.TASK_READ not in permissions:
            raise ForbiddenError("Missing permission to read tasks")

        locked_assignee = members[assignee_id] if assignee_id is not None else None
        return permissions, locked_assignee

    async def _validate_assignee_limit(
        self,
        team_id: UUID,
        assignee_id: UUID,
        locked_member: TeamMember | None,
        exclude_task_id: UUID | None = None,
    ) -> None:
        if locked_member is None:
            raise BadRequestError("Assignee must be a member of the team")

        active_count = await self.task_repo.count_active_for_assignee(
            team_id=team_id,
            assignee_id=assignee_id,
            exclude_task_id=exclude_task_id,
        )
        if active_count >= MAX_ACTIVE_TASKS_PER_ASSIGNEE:
            raise ConflictError("Assignee cannot have more than 10 active tasks in this team")

    async def create_task(
        self,
        team_id: UUID,
        actor: TeamMember,
        data: TaskCreate,
    ) -> Task:
        assignee_id = data.assignee_id if "assignee_id" in data.model_fields_set else actor.user_id
        permissions, locked_assignee = await self._lock_actor_permissions(
            team_id,
            actor.user_id,
            assignee_id=assignee_id,
        )
        if Permission.TASK_CREATE not in permissions:
            raise ForbiddenError("Missing permission to create tasks")

        can_edit_any = Permission.TASK_EDIT_ANY in permissions
        if assignee_id is not None and assignee_id != actor.user_id and not can_edit_any:
            raise ForbiddenError("Insufficient permissions to assign tasks to other users")

        now = datetime.now(UTC)
        if data.deadline is not None and data.deadline < now:
            raise BadRequestError("Deadline cannot be earlier than the current date and time")

        if assignee_id is not None:
            await self._validate_assignee_limit(team_id, assignee_id, locked_assignee)

        task = await self.task_repo.create(
            team_id=team_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            author_id=actor.user_id,
            assignee_id=assignee_id,
            deadline=data.deadline,
        )
        await self.session.commit()
        return task

    async def get_task(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
    ) -> Task:
        self._require_read(actor)
        task = await self.task_repo.get_by_id(team_id, task_id)
        if task is None:
            raise NotFoundError("Task not found")
        return task

    async def list_tasks(
        self,
        team_id: UUID,
        actor: TeamMember,
        search: str | None,
        status: TaskStatus | None,
        priority: TaskPriority | None,
        assignee_id: UUID | None,
        deadline_from: datetime | None,
        deadline_to: datetime | None,
        sort_by: TaskSortBy | None,
        sort_order: SortOrder | None,
        page: int,
        size: int,
    ) -> PaginatedResponse[TaskResponse]:
        self._require_read(actor)
        if sort_order is not None and sort_by is None:
            raise BadRequestError("sort_order requires sort_by")
        if deadline_from is not None and deadline_to is not None and deadline_from > deadline_to:
            raise BadRequestError("deadline_from cannot be later than deadline_to")

        tasks, total = await self.task_repo.list_tasks(
            team_id=team_id,
            search=search,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            size=size,
        )
        items = [TaskResponse.model_validate(task) for task in tasks]
        return build_paginated_response(items=items, total=total, page=page, size=size)

    async def list_overdue_tasks(
        self,
        team_id: UUID,
        actor: TeamMember,
        page: int,
        size: int,
    ) -> PaginatedResponse[TaskResponse]:
        self._require_read(actor)
        tasks, total = await self.task_repo.list_overdue(
            team_id=team_id,
            now=datetime.now(UTC),
            page=page,
            size=size,
        )
        items = [TaskResponse.model_validate(task) for task in tasks]
        return build_paginated_response(items=items, total=total, page=page, size=size)

    async def get_stats(
        self,
        team_id: UUID,
        actor: TeamMember,
    ) -> TaskStatsResponse:
        self._require_read(actor)
        stats = await self.task_repo.get_stats(team_id=team_id, now=datetime.now(UTC))
        return TaskStatsResponse(**stats)

    async def update_task(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
        data: TaskUpdate,
    ) -> Task:
        target_assignee = data.assignee_id if "assignee_id" in data.model_fields_set else None
        permissions, locked_assignee = await self._lock_actor_permissions(
            team_id,
            actor.user_id,
            assignee_id=target_assignee,
        )

        task = await self.task_repo.get_by_id(team_id, task_id, for_update=True)
        if task is None:
            raise NotFoundError("Task not found")

        has_edit_any = Permission.TASK_EDIT_ANY in permissions
        has_create = Permission.TASK_CREATE in permissions
        is_author = task.author_id == actor.user_id
        if not (has_edit_any or (has_create and is_author)):
            raise ForbiddenError("Insufficient permissions to edit this task")

        if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
            raise ConflictError("Tasks in done or cancelled status cannot be edited")

        now = datetime.now(UTC)
        if "deadline" in data.model_fields_set and data.deadline is not None:
            if data.deadline < now:
                raise BadRequestError("Deadline cannot be earlier than the current date and time")

        if "assignee_id" in data.model_fields_set and data.assignee_id != task.assignee_id:
            if not has_edit_any:
                raise ForbiddenError("Insufficient permissions to change task assignee")

            if task.status in (TaskStatus.REVIEW, TaskStatus.DONE):
                raise ConflictError("Assignee cannot be changed once task is in review or done")

            if data.assignee_id is not None:
                await self._validate_assignee_limit(
                    team_id=team_id,
                    assignee_id=data.assignee_id,
                    locked_member=locked_assignee,
                    exclude_task_id=task.id,
                )
            task.assignee_id = data.assignee_id

        if "title" in data.model_fields_set and data.title is not None:
            task.title = data.title
        if "description" in data.model_fields_set:
            task.description = data.description
        if "priority" in data.model_fields_set and data.priority is not None:
            task.priority = data.priority
        if "deadline" in data.model_fields_set:
            task.deadline = data.deadline

        task.updated_at = now
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def change_status(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
        new_status: TaskStatus,
    ) -> Task:
        permissions, _ = await self._lock_actor_permissions(team_id, actor.user_id)
        task = await self.task_repo.get_by_id(team_id, task_id, for_update=True)
        if task is None:
            raise NotFoundError("Task not found")

        can_change_any = Permission.TASK_CHANGE_STATUS_ANY in permissions
        is_owner_or_assignee = (
            task.author_id == actor.user_id or task.assignee_id == actor.user_id
        )
        if not (can_change_any or is_owner_or_assignee):
            raise ForbiddenError("Insufficient permissions to change task status")

        allowed_targets = ALLOWED_STATUS_TRANSITIONS[task.status]
        if new_status not in allowed_targets:
            raise ConflictError(
                f"Transition from {task.status.value} to {new_status.value} is not allowed"
            )

        now = datetime.now(UTC)
        if new_status == TaskStatus.REVIEW:
            if task.assignee_id is None:
                raise BadRequestError("Task cannot be moved to review without an assignee")
            if await self.team_repo.get_member(team_id, task.assignee_id) is None:
                raise BadRequestError("Task assignee is no longer a member of the team")

        if new_status == TaskStatus.DONE:
            if task.assignee_id is None:
                raise BadRequestError("Task cannot be marked as done without an assignee")
            if await self.team_repo.get_member(team_id, task.assignee_id) is None:
                raise BadRequestError("Task assignee is no longer a member of the team")
            if task.deadline is not None and task.deadline <= now:
                raise BadRequestError("Task cannot be marked as done after its deadline has passed")

        task.status = new_status
        task.updated_at = now
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def delete_task(
        self,
        team_id: UUID,
        actor: TeamMember,
        task_id: UUID,
    ) -> None:
        permissions, _ = await self._lock_actor_permissions(team_id, actor.user_id)
        if Permission.TASK_DELETE not in permissions:
            raise ForbiddenError("Missing permission to delete tasks")

        task = await self.task_repo.get_by_id(team_id, task_id, for_update=True)
        if task is None:
            raise NotFoundError("Task not found")

        if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
            raise ConflictError(
                "Tasks in progress or review cannot be deleted; cancel or complete them first"
            )

        await self.task_repo.delete(task)
        await self.session.commit()
