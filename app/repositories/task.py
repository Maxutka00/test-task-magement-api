from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import ACTIVE_TASK_STATUSES, Task, TaskPriority, TaskStatus
from app.schemas.task import SortOrder, TaskSortBy


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        team_id: UUID,
        title: str,
        description: str | None,
        priority: TaskPriority,
        author_id: UUID,
        assignee_id: UUID | None,
        deadline: datetime | None,
    ) -> Task:
        task = Task(
            team_id=team_id,
            title=title,
            description=description,
            status=TaskStatus.BACKLOG,
            priority=priority,
            author_id=author_id,
            assignee_id=assignee_id,
            deadline=deadline,
        )
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def get_by_id(
        self,
        team_id: UUID,
        task_id: UUID,
        for_update: bool = False,
        for_key_share: bool = False,
    ) -> Task | None:
        stmt = select(Task).where(Task.team_id == team_id, Task.id == task_id)
        if for_update:
            stmt = stmt.with_for_update()
        elif for_key_share:
            stmt = stmt.with_for_update(read=True, key_share=True)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_active_for_assignee(
        self,
        team_id: UUID,
        assignee_id: UUID,
        exclude_task_id: UUID | None = None,
    ) -> int:
        stmt = select(func.count(Task.id)).where(
            Task.team_id == team_id,
            Task.assignee_id == assignee_id,
            Task.status.in_(ACTIVE_TASK_STATUSES),
        )
        if exclude_task_id is not None:
            stmt = stmt.where(Task.id != exclude_task_id)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_tasks(
        self,
        team_id: UUID,
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
    ) -> tuple[list[Task], int]:
        conditions = [Task.team_id == team_id]

        if search and search.strip():
            pattern = f"%{_escape_like(search.strip())}%"
            conditions.append(
                or_(
                    Task.title.ilike(pattern, escape="\\"),
                    Task.description.ilike(pattern, escape="\\"),
                )
            )
        if status is not None:
            conditions.append(Task.status == status)
        if priority is not None:
            conditions.append(Task.priority == priority)
        if assignee_id is not None:
            conditions.append(Task.assignee_id == assignee_id)
        if deadline_from is not None:
            conditions.append(Task.deadline >= deadline_from)
        if deadline_to is not None:
            conditions.append(Task.deadline <= deadline_to)

        count_stmt = select(func.count(Task.id)).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        priority_weight = case(
            (Task.priority == TaskPriority.HIGH, 3),
            (Task.priority == TaskPriority.MEDIUM, 2),
            (Task.priority == TaskPriority.LOW, 1),
            else_=0,
        )

        if sort_by is None:
            order_clauses = [
                priority_weight.desc(),
                Task.deadline.asc().nulls_last(),
                Task.created_at.desc(),
                Task.id.asc(),
            ]
        elif sort_by == TaskSortBy.PRIORITY:
            direction = sort_order or SortOrder.DESC
            primary = priority_weight.asc() if direction == SortOrder.ASC else priority_weight.desc()
            order_clauses = [primary, Task.deadline.asc().nulls_last(), Task.created_at.desc(), Task.id.asc()]
        elif sort_by == TaskSortBy.DEADLINE:
            direction = sort_order or SortOrder.ASC
            primary = (
                Task.deadline.desc().nulls_last()
                if direction == SortOrder.DESC
                else Task.deadline.asc().nulls_last()
            )
            order_clauses = [primary, Task.created_at.desc(), Task.id.asc()]
        else:
            direction = sort_order or SortOrder.DESC
            primary = Task.created_at.asc() if direction == SortOrder.ASC else Task.created_at.desc()
            order_clauses = [primary, Task.id.asc()]

        stmt = (
            select(Task)
            .where(*conditions)
            .order_by(*order_clauses)
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all()), total

    async def list_overdue(
        self,
        team_id: UUID,
        now: datetime,
        page: int,
        size: int,
    ) -> tuple[list[Task], int]:
        conditions = [
            Task.team_id == team_id,
            Task.deadline.is_not(None),
            Task.deadline < now,
            Task.status.notin_((TaskStatus.DONE, TaskStatus.CANCELLED)),
        ]
        total = (await self.session.execute(select(func.count(Task.id)).where(*conditions))).scalar_one()
        stmt = (
            select(Task)
            .where(*conditions)
            .order_by(Task.deadline.asc(), Task.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all()), total

    async def get_stats(self, team_id: UUID, now: datetime) -> dict:
        stmt = select(
            func.count(Task.id).label("total"),
            func.count(Task.id).filter(Task.status == TaskStatus.BACKLOG).label("st_backlog"),
            func.count(Task.id).filter(Task.status == TaskStatus.IN_PROGRESS).label("st_in_progress"),
            func.count(Task.id).filter(Task.status == TaskStatus.REVIEW).label("st_review"),
            func.count(Task.id).filter(Task.status == TaskStatus.DONE).label("st_done"),
            func.count(Task.id).filter(Task.status == TaskStatus.CANCELLED).label("st_cancelled"),
            func.count(Task.id).filter(Task.priority == TaskPriority.HIGH).label("pr_high"),
            func.count(Task.id).filter(Task.priority == TaskPriority.MEDIUM).label("pr_medium"),
            func.count(Task.id).filter(Task.priority == TaskPriority.LOW).label("pr_low"),
            func.count(Task.id)
            .filter(
                and_(
                    Task.deadline.is_not(None),
                    Task.deadline < now,
                    Task.status.notin_((TaskStatus.DONE, TaskStatus.CANCELLED)),
                )
            )
            .label("overdue"),
            func.count(Task.id).filter(Task.status.in_(ACTIVE_TASK_STATUSES)).label("active"),
        ).where(Task.team_id == team_id)

        row = (await self.session.execute(stmt)).one()
        return {
            "total": row.total,
            "by_status": {
                TaskStatus.BACKLOG: row.st_backlog,
                TaskStatus.IN_PROGRESS: row.st_in_progress,
                TaskStatus.REVIEW: row.st_review,
                TaskStatus.DONE: row.st_done,
                TaskStatus.CANCELLED: row.st_cancelled,
            },
            "by_priority": {
                TaskPriority.HIGH: row.pr_high,
                TaskPriority.MEDIUM: row.pr_medium,
                TaskPriority.LOW: row.pr_low,
            },
            "overdue": row.overdue,
            "active": row.active,
        }

    async def delete(self, task: Task) -> None:
        await self.session.delete(task)
        await self.session.flush()

    async def unassign_active_for_departing_member(
        self,
        team_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> None:
        await self.session.execute(
            update(Task)
            .where(
                Task.team_id == team_id,
                Task.assignee_id == user_id,
                Task.status.in_((TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS)),
            )
            .values(assignee_id=None, updated_at=now)
        )
        await self.session.execute(
            update(Task)
            .where(
                Task.team_id == team_id,
                Task.assignee_id == user_id,
                Task.status == TaskStatus.REVIEW,
            )
            .values(assignee_id=None, status=TaskStatus.IN_PROGRESS, updated_at=now)
        )
        await self.session.flush()

    async def cancel_overdue_tasks(self, now: datetime) -> int:
        result = await self.session.execute(
            update(Task)
            .where(
                Task.deadline.is_not(None),
                Task.deadline < now,
                Task.status.notin_((TaskStatus.DONE, TaskStatus.CANCELLED)),
            )
            .values(status=TaskStatus.CANCELLED, updated_at=now)
            .returning(Task.id)
        )
        return len(result.all())
