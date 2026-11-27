from uuid import UUID

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        task_id: UUID,
        author_id: UUID,
        content: str,
        parent_id: UUID | None = None,
    ) -> Comment:
        comment = Comment(
            task_id=task_id,
            author_id=author_id,
            content=content,
            parent_id=parent_id,
        )
        self.session.add(comment)
        await self.session.flush()
        await self.session.refresh(comment)
        return comment

    async def get_by_id(self, task_id: UUID, comment_id: UUID) -> Comment | None:
        result = await self.session.execute(
            select(Comment).where(Comment.task_id == task_id, Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_depth(self, task_id: UUID, comment_id: UUID) -> int:
        base_cte = (
            select(
                Comment.id.label("id"),
                Comment.parent_id.label("parent_id"),
                literal(0).label("depth"),
            )
            .where(Comment.task_id == task_id, Comment.id == comment_id)
            .cte(name="ancestor_chain", recursive=True)
        )
        recursive_part = (
            select(
                Comment.id.label("id"),
                Comment.parent_id.label("parent_id"),
                (base_cte.c.depth + 1).label("depth"),
            )
            .join(base_cte, Comment.id == base_cte.c.parent_id)
            .where(Comment.task_id == task_id)
        )
        chain_cte = base_cte.union_all(recursive_part)
        result = await self.session.execute(select(func.max(chain_cte.c.depth)))
        max_depth = result.scalar_one_or_none()
        return int(max_depth) if max_depth is not None else 0

    async def list_roots_with_replies(
        self,
        task_id: UUID,
        page: int,
        size: int,
        max_depth: int,
        max_replies: int = 500,
    ) -> tuple[list[Comment], list[Comment], int]:
        total = (
            await self.session.execute(
                select(func.count(Comment.id)).where(
                    Comment.task_id == task_id,
                    Comment.parent_id.is_(None),
                )
            )
        ).scalar_one()

        roots_stmt = (
            select(Comment)
            .where(Comment.task_id == task_id, Comment.parent_id.is_(None))
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        roots = list((await self.session.execute(roots_stmt)).scalars().all())
        if not roots:
            return [], [], total

        root_ids = [root.id for root in roots]
        base_cte = (
            select(
                Comment.id.label("id"),
                Comment.created_at.label("created_at"),
                literal(1).label("depth"),
            )
            .where(Comment.task_id == task_id, Comment.parent_id.in_(root_ids))
            .cte(name="comment_tree", recursive=True)
        )
        recursive_part = (
            select(
                Comment.id.label("id"),
                Comment.created_at.label("created_at"),
                (base_cte.c.depth + 1).label("depth"),
            )
            .join(base_cte, Comment.parent_id == base_cte.c.id)
            .where(Comment.task_id == task_id, base_cte.c.depth < max_depth)
        )
        tree_cte = base_cte.union_all(recursive_part)

        limited_ids = (
            select(tree_cte.c.id)
            .order_by(tree_cte.c.depth.asc(), tree_cte.c.created_at.asc(), tree_cte.c.id.asc())
            .limit(max_replies)
        )
        descendants_stmt = (
            select(Comment)
            .where(Comment.task_id == task_id, Comment.id.in_(limited_ids))
            .order_by(Comment.created_at.asc(), Comment.id.asc())
        )
        descendants = list((await self.session.execute(descendants_stmt)).scalars().all())
        return roots, descendants, total
